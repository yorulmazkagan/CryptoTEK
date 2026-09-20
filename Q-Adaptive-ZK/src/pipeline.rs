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

use std::time::Instant;

use serde::{Deserialize, Serialize};
use winterfell::math::fields::f128::BaseElement;
use winterfell::TraceTable;

use crate::armor::{self, ArmorDecision};
use crate::hashing;
use crate::pqc::{self, PqcSignatureRecord};
use crate::trace::{
    Dilithium5InjectionPayload, MlDsaSecurityLevel, QAdaptiveTrace, TRACE_LENGTH, TRACE_WIDTH,
};

// ─────────────────────────────────────────────────────────────────────────────
// Aşama Kaydı — "arkada ne oluyor" sorusunun veri karşılığı
// ─────────────────────────────────────────────────────────────────────────────

/// Boru hattındaki tek bir aşamanın ölçülmüş kaydı.
///
/// Arayüzdeki adım adım şerit doğrudan bu listeden beslenir. Her aşama kendi
/// süresini taşır; hiçbiri tahmin edilmez ya da elle yazılmaz.
///
/// **Neden gerekli:** "AI kararı kriptografiyi sürüklüyor" iddiasını jüriye
/// göstermenin yolu, zincirin her halkasının gerçekten koştuğunu ve ne kadar
/// sürdüğünü görünür kılmaktan geçiyor. Bu liste olmadan arayüz yalnızca
/// başlangıç ve bitiş değerlerini gösterebilirdi.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct StageRecord {
    /// Aşamanın makine-okunur adı (arayüz bunu etikete çevirir).
    pub name: String,
    /// Ölçülen süre (milisaniye).
    pub ms: f64,
    /// Aşama başarıyla tamamlandı mı?
    pub ok: bool,
    /// Kısa, insan-okunur ayrıntı (ör. "8×7 = 56 eleman").
    pub detail: String,
}

impl StageRecord {
    fn yeni(name: &str, baslangic: Instant, detail: impl Into<String>) -> Self {
        Self {
            name: name.to_string(),
            ms: baslangic.elapsed().as_secs_f64() * 1000.0,
            ok: true,
            detail: detail.into(),
        }
    }
}

/// Kafes matrisinin arayüze taşınabilir anlık görüntüsü.
///
/// Matris en fazla 8×7 = 56 eleman olduğu için tamamı payload'a sığar.
/// Hücreler **dize olarak** serileştirilir: `u128` değerleri JSON sayı
/// aralığını aşabilir ve JavaScript tarafında sessizce hassasiyet kaybederdi.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct LatticeSnapshot {
    /// Matris satır sayısı (k).
    pub k: usize,
    /// Matris sütun sayısı (ℓ).
    pub ell: usize,
    /// Toplam eleman sayısı (k × ℓ) — arayüz ızgarayı buna göre çizer.
    pub cell_count: usize,
    /// Hücre değerleri, satır satır, dize olarak.
    pub cells: Vec<Vec<String>>,
    /// Matrisin skalar taahhüdü.
    pub commitment: String,
}

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
    /// Bu koşuda yürütülen aşamaların ölçülmüş kaydı.
    ///
    /// Normal modda yalnızca karar aşamaları bulunur (kafes ve imza
    /// üretilmediği için onların aşamaları yoktur). Kanıt akışında
    /// `main.rs` bu listeye STARK aşamalarını da ekler.
    pub stages: Vec<StageRecord>,
    /// Kafes matrisinin anlık görüntüsü (kanıt üretilmediyse `None`).
    pub lattice: Option<LatticeSnapshot>,
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
    let mut stages: Vec<StageRecord> = Vec::new();

    // ── Aşama: zırh kararı ──────────────────────────────────────────────────
    let t = Instant::now();
    let decision = armor::decide(request.risk_score, request.tau, request.baseline);
    stages.push(StageRecord::yeni(
        "armor_karari",
        t,
        format!(
            "risk {:.2} vs τ {:.2} → {}",
            request.risk_score,
            request.tau,
            decision.level.name()
        ),
    ));

    // ── Aşama: ρ' türetimi ──────────────────────────────────────────────────
    let t = Instant::now();
    let rho_prime = match request.rho_override {
        Some(seed) => seed,
        None => hashing::derive_rho_prime(
            request.risk_score,
            request.epoch_ns,
            request.user_op_hash.as_bytes(),
            request.fresh_entropy.as_ref(),
        ),
    };
    stages.push(StageRecord::yeni(
        "rho_turetimi",
        t,
        if request.rho_override.is_some() {
            "dışarıdan verildi".to_string()
        } else {
            format!("BLAKE3 → {}…", &hex::encode(&rho_prime[..8]))
        },
    ));

    if !decision.proof_required {
        return Ok(RunOutcome {
            decision,
            rho_prime,
            payload: None,
            pqc: None,
            deterministic: request.fresh_entropy.is_none(),
            stages,
            lattice: None,
        });
    }

    // ── Aşama: kafes genişletme (kısa tohum türetimi dahil) ─────────────────
    let t = Instant::now();
    let payload = Dilithium5InjectionPayload::from_rho_prime(rho_prime, decision.level);
    stages.push(StageRecord::yeni(
        "kafes_genisletme",
        t,
        format!(
            "{}×{} = {} eleman (SHAKE-128)",
            payload.config.k,
            payload.config.ell,
            payload.config.matrix_elements()
        ),
    ));

    let lattice = LatticeSnapshot {
        k: payload.config.k,
        ell: payload.config.ell,
        cell_count: payload.config.matrix_elements(),
        cells: payload
            .matrix_a
            .iter()
            .map(|satir| satir.iter().map(|h| h.to_string()).collect())
            .collect(),
        commitment: payload.lattice_commitment.to_string(),
    };

    // İmzalanan mesaj: bu koşuyu benzersiz kılan bağlam.
    // Aynı ρ' ile farklı bir UserOperation imzalanırsa imza da farklı olur.
    let mesaj = format!(
        "Q-ADAPTIVE|run={}|op={}|epoch={}|tier={}",
        request.run_id,
        request.user_op_hash,
        request.epoch_ns,
        decision.level.name(),
    );

    // ── Aşamalar: ML-DSA keygen · imzalama · doğrulama · kurcalama testi ────
    //
    // `sign_and_verify` dördünü de kendi içinde ölçüyor; burada tek tek
    // aşama kaydına çevriliyor. Böylece arayüz "hangi adım pahalı?" sorusunu
    // cevaplayabiliyor — ML-DSA'da bu genellikle keygen'dir.
    let pqc_record = pqc::sign_and_verify(&rho_prime, decision.level, mesaj.as_bytes())?;

    stages.push(StageRecord {
        name: "mldsa_keygen".to_string(),
        ms: pqc_record.keygen_ms,
        ok: true,
        detail: format!(
            "pk {} B · sk {} B",
            pqc_record.public_key_len, pqc_record.secret_key_len
        ),
    });
    stages.push(StageRecord {
        name: "mldsa_imzalama".to_string(),
        ms: pqc_record.sign_ms,
        ok: true,
        detail: format!("imza {} B", pqc_record.signature_len),
    });
    stages.push(StageRecord {
        name: "mldsa_dogrulama".to_string(),
        ms: pqc_record.verify_ms,
        ok: pqc_record.verified,
        detail: if pqc_record.verified {
            "imza geçerli".to_string()
        } else {
            "DOĞRULANAMADI".to_string()
        },
    });
    stages.push(StageRecord {
        name: "kurcalama_testi".to_string(),
        ms: pqc_record.tamper_ms,
        ok: pqc_record.tamper_rejected,
        detail: if pqc_record.tamper_rejected {
            "kurcalanmış mesaj reddedildi".to_string()
        } else {
            "KURCALAMA KABUL EDİLDİ".to_string()
        },
    });

    Ok(RunOutcome {
        decision,
        rho_prime,
        payload: Some(payload),
        pqc: Some(pqc_record),
        deterministic: request.fresh_entropy.is_none(),
        stages,
        lattice: Some(lattice),
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

    /// Aşamalar beklenen sırayla kaydediliyor.
    ///
    /// Arayüzdeki adım adım şerit bu sıraya güveniyor. Bir aşama eklenir,
    /// çıkarılır ya da yeri değişirse bu test kırılır ve arayüzün hangi
    /// adımı gösterdiği belirsiz kalmaz.
    #[test]
    fn asamalar_sirayla_kaydediliyor() {
        let panik = run(&istek(95.0, 75.0)).unwrap();
        let adlar: Vec<&str> = panik.stages.iter().map(|s| s.name.as_str()).collect();

        assert_eq!(
            adlar,
            vec![
                "armor_karari",
                "rho_turetimi",
                "kafes_genisletme",
                "mldsa_keygen",
                "mldsa_imzalama",
                "mldsa_dogrulama",
                "kurcalama_testi",
            ]
        );

        // Normal modda kripto aşamaları hiç koşmaz — uydurulmuş aşama olmamalı.
        let normal = run(&istek(50.0, 75.0)).unwrap();
        let normal_adlar: Vec<&str> = normal.stages.iter().map(|s| s.name.as_str()).collect();
        assert_eq!(normal_adlar, vec!["armor_karari", "rho_turetimi"]);
    }

    /// Ölçülmeyen bir aşama listede yer ALMAMALI.
    ///
    /// "payload_yazma" bir aşama olarak eklenmişti ama kendi süresini kendi
    /// yazdığı dosyaya koyamadığı için her koşuda 0.000 ms yazıyordu.
    /// Ölçülmemiş bir şeyi ölçülmüş gibi göstermek, bu denetimin kapattığı
    /// hata sınıfının ta kendisi — o yüzden kaldırıldı ve bu test geri
    /// gelmesini engelliyor.
    #[test]
    fn olculmeyen_asama_listeye_girmiyor() {
        let sonuc = run(&istek(95.0, 75.0)).unwrap();

        assert!(
            !sonuc.stages.iter().any(|s| s.name == "payload_yazma"),
            "payload_yazma aşaması geri gelmiş — süresi ölçülemiyor"
        );
    }

    #[test]
    fn asama_sureleri_makul() {
        let sonuc = run(&istek(95.0, 75.0)).unwrap();

        for asama in &sonuc.stages {
            assert!(
                asama.ms >= 0.0,
                "{} süresi negatif: {}",
                asama.name,
                asama.ms
            );
            assert!(
                asama.ms < 10_000.0,
                "{} süresi mantıksız: {} ms",
                asama.name,
                asama.ms
            );
            assert!(asama.ok, "{} başarısız: {}", asama.name, asama.detail);
            assert!(!asama.detail.is_empty(), "{} ayrıntısı boş", asama.name);
        }
    }

    /// Kurcalama testi CANLI hatta koşuyor — testte değil.
    #[test]
    fn kurcalama_testi_canli_hatta_kosuyor() {
        let sonuc = run(&istek(95.0, 75.0)).unwrap();

        let kurcalama = sonuc
            .stages
            .iter()
            .find(|s| s.name == "kurcalama_testi")
            .expect("kurcalama_testi aşaması yok");

        assert!(kurcalama.ok, "kurcalama reddedilmedi");
        assert!(sonuc.pqc.as_ref().unwrap().tamper_rejected);
    }

    /// Kafes matrisi arayüze taşınabilir hâlde payload'a giriyor.
    #[test]
    fn kafes_payloadda_tasiniyor() {
        for (risk, k, ell) in [(76.0, 4, 4), (82.0, 6, 5), (95.0, 8, 7)] {
            let sonuc = run(&istek(risk, 75.0)).unwrap();
            let kafes = sonuc.lattice.as_ref().expect("kafes anlık görüntüsü yok");

            assert_eq!((kafes.k, kafes.ell), (k, ell));
            assert_eq!(kafes.cell_count, k * ell);
            assert_eq!(kafes.cells.len(), k);
            assert!(kafes.cells.iter().all(|satir| satir.len() == ell));

            // Hücreler DİZE olmalı: u128 değerleri JSON sayı aralığını aşabilir
            // ve JavaScript tarafında sessizce hassasiyet kaybederdi.
            assert!(kafes.cells[0][0].parse::<u128>().is_ok());
        }

        // Kanıt üretilmeyen koşuda kafes de olmamalı — boş ızgara gösterilmesin.
        assert!(run(&istek(50.0, 75.0)).unwrap().lattice.is_none());
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
