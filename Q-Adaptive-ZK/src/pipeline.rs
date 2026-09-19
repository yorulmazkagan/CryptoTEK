// =============================================================================
// Q-ADAPTIVE ZK — Otonomi Köprüsü (src/pipeline.rs)
// =============================================================================
// AI'ın risk kararının kriptografik katmana ULAŞTIĞI yer burasıdır.
//
// Önceki durum — iki ayrı kopukluk:
//
//   1) API, prover'ı HİÇ ARGÜMAN GEÇMEDEN çağırıyordu:
//        `create_subprocess_exec(binary)` — argüman listesi boş.
//      Prover da her koşuda kendi varsayılanlarıyla (risk = 98.52,
//      zırh = ML-DSA-87) çalışıyordu. Matris koşudan koşuya değişiyordu ama
//      ZAMANA bağlı olarak; AI'ın skoruna bağlı olarak değil. Yani "AI kararı
//      kriptografiyi değiştiriyor" iddiasının kodda karşılığı yoktu.
//
//   2) Gösterilen iz ile kanıtlanan iz iki ayrı yerde, iki ayrı aritmetikle
//      üretiliyordu (bkz. trace.rs'teki E2 notu). Sahnedeki tablo STARK'ın
//      kanıtladığı tablo değildi.
//
// Bu modül ikisini de tek akışta toplar:
//
//   RunRequest (risk, τ, taban, userOpHash, dönem)
//        │
//        ├─► armor::decide      → kademe + kanıt gerekli mi
//        ├─► hashing::derive_rho_prime → ρ'
//        ├─► trace::from_rho_prime     → kafes + kısa tohumlar
//        ├─► trace_table_from          → Winterfell tablosu (KOPYA)
//        └─► pqc::sign_and_verify      → gerçek ML-DSA imzası
//
// `trace_table_from` kritik: Winterfell tablosunu sıfırdan hesaplamaz,
// `QAdaptiveTrace`'ten hücre hücre KOPYALAR. İki temsilin ayrışması
// yapısal olarak imkânsız hâle gelir.
// =============================================================================

use winterfell::math::fields::f128::BaseElement;
use winterfell::TraceTable;

use crate::armor::{self, ArmorDecision};
use crate::hashing;
use crate::pqc::{self, PqcSignatureRecord};
use crate::trace::{
    Dilithium5InjectionPayload, MlDsaSecurityLevel, QAdaptiveTrace, TRACE_LENGTH, TRACE_WIDTH,
};

// ─────────────────────────────────────────────────────────────────────────────
// Koşu Girdisi
// ─────────────────────────────────────────────────────────────────────────────

/// Bir prover koşusunun tüm girdileri.
///
/// Bu yapının alanları birebir CLI argümanlarına karşılık gelir; API katmanı
/// her koşuda bunların hepsini geçirir. Hiçbiri prover içinde varsayılan
/// değere düşmez — düşerse otonomi köprüsü yine kopar.
#[derive(Clone, Debug)]
pub struct RunRequest {
    /// AI'ın ürettiği risk yüzdesi (`--risk-score`).
    pub risk_score: f64,
    /// Dinamik eşik τ(t) (`--tau`).
    pub tau: f64,
    /// Hesabın taban zırh kademesi (`--baseline`).
    pub baseline: MlDsaSecurityLevel,
    /// Bu kanıtın bağlandığı UserOperation özeti (`--user-op-hash`).
    pub user_op_hash: String,
    /// Dönem damgası, nanosaniye (`--epoch-ns`).
    pub epoch_ns: u64,
    /// Koşu kimliği — loglarda ve payload'da izlenebilirlik için (`--run-id`).
    pub run_id: String,
    /// Taze entropi (`--fresh-entropy`). `None` ise koşu tam deterministiktir.
    pub fresh_entropy: Option<[u8; 32]>,
    /// ρ' doğrudan verilmişse (`--rho-prime`) türetme atlanır.
    pub rho_override: Option<[u8; 32]>,
}

impl RunRequest {
    /// Elle koşular için makul bir varsayılan.
    ///
    /// Dikkat: `risk_score` burada τ'nun ALTINDA seçilmiştir. Eski prover'ın
    /// varsayılanı 98.52 idi ve argümansız her çağrı panik moduna giriyordu;
    /// bu, "kanıt üretildi" görüntüsünü AI'dan bağımsız olarak üretiyordu.
    pub fn elle_kosu() -> Self {
        Self {
            risk_score: 50.0,
            tau: armor::VARSAYILAN_TAU,
            baseline: MlDsaSecurityLevel::Level44,
            user_op_hash: String::new(),
            epoch_ns: 0,
            run_id: "elle".to_string(),
            fresh_entropy: None,
            rho_override: None,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Koşu Çıktısı
// ─────────────────────────────────────────────────────────────────────────────

/// Bir koşunun ürettiği her şey — kanıt üretilmediği durumlar dahil.
#[derive(Clone, Debug)]
pub struct RunOutcome {
    /// Zırh kararı (kademe, kanıt gerekli mi, durum metni).
    pub decision: ArmorDecision,
    /// Bu koşuda kullanılan ρ'.
    pub rho_prime: [u8; 32],
    /// Kanıt gerekliyse üretilen kafes payload'u.
    pub payload: Option<Dilithium5InjectionPayload>,
    /// Kanıt gerekliyse ölçülmüş ML-DSA imza kaydı.
    pub pqc: Option<PqcSignatureRecord>,
    /// Koşu tam deterministik miydi? (`fresh_entropy` verilmediyse `true`)
    pub deterministic: bool,
}

// ─────────────────────────────────────────────────────────────────────────────
// Ana Akış
// ─────────────────────────────────────────────────────────────────────────────

/// Bir koşuyu baştan sona yürütür.
///
/// Kanıt üretilmesi gerekmiyorsa (`risk < τ`) kafes ve imza üretilmez ve
/// `payload`/`pqc` alanları `None` döner. **Bu durumda çağıran taraf
/// diskteki eski bir kanıtı okumamalıdır** — API katmanındaki o davranış
/// (bayat dosya geri dönüşü) kaldırılmıştır.
pub fn run(request: &RunRequest) -> Result<RunOutcome, String> {
    let decision = armor::decide(request.risk_score, request.tau, request.baseline);

    let rho_prime = match request.rho_override {
        Some(seed) => seed,
        None => hashing::derive_rho_prime(
            request.risk_score,
            request.epoch_ns,
            request.user_op_hash.as_bytes(),
            request.fresh_entropy.as_ref(),
        ),
    };

    if !decision.proof_required {
        return Ok(RunOutcome {
            decision,
            rho_prime,
            payload: None,
            pqc: None,
            deterministic: request.fresh_entropy.is_none(),
        });
    }

    let payload = Dilithium5InjectionPayload::from_rho_prime(rho_prime, decision.level);

    // İmzalanan mesaj: bu koşuyu benzersiz kılan bağlam.
    // Aynı ρ' ile farklı bir UserOperation imzalanırsa imza da farklı olur.
    let mesaj = format!(
        "Q-ADAPTIVE|run={}|op={}|epoch={}|tier={}",
        request.run_id,
        request.user_op_hash,
        request.epoch_ns,
        decision.level.name(),
    );

    let pqc_record = pqc::sign_and_verify(&rho_prime, decision.level, mesaj.as_bytes())?;

    Ok(RunOutcome {
        decision,
        rho_prime,
        payload: Some(payload),
        pqc: Some(pqc_record),
        deterministic: request.fresh_entropy.is_none(),
    })
}

// ─────────────────────────────────────────────────────────────────────────────
// İz Tablosu — TEK KAYNAK
// ─────────────────────────────────────────────────────────────────────────────

/// `QAdaptiveTrace`'ten Winterfell `TraceTable`'ı KOPYALAYARAK üretir.
///
/// Burada hiçbir aritmetik YENİDEN hesaplanmaz. Eski `build_parameterized_trace`
/// fonksiyonu `trace.fill(...)` içinde kendi geçiş mantığını baştan yazıyordu;
/// iki uygulama zamanla ayrıştı (hata E2). Kopyalama, o sınıf hatayı yapısal
/// olarak imkânsız kılar.
pub fn trace_table_from(q_trace: &QAdaptiveTrace) -> TraceTable<BaseElement> {
    let uzunluk = q_trace.length();
    let mut table = TraceTable::new(TRACE_WIDTH, uzunluk);

    table.fill(
        |state| {
            for (col, hucre) in state.iter_mut().enumerate().take(TRACE_WIDTH) {
                *hucre = q_trace.get(0, col);
            }
        },
        |step, state| {
            // `step` mevcut adım; doldurulan satır `step + 1`.
            let sonraki = step + 1;
            for (col, hucre) in state.iter_mut().enumerate().take(TRACE_WIDTH) {
                *hucre = q_trace.get(sonraki, col);
            }
        },
    );

    table
}

/// Bir koşu sonucundan doğrudan Winterfell tablosu üretir.
///
/// `main` akışı tabloyu `build_trace_for_display_and_proof` üzerinden alır
/// (çünkü aynı anda ekrana da basar); bu kısayol testlerden çağrılır.
#[allow(dead_code)]
pub fn trace_table_for(outcome: &RunOutcome) -> Option<TraceTable<BaseElement>> {
    let payload = outcome.payload.as_ref()?;
    let q_trace = QAdaptiveTrace::new(payload, TRACE_LENGTH);
    Some(trace_table_from(&q_trace))
}

// ─────────────────────────────────────────────────────────────────────────────
// Birim Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use winterfell::Trace;

    fn istek(risk: f64, tau: f64) -> RunRequest {
        RunRequest {
            risk_score: risk,
            tau,
            baseline: MlDsaSecurityLevel::Level44,
            user_op_hash: "0xdeadbeefcafebabe".to_string(),
            epoch_ns: 1_700_000_000_000_000_000,
            run_id: "test".to_string(),
            fresh_entropy: None,
            rho_override: None,
        }
    }

    /// BULGU 2 REGRESYONU — AI'ın riski kriptografik katmana ULAŞIYOR.
    ///
    /// Risk değişince kafes boyutu ve imza boyutu değişmeli. Argümanlar
    /// prover'a geçmeyi bırakırsa (eski `create_subprocess_exec(binary)`
    /// davranışı) bu test kırılır: üç koşu da aynı sonucu verir.
    #[test]
    fn otonomi_koprusu_riski_kripto_katmanina_tasiyor() {
        let dusuk = run(&istek(76.0, 75.0)).unwrap(); // aşım  1 → 44
        let orta = run(&istek(82.0, 75.0)).unwrap(); // aşım  7 → 65
        let yuksek = run(&istek(95.0, 75.0)).unwrap(); // aşım 20 → 87

        let k = |o: &RunOutcome| o.payload.as_ref().unwrap().config.matrix_elements();
        assert_eq!((k(&dusuk), k(&orta), k(&yuksek)), (16, 30, 56));

        let s = |o: &RunOutcome| o.pqc.as_ref().unwrap().signature_len;
        assert_eq!((s(&dusuk), s(&orta), s(&yuksek)), (2_420, 3_309, 4_627));
    }

    /// BULGU 3 REGRESYONU — τ köprüsü kanıt üretimini gerçekten tetikliyor.
    #[test]
    fn tau_koprusu_kanit_uretimini_tetikliyor() {
        // Aynı risk, farklı τ → farklı karar.
        let panik = run(&istek(82.0, 75.0)).unwrap();
        let normal = run(&istek(82.0, 90.0)).unwrap();

        assert!(
            panik.payload.is_some(),
            "risk 82 > τ 75 iken kanıt üretilmeli"
        );
        assert!(
            normal.payload.is_none(),
            "risk 82 < τ 90 iken kanıt üretilmemeli"
        );
        assert!(normal.pqc.is_none());
    }

    /// HATA E2 REGRESYONU — gösterilen iz, kanıtlanan izle AYNI.
    ///
    /// Winterfell tablosunun her hücresi `QAdaptiveTrace`'in aynı hücresine
    /// eşit olmalı. İki uygulama tekrar ayrışırsa bu test kırılır.
    #[test]
    fn gosterilen_iz_kanitlanan_izle_ayni() {
        let sonuc = run(&istek(95.0, 75.0)).unwrap();
        let payload = sonuc.payload.as_ref().unwrap();
        let q_trace = QAdaptiveTrace::new(payload, TRACE_LENGTH);
        let table = trace_table_from(&q_trace);

        assert_eq!(table.length(), TRACE_LENGTH);
        assert_eq!(table.width(), TRACE_WIDTH);

        for step in 0..TRACE_LENGTH {
            for col in 0..TRACE_WIDTH {
                assert_eq!(
                    table.get(col, step),
                    q_trace.get(step, col),
                    "Adım {} sütun {}: gösterilen iz kanıtlanan izden ayrıştı",
                    step,
                    col
                );
            }
        }
    }

    /// İz tablosunun MLWE ilişkisini her adımda sağladığını sınar.
    #[test]
    fn iz_mlwe_iliskisini_saglıyor() {
        let sonuc = run(&istek(95.0, 75.0)).unwrap();
        let payload = sonuc.payload.as_ref().unwrap();
        let q_trace = QAdaptiveTrace::new(payload, TRACE_LENGTH);

        for step in 0..TRACE_LENGTH {
            let a = q_trace.get(step, 0);
            let s1 = q_trace.get(step, 1);
            let s2 = q_trace.get(step, 2);
            let t = q_trace.get(step, 3);
            assert_eq!(t, a * s1 + s2, "adım {}", step);
        }
    }

    /// BULGU 11 REGRESYONU — aynı girdi birebir aynı çıktı.
    #[test]
    fn ayni_girdi_birebir_ayni_cikti() {
        let a = run(&istek(95.0, 75.0)).unwrap();
        let b = run(&istek(95.0, 75.0)).unwrap();

        assert_eq!(a.rho_prime, b.rho_prime, "ρ' iki koşuda farklı çıktı");
        assert_eq!(
            a.pqc.as_ref().unwrap().public_key_commitment,
            b.pqc.as_ref().unwrap().public_key_commitment,
            "Aynı girdi aynı anahtarı vermeli"
        );
        assert_eq!(
            a.pqc.as_ref().unwrap().signature_prefix_hex,
            b.pqc.as_ref().unwrap().signature_prefix_hex,
            "Aynı girdi aynı imzayı vermeli"
        );
        assert!(a.deterministic && b.deterministic);
    }

    /// Taze entropi istendiğinde koşu açıkça deterministik OLMADIĞINI bildirir.
    #[test]
    fn taze_entropi_isaretleniyor() {
        let mut ist = istek(95.0, 75.0);
        ist.fresh_entropy = Some([0x11u8; 32]);
        let sonuc = run(&ist).unwrap();

        assert!(
            !sonuc.deterministic,
            "taze entropi koşusu deterministik sayılmamalı"
        );
        // Taze entropi ρ''yü gerçekten değiştirmeli.
        assert_ne!(sonuc.rho_prime, run(&istek(95.0, 75.0)).unwrap().rho_prime);
    }

    /// userOpHash kanıta gerçekten bağlanıyor mu?
    #[test]
    fn userop_hash_kanita_bagli() {
        let mut a = istek(95.0, 75.0);
        let mut b = istek(95.0, 75.0);
        a.user_op_hash = "0xaaaa".to_string();
        b.user_op_hash = "0xbbbb".to_string();

        let ra = run(&a).unwrap();
        let rb = run(&b).unwrap();

        assert_ne!(
            ra.rho_prime, rb.rho_prime,
            "farklı UserOperation farklı ρ' vermeli"
        );
    }

    /// Taban kademe kanıt akışında da korunuyor mu?
    #[test]
    fn taban_kademe_kanit_akisinda_korunuyor() {
        let mut ist = istek(76.0, 75.0); // aşım 1 → normalde 44
        ist.baseline = MlDsaSecurityLevel::Level87;

        let sonuc = run(&ist).unwrap();
        assert_eq!(sonuc.decision.level, MlDsaSecurityLevel::Level87);
        assert_eq!(sonuc.pqc.as_ref().unwrap().signature_len, 4_627);
    }
}
