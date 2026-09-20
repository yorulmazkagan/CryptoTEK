// =============================================================================
// Q-ADAPTIVE ZK — Ana Kanıt Pipeline'ı (src/main.rs)
// =============================================================================
// Production-Grade Refactor: Rho-Prime Seed Bridge + Parameterized Pipeline
//
// Önceki sorun: Sabit seed (42, 13, 7). AI ile bağlantı yok.
//
// Yeni tasarım:
//   1. generate_rho_prime_from_entropy(): AI risk skoru + timestamp + OS CSPRNG
//      → BLAKE3 hash → 32-byte kriptografik seed ρ' üretir.
//   2. --rho-prime <hex> CLI argümanı: API katmanı bu parametreyi geçirir.
//      API, bir rotasyon kararı verdiğinde rho_prime'ı hesaplayıp binary'ye
//      argüman olarak geçer:
//        asyncio.create_subprocess_exec(binary, "--rho-prime", rho_hex, ...)
//   3. build_parameterized_trace(): LatticeModuleConfig + rho_prime'dan
//      tam MLWE iz tablosu oluşturur. Artık sabit tohumlar yok.
//   4. JSON export: proof_payload.json artık rho_prime_hex içerir —
//      API katmanı bunu onay için okur ve Solidity'e aktarır.
//
// Kullanım:
//   ./q-adaptive-zk                          # Rastgele rho_prime üret
//   ./q-adaptive-zk --rho-prime <64-char-hex># API'den gelen rho_prime kullan
// =============================================================================

use std::env;
use std::fs;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use winter_verifier::verify;
use winterfell::{
    crypto::{hashers::Blake3_256, DefaultRandomCoin, MerkleTree},
    math::{fields::f128::BaseElement, FieldElement},
    matrix::ColMatrix,
    AcceptableOptions, AuxRandElements, CompositionPoly, CompositionPolyTrace,
    DefaultConstraintCommitment, DefaultConstraintEvaluator, DefaultTraceLde, PartitionOptions,
    Proof, ProofOptions, Prover, StarkDomain, Trace, TracePolyTable, TraceTable,
};

// Proje modülleri
mod air;
mod armor;
mod bridge;
mod hashing;
mod pipeline;
mod pqc;
mod trace;

use air::{get_proof_options, QAdaptiveAir, QAdaptivePublicInputs};
use bridge::export_proof_payload;
use pipeline::{RunOutcome, RunRequest};
use trace::{MlDsaSecurityLevel, QAdaptiveTrace, TRACE_LENGTH, TRACE_WIDTH};

// ─────────────────────────────────────────────────────────────────────────────
// Sabitler
// ─────────────────────────────────────────────────────────────────────────────

const SEPARATOR: &str = "=================================================================";
const THIN_SEP: &str = "-----------------------------------------------------------------";

// ─────────────────────────────────────────────────────────────────────────────
// Rho-Prime Seed Üretimi (AI Entropi Köprüsü)
// ─────────────────────────────────────────────────────────────────────────────

/// AI Guardian risk skoru ve zaman damgasından kriptografik olarak güvenli
/// 32-byte ρ' (rho-prime) seed'i üretir.
///
/// Üretim Prosedürü (`hashing::derive_rho_prime`):
///   BLAKE3( ALAN_ETIKETI ‖ risk_bits ‖ epoch_ns ‖ len(user_op_hash) ‖
///           user_op_hash ‖ entropi_bayragi [‖ taze_entropi] ) → 32 bayt
///
///   Alan etiketi, aynı hash'in başka amaçlarla üretilen özetleriyle
///   çakışmayı önler. `user_op_hash` uzunluk ön-ekiyle yazılır ki
///   ("ab" ‖ "") ile ("a" ‖ "b") aynı özete gitmesin.
///
/// Determinizm — bu fonksiyon TAZE ENTROPİ KARIŞTIRMAZ:
///   `user_op_hash` boş, `extra_entropy` `None` olarak geçilir; entropi
///   bayrağı `0`'dır. Aynı (risk, epoch_ns) çifti her zaman aynı ρ''yü verir.
///   Bu bilinçli: jüri aynı girdiyle aynı kanıtı yeniden üretebilmeli.
///   Eski uygulama `process::id()` karıştırdığı için bu mümkün değildi.
///   Taze entropi isteyen `--fresh-entropy` ile AÇIKÇA verir ve bu durum
///   payload'da `deterministic_run = false` olarak işaretlenir.
///
/// Güvenlik Garantileri:
///   • ai_risk_score değişirse → seed tamamen farklı (risk seviyesi bağlantısı)
///   • epoch_ns çağıran tarafından verilir → tekrar koruması ÇAĞIRANIN işi,
///     bu fonksiyonun değil (bkz. yukarıdaki determinizm notu)
///   • BLAKE3 çıktısı 256-bit → ön-görüntü araması pratik değil
///
/// ρ' nereye gidiyor:
///   1. `pqc::sign_and_verify` → ξ = BLAKE3(alan ‖ ρ') → `KG::keygen_from_seed(ξ)`.
///      Bu GERÇEK bir ML-DSA anahtar üretimidir (`fips204` crate'i, FIPS 204);
///      artık bir benzetim değil.
///   2. `Dilithium5InjectionPayload::from_rho_prime` → STARK iz tablosunun
///      kafes matrisi, SHAKE-128 + reddetme örneklemesiyle genişletilir
///      (FIPS 204 §7.3 ExpandA ile aynı yordam).
///
/// # Arguments
/// * `ai_risk_score` - AI modülünden gelen risk yüzdesi (0.0 - 100.0).
/// * `timestamp_ns`  - Nanosaniye cinsinden zaman damgası (monotonic clock).
///
/// # Returns
/// 32-byte kriptografik seed [u8; 32].
pub fn generate_rho_prime_from_entropy(ai_risk_score: f64, timestamp_ns: u64) -> [u8; 32] {
    // Türetmenin tamamı `hashing::derive_rho_prime`e devredildi.
    //
    // Buradaki eski uygulama dört ayrı `DefaultHasher` (SipHash) bloğuyla
    // seed üretiyordu ve aralarına `std::process::id()` karıştırıyordu.
    // İki ayrı sorun vardı:
    //
    //   • SipHash kriptografik değil ve Rust sürümleri arasında çıktı
    //     kararlılığı GARANTİ EDİLMİYOR — yani aynı girdi başka bir
    //     derlemede başka bir ρ' üretebilirdi.
    //   • `process::id()` her koşuda değiştiği için kanıt YENİDEN
    //     ÜRETİLEBİLİR değildi; jüri aynı sonucu alamazdı.
    //
    // Taze entropi artık sessizce karıştırılmıyor: isteyen `--fresh-entropy`
    // ile açıkça veriyor ve bu payload'da işaretleniyor.
    hashing::derive_rho_prime(ai_risk_score, timestamp_ns, &[], None)
}

/// Hex string'den 32-byte rho_prime seed'i ayrıştırır.
/// API katmanı --rho-prime argümanı olarak 64 karakterlik hex string geçirir.
///
/// # Returns
/// Ok([u8; 32]) veya Err(String) — geçersiz hex formatı.
pub fn parse_rho_prime_hex(hex_str: &str) -> Result<[u8; 32], String> {
    let trimmed = hex_str.trim();
    if trimmed.len() != 64 {
        return Err(format!(
            "rho_prime hex {} karakter olmalı, {} alındı",
            64,
            trimmed.len()
        ));
    }

    let bytes = hex::decode(trimmed).map_err(|e| format!("Geçersiz hex formatı: {}", e))?;

    let mut seed = [0u8; 32];
    seed.copy_from_slice(&bytes);
    Ok(seed)
}

// ─────────────────────────────────────────────────────────────────────────────
// STARK Prover Yapısı
// ─────────────────────────────────────────────────────────────────────────────

struct QAdaptiveProver {
    options: ProofOptions,
}

impl QAdaptiveProver {
    fn new(options: ProofOptions) -> Self {
        Self { options }
    }
}

impl Prover for QAdaptiveProver {
    type BaseField = BaseElement;
    type Air = QAdaptiveAir;
    type Trace = TraceTable<Self::BaseField>;
    type HashFn = Blake3_256<Self::BaseField>;
    type VC = MerkleTree<Self::HashFn>;
    type RandomCoin = DefaultRandomCoin<Self::HashFn>;
    type TraceLde<E: FieldElement<BaseField = Self::BaseField>> =
        DefaultTraceLde<E, Self::HashFn, Self::VC>;
    type ConstraintCommitment<E: FieldElement<BaseField = Self::BaseField>> =
        DefaultConstraintCommitment<E, Self::HashFn, Self::VC>;
    type ConstraintEvaluator<'a, E: FieldElement<BaseField = Self::BaseField>> =
        DefaultConstraintEvaluator<'a, Self::Air, E>;

    fn get_pub_inputs(&self, trace: &Self::Trace) -> QAdaptivePublicInputs {
        let last_step = trace.length() - 1;
        QAdaptivePublicInputs {
            start_state: [
                trace.get(0, 0),
                trace.get(1, 0),
                trace.get(2, 0),
                trace.get(3, 0),
            ],
            final_state: [
                trace.get(0, last_step),
                trace.get(1, last_step),
                trace.get(2, last_step),
                trace.get(3, last_step),
            ],
        }
    }

    fn options(&self) -> &ProofOptions {
        &self.options
    }

    fn new_trace_lde<E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        trace_info: &winterfell::TraceInfo,
        main_trace: &ColMatrix<Self::BaseField>,
        domain: &StarkDomain<Self::BaseField>,
        partition_option: PartitionOptions,
    ) -> (Self::TraceLde<E>, TracePolyTable<E>) {
        DefaultTraceLde::new(trace_info, main_trace, domain, partition_option)
    }

    fn build_constraint_commitment<E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        composition_poly_trace: CompositionPolyTrace<E>,
        num_constraint_composition_columns: usize,
        domain: &StarkDomain<Self::BaseField>,
        partition_options: PartitionOptions,
    ) -> (Self::ConstraintCommitment<E>, CompositionPoly<E>) {
        DefaultConstraintCommitment::new(
            composition_poly_trace,
            num_constraint_composition_columns,
            domain,
            partition_options,
        )
    }

    fn new_evaluator<'a, E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        air: &'a Self::Air,
        aux_rand_elements: Option<AuxRandElements<E>>,
        composition_coefficients: winterfell::ConstraintCompositionCoefficients<E>,
    ) -> Self::ConstraintEvaluator<'a, E> {
        DefaultConstraintEvaluator::new(air, aux_rand_elements, composition_coefficients)
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline Adımları
// ─────────────────────────────────────────────────────────────────────────────

fn print_banner() {
    println!();
    println!("{SEPARATOR}");
    println!("  >>> [Q-ADAPTIVE ZK] Üretim-Grade Siber-Savunma Entegrasyon Köprüsü");
    println!("{SEPARATOR}");
    println!("  Hedef         : AI Guardian Tetikleyici -> ML-DSA STARK PQC Export");
    println!("  Çıktı Formatı : Solidity On-Chain Doğrulama (JSON Payload)");
    println!("  Kafes Modülü  : NIST FIPS 204 Parameterize k×ℓ Simülasyon");
    println!("{SEPARATOR}");
    println!();
}

/// AI sinyalini ve zırh kararını ekrana basar.
///
/// **Burada artık karar VERİLMİYOR** — karar `armor::decide`'da verilir ve
/// bu fonksiyon yalnızca sonucu gösterir.
///
/// Eski hâli kararı kendisi veriyordu: `if ai_risk_score > 90.0`. Bu sabit,
/// Python tarafındaki τ(t) ile uyuşmuyordu; risk = 82 / τ = 75 durumunda iki
/// katman zıt kararlar üretiyordu (bkz. src/armor.rs başlığı).
fn print_ai_signal(request: &RunRequest, decision: &armor::ArmorDecision) {
    println!("[ADIM 1] AI Guardian Sinyali İşleniyor...");
    println!("{THIN_SEP}");

    println!("  Analiz Edilen Anomali Skoru : {:.2}", request.risk_score);
    println!("  Dinamik Eşik τ(t)           : {:.2}", request.tau);
    println!(
        "  Taban Zırh                  : {}",
        request.baseline.name()
    );
    println!("  Sistem Durumu               : {}", decision.status);

    if decision.proof_required {
        println!("  Eşik Aşımı                  : {:.2} puan", decision.asim);
        println!("  Seçilen Zırh                : {}", decision.level.name());
        println!("  ⚠️  TEHDİT TESPİT EDİLDİ! Post-Kuantum Kalkanı Aktive Ediliyor...");
    }
    println!();
}

/// Kafes matrisini, kısa tohumları ve gerçek ML-DSA imzasını ekrana basar,
/// ardından kanıtlanacak Winterfell tablosunu döndürür.
///
/// **Tablo burada YENİDEN HESAPLANMAZ.** `pipeline::trace_table_from`
/// ekranda gösterilen `QAdaptiveTrace`'i hücre hücre kopyalar.
///
/// Eski `build_parameterized_trace` fonksiyonu `trace.fill(...)` içinde kendi
/// geçiş mantığını baştan yazıyordu; `QAdaptiveTrace` ise u128 + `% q`
/// kullanıyordu. Sahnede jüriye gösterilen tablo, STARK'ın kanıtladığı tablo
/// değildi (hata E2). Kopyalama bu ayrışmayı yapısal olarak imkânsız kılar.
fn build_trace_for_display_and_proof(outcome: &RunOutcome) -> TraceTable<BaseElement> {
    println!("[ADIM 2] Parameterize ML-DSA Kafes Matrisi Enjekte Ediliyor...");
    println!("{THIN_SEP}");

    let payload = outcome
        .payload
        .as_ref()
        .expect("kanıt gerekli koşuda payload üretilmiş olmalı");

    println!(
        "  Güvenlik Seviyesi           : {}",
        payload.config.level.name()
    );
    println!(
        "  Kafes Boyutu                : {}×{} = {} eleman",
        payload.config.k,
        payload.config.ell,
        payload.config.matrix_elements()
    );
    println!(
        "  rho_prime (ilk 8 byte)      : {}",
        hex::encode(&outcome.rho_prime[..8])
    );
    println!("  Kafes Taahhüdü (A_commit_0) : {}", payload.matrix_a[0][0]);
    println!(
        "  İz Tablosu                  : {} Sütun, {} Satır",
        TRACE_WIDTH, TRACE_LENGTH
    );
    println!(
        "  Koşu Türü                   : {}",
        if outcome.deterministic {
            "deterministik"
        } else {
            "taze entropili"
        }
    );

    if let Some(kayit) = &outcome.pqc {
        println!();
        println!("  ── Gerçek ML-DSA İmzası (fips204) ──");
        println!(
            "  Açık Anahtar                : {} bayt",
            kayit.public_key_len
        );
        println!(
            "  Gizli Anahtar               : {} bayt",
            kayit.secret_key_len
        );
        println!(
            "  İmza                        : {} bayt",
            kayit.signature_len
        );
        println!(
            "  İmza (ilk 16 bayt)          : {}...",
            kayit.signature_prefix_hex
        );
        println!(
            "  Doğrulama                   : {}",
            if kayit.verified {
                "✅ GEÇTİ"
            } else {
                "❌ KALDI"
            }
        );
    }

    println!();

    // Gösterilen tablo ve kanıtlanan tablo — tek kaynak.
    let q_trace = QAdaptiveTrace::new(payload, TRACE_LENGTH);
    q_trace.print_table();
    println!();

    pipeline::trace_table_from(&q_trace)
}

/// Winterfell STARK kanıtı üretir.
///
/// # Returns
/// `Ok(Proof)` başarılıysa, `Err(String)` kısıt ihlali veya prover hatası.
fn generate_proof(
    trace: TraceTable<BaseElement>,
    options: ProofOptions,
) -> Result<(Proof, f64), String> {
    println!("[ADIM 3] STARK Kanıtı Üretiliyor (Prover)...");
    println!("{THIN_SEP}");

    let prover = QAdaptiveProver::new(options);
    let t_start = Instant::now();
    // Güvenlik: .expect() kaldırıldı. Prover hatası (kısıt ihlali vb.) sonaç
    // program sonlanmasına değil, çağıran koda iletilen Err'ye dönüştürülür.
    let proof = prover
        .prove(trace)
        .map_err(|e| format!("STARK prover hatası: {:?}", e))?;
    // Süre payload'a yazılır; raporlarda sabitlenmiş "18.52 ms" değeri tek bir
    // makinedeki tek bir koşudan geliyordu (bkz. bridge::StarkMetrics).
    let elapsed_ms = t_start.elapsed().as_secs_f64() * 1000.0;

    println!("  ✅ Prover Çalışması Tamamlandı ({:.2} ms)", elapsed_ms);
    println!(
        "  Kanıt Ham Boyutu            : {:.2} KB",
        proof.to_bytes().len() as f64 / 1024.0
    );
    println!();

    Ok((proof, elapsed_ms))
}

fn verify_proof(proof: Proof, pub_inputs: QAdaptivePublicInputs) -> Proof {
    println!("[ADIM 4] Yerel Doğrulama (Verifier)...");
    println!("{THIN_SEP}");

    // Güvenlik seviyesi tek yerden gelir (air::STARK_SECURITY_BITS).
    // Buraya elle "80" yazmak, README'nin "96" demesiyle aynı sınıf hatadır.
    let acceptable = AcceptableOptions::MinConjecturedSecurity(air::STARK_SECURITY_BITS);
    let t_start = Instant::now();

    let result = verify::<
        QAdaptiveAir,
        Blake3_256<BaseElement>,
        DefaultRandomCoin<Blake3_256<BaseElement>>,
        MerkleTree<Blake3_256<BaseElement>>,
    >(proof.clone(), pub_inputs, &acceptable);

    let elapsed_ms = t_start.elapsed().as_millis();

    if result.is_ok() {
        println!(
            "  ✅ KANIT DOĞRULANDI! İç Bütünlük Sağlandı ({} ms)",
            elapsed_ms
        );
    } else {
        println!("  ❌ KANIT DOĞRULANAMADI! Hata: {:?}", result.err());
        std::process::exit(1);
    }
    println!();

    proof
}

fn export_payload(
    request: &RunRequest,
    outcome: &RunOutcome,
    proof: Proof,
    pub_inputs: QAdaptivePublicInputs,
    prover_ms: f64,
) {
    println!("[ADIM 5] Solidity Akıllı Sözleşme Payload'u Oluşturuluyor...");
    println!("{THIN_SEP}");

    let filepath = "proof_payload.json";
    let proof_bytes = proof.to_bytes();
    let status = outcome.decision.status;
    let risk_score = request.risk_score;
    let rho_prime = &outcome.rho_prime;
    let security_level = outcome.decision.level.name();

    // Ölçümler — hepsi bu koşudan, hiçbiri elle yazılmamış.
    let pqc_ozet = outcome.pqc.as_ref().map(|k| bridge::PqcSummary {
        tier: k.level.name().to_string(),
        public_key_bytes: k.public_key_len,
        secret_key_bytes: k.secret_key_len,
        signature_bytes: k.signature_len,
        public_key_commitment_hex: hex::encode(k.public_key_commitment),
        signature_prefix_hex: k.signature_prefix_hex.clone(),
        signature_verified: k.verified,
        keygen_ms: k.keygen_ms,
        sign_ms: k.sign_ms,
        verify_ms: k.verify_ms,
        tamper_rejected: k.tamper_rejected,
        tamper_ms: k.tamper_ms,
    });

    // Calldata tasarrufu, bu kademedeki GERÇEK imza boyutundan hesaplanır.
    let calldata = outcome.pqc.as_ref().map(|k| {
        bridge::CalldataRecord::compute(
            bridge::CalldataRecord::DEFAULT_BATCH_SIZE,
            k.signature_len,
            proof_bytes.len(),
        )
    });

    let extras = bridge::PayloadExtras {
        tau: request.tau,
        run_id: request.run_id.clone(),
        deterministic: outcome.deterministic,
        stark: bridge::StarkMetrics {
            proof_bytes: proof_bytes.len(),
            prover_ms,
            conjectured_security_bits: air::STARK_SECURITY_BITS,
            field: "f128".to_string(),
            num_queries: air::FRI_NUM_QUERIES,
            blowup_factor: air::FRI_BLOWUP_FACTOR,
        },
        pqc: pqc_ozet,
        calldata,
        // Aşamalar `outcome`'dan gelir; STARK aşamaları main akışında eklendi.
        stages: outcome.stages.clone(),
        lattice: outcome.lattice.clone(),
    };

    if let Some(c) = &extras.calldata {
        println!("  Calldata Tasarrufu          : %{:.2}", c.savings_pct);
        println!("  Formül                      : {}", c.formula);
        println!(
            "  ECDSA partisi ({} imza)     : {} bayt{}",
            c.batch_size,
            c.ecdsa_batch_bytes,
            if c.beats_ecdsa {
                ""
            } else {
                "  ← ECDSA calldata'da daha küçük"
            }
        );
    }

    match export_proof_payload(
        status,
        risk_score,
        rho_prime,
        security_level,
        &proof_bytes,
        &pub_inputs,
        extras,
        filepath,
    ) {
        Ok(_) => {
            // Güvenlik: fs::metadata().unwrap() panic'i kaldırıldı.
            // Dosya boyutu alınamazsa (yarış koşulu, izin sorunu) uyarı basılır.
            match fs::metadata(filepath) {
                Ok(meta) => {
                    let size_kb = meta.len() as f64 / 1024.0;
                    println!("  ✅ JSON Payload Başarıyla Dışa Aktarıldı!");
                    println!("  Dosya Yolu      : ./{}", filepath);
                    println!("  JSON Boyutu     : {:.2} KB", size_kb);
                    println!("  rho_prime_hex   : {}...", hex::encode(&rho_prime[..8]));
                }
                Err(e) => {
                    println!("  ✅ JSON Payload Dışa Aktarıldı (boyut alınamadı: {})", e);
                    println!("  Dosya Yolu      : ./{}", filepath);
                    println!("  rho_prime_hex   : {}...", hex::encode(&rho_prime[..8]));
                }
            }
        }
        Err(e) => {
            println!("  ❌ JSON Dışa Aktarma Hatası: {}", e);
        }
    }
    println!();
}

fn print_summary(elapsed_total_ms: u128, risk_score: f64, level: &str, rho_prime: &[u8; 32]) {
    println!("{SEPARATOR}");
    println!("  Q-ADAPTIVE ZK GUARD — ÜRETIM-GRADE PIPELINE TAMAMLANDI");
    println!("{SEPARATOR}");
    println!();
    println!("  🌐  Sistem Entegrasyon Özeti:");
    println!(
        "    AI Modülü           : Risk Tespiti Başarılı (Skor: {:.2})",
        risk_score
    );
    println!(
        "    PQC Modülü          : {} MLWE İzleme & Kanıtlama Başarılı",
        level
    );
    println!(
        "    Rho-Prime Seed (ρ') : {}...",
        hex::encode(&rho_prime[..16])
    );
    println!("    Köprü               : JSON Export Başarılı (proof_payload.json)");
    println!("    Toplam Gecikme      : {} ms", elapsed_total_ms);
    println!();
    println!("{SEPARATOR}");
    println!();
}

// ─────────────────────────────────────────────────────────────────────────────
// CLI Argüman Ayrıştırma
// ─────────────────────────────────────────────────────────────────────────────

/// Prover'ın kabul ettiği argümanlar.
///
/// API katmanı bunların hepsini her koşuda geçirir. Eskiden API prover'ı
/// `create_subprocess_exec(binary)` ile **hiç argüman vermeden** çağırıyordu;
/// prover da kendi varsayılanlarıyla (risk 98.52, zırh ML-DSA-87) koşuyordu.
/// Yani kafes her koşuda değişiyordu ama AI'ın kararına göre değil.
const KULLANIM: &str = "\
Kullanım: q-adaptive-zk [SEÇENEKLER]

Seçenekler:
  --risk-score <f64>     AI'ın ürettiği risk yüzdesi (0–100)
  --tau <f64>            Dinamik eşik τ(t)
  --level <44|65|87>     Zırh kademesini elle sabitle (τ kararını geçersiz kılar)
  --baseline <44|65|87>  Hesabın taban zırhı; kademe bunun altına inemez
  --user-op-hash <hex>   Kanıtın bağlanacağı UserOperation özeti
  --epoch-ns <u64>       Dönem damgası (nanosaniye)
  --run-id <metin>       Koşu kimliği (loglar ve payload için)
  --rho-prime <64-hex>   ρ''yü doğrudan ver (türetmeyi atlar)
  --fresh-entropy <hex>  Taze entropi ekle — koşu deterministik OLMAZ
  --help                 Bu metni göster
";

/// Ayrıştırma sonucu — hata durumunda çağıran çıkış kodu 1 ile durur.
fn parse_cli() -> Result<(RunRequest, Option<MlDsaSecurityLevel>), String> {
    let args: Vec<String> = env::args().collect();
    let mut request = RunRequest::elle_kosu();
    let mut level_override: Option<MlDsaSecurityLevel> = None;

    /// Bir seçeneğin değerini alır; eksikse açık hata döner.
    fn deger<'a>(args: &'a [String], i: usize, ad: &str) -> Result<&'a str, String> {
        args.get(i + 1)
            .map(|s| s.as_str())
            .ok_or_else(|| format!("{} bir değer bekliyor", ad))
    }

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--help" | "-h" => {
                println!("{}", KULLANIM);
                std::process::exit(0);
            }
            "--risk-score" => {
                let ham = deger(&args, i, "--risk-score")?;
                // Eskiden ayrıştırma hatası yalnızca uyarı basıp varsayılana
                // düşüyordu — sessiz yapılandırma hatası. Artık durduruyor.
                request.risk_score = ham
                    .parse::<f64>()
                    .map_err(|_| format!("--risk-score sayı olmalı, '{}' alındı", ham))?;
                i += 1;
            }
            "--tau" => {
                let ham = deger(&args, i, "--tau")?;
                request.tau = ham
                    .parse::<f64>()
                    .map_err(|_| format!("--tau sayı olmalı, '{}' alındı", ham))?;
                i += 1;
            }
            "--level" => {
                // HATA E5: eski desen `"87" | _ => Level87` geçersiz girdiyi
                // sessizce en yüksek kademeye düşürüyordu.
                level_override = Some(MlDsaSecurityLevel::parse(deger(&args, i, "--level")?)?);
                i += 1;
            }
            "--baseline" => {
                request.baseline = MlDsaSecurityLevel::parse(deger(&args, i, "--baseline")?)?;
                i += 1;
            }
            "--user-op-hash" => {
                request.user_op_hash = deger(&args, i, "--user-op-hash")?.to_string();
                i += 1;
            }
            "--epoch-ns" => {
                let ham = deger(&args, i, "--epoch-ns")?;
                request.epoch_ns = ham
                    .parse::<u64>()
                    .map_err(|_| format!("--epoch-ns tamsayı olmalı, '{}' alındı", ham))?;
                i += 1;
            }
            "--run-id" => {
                request.run_id = deger(&args, i, "--run-id")?.to_string();
                i += 1;
            }
            "--rho-prime" => {
                request.rho_override = Some(parse_rho_prime_hex(deger(&args, i, "--rho-prime")?)?);
                i += 1;
            }
            "--fresh-entropy" => {
                request.fresh_entropy =
                    Some(parse_rho_prime_hex(deger(&args, i, "--fresh-entropy")?)?);
                i += 1;
            }
            bilinmeyen => {
                return Err(format!(
                    "Bilinmeyen argüman: '{}'\n\n{}",
                    bilinmeyen, KULLANIM
                ));
            }
        }
        i += 1;
    }

    // Dönem damgası verilmediyse sistem saatinden al — ama bunu sessizce
    // yapmak determinizmi bozar, o yüzden loga yazılıyor.
    if request.epoch_ns == 0 {
        request.epoch_ns = simdi_ns();
        eprintln!(
            "[WARN][Q-ZK] --epoch-ns verilmedi, sistem saati kullanıldı ({}). \
             Tekrarlanabilir koşu için bu değeri açıkça geçirin.",
            request.epoch_ns
        );
    }

    Ok((request, level_override))
}

/// Şu anki zamanı nanosaniye olarak verir.
fn simdi_ns() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_else(|_| {
            eprintln!("[WARN][Q-ZK] Sistem saati UNIX epoch'tan önce görünüyor — 0 kullanılıyor.");
            std::time::Duration::ZERO
        })
        .as_nanos() as u64
}

// ─────────────────────────────────────────────────────────────────────────────
// Giriş Noktası
// ─────────────────────────────────────────────────────────────────────────────

fn main() {
    let t_total = Instant::now();

    // Loglama başlat
    env_logger::init();

    print_banner();

    // CLI argümanlarını ayrıştır. Geçersiz argüman artık sessizce
    // varsayılana düşmüyor — çıkış kodu 1 ile duruyoruz (hata E5).
    let (mut request, level_override) = match parse_cli() {
        Ok(v) => v,
        Err(e) => {
            eprintln!("[ERROR][Q-ZK] {}", e);
            std::process::exit(1);
        }
    };

    // `--level` verilmişse taban kademeyi oraya çekeriz; tek yönlü tırmanma
    // kuralı gereği armor::decide sonucu bunun altına düşemez.
    if let Some(level) = level_override {
        request.baseline = level;
    }

    // Adım 1: Zırh kararı — TEK kural, τ köprüsü üzerinden.
    let outcome = match pipeline::run(&request) {
        Ok(o) => o,
        Err(e) => {
            eprintln!("[ERROR][Q-ZK] Kriptografik katman hatası: {}", e);
            std::process::exit(2);
        }
    };

    print_ai_signal(&request, &outcome.decision);

    if !outcome.decision.proof_required {
        println!("  Sistem normal modda. ZK kanıt üretimi tetiklenmedi.");
        println!();
        println!("  NOT: Bu koşuda kanıt ÜRETİLMEDİ. Çağıran taraf diskteki");
        println!("       eski proof_payload.json'ı taze bir kanıt gibi sunmamalıdır.");
        println!();
        let total_ms = t_total.elapsed().as_millis();
        println!("{SEPARATOR}");
        println!(
            "  Q-ADAPTIVE ZK GUARD — Normal Mod Tamamlandı ({} ms)",
            total_ms
        );
        println!("{SEPARATOR}");
        return;
    }

    let level_name = outcome.decision.level.name();

    // `outcome` artık aşama listesini taşıyor; STARK aşamaları burada eklenecek.
    let mut outcome = outcome;

    // ── Aşama: iz tablosu ───────────────────────────────────────────────────
    let t_iz = Instant::now();
    let trace = build_trace_for_display_and_proof(&outcome);
    outcome.stages.push(pipeline::StageRecord {
        name: "iz_tablosu".to_string(),
        ms: t_iz.elapsed().as_secs_f64() * 1000.0,
        ok: true,
        detail: format!("{} satır × {} sütun", TRACE_LENGTH, TRACE_WIDTH),
    });

    // Genel girdileri çıkar
    let last_step = trace.length() - 1;
    let pub_inputs = QAdaptivePublicInputs {
        start_state: [
            trace.get(0, 0),
            trace.get(1, 0),
            trace.get(2, 0),
            trace.get(3, 0),
        ],
        final_state: [
            trace.get(0, last_step),
            trace.get(1, last_step),
            trace.get(2, last_step),
            trace.get(3, last_step),
        ],
    };
    let pub_inputs_verify = pub_inputs.clone();
    let pub_inputs_export = pub_inputs.clone();

    let options = get_proof_options();

    // ── Aşama: STARK prover ─────────────────────────────────────────────────
    // Adım 3: STARK Kanıtı Üret (Result propagasyon — program crash yok)
    let (proof, prover_ms) = match generate_proof(trace, options) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("[ERROR][Q-ZK] STARK kanıt üretimi başarısız: {}", e);
            eprintln!("[ERROR][Q-ZK] Pipeline durduruldu. proof_payload.json güncellenmedi.");
            std::process::exit(2);
        }
    };
    outcome.stages.push(pipeline::StageRecord {
        name: "stark_prover".to_string(),
        ms: prover_ms,
        ok: true,
        detail: format!("{} bayt kanıt", proof.to_bytes().len()),
    });

    // ── Aşama: yerel doğrulama ──────────────────────────────────────────────
    // Adım 4: Doğrula
    let t_dogrula = Instant::now();
    let verified_proof = verify_proof(proof, pub_inputs_verify);
    outcome.stages.push(pipeline::StageRecord {
        name: "stark_dogrulama".to_string(),
        ms: t_dogrula.elapsed().as_secs_f64() * 1000.0,
        ok: true,
        detail: format!("{} bit konjektürel", air::STARK_SECURITY_BITS),
    });

    // NOT: "payload yazma" bilinçli olarak bir AŞAMA DEĞİL.
    //
    // Bir aşama kendi süresini kendi yazdığı dosyaya koyamaz — ölçüm, yazma
    // işleminden önce bitmek zorunda kalır ve her koşuda 0.000 ms yazardı.
    // Ölçülmemiş bir şeyi ölçülmüş gibi göstermektense listeden çıkarıldı;
    // arayüz bu adımı süre iddiası olmadan bir tamamlanma işareti olarak
    // gösterir.
    //
    // Adım 5: Köprü (JSON Export — ölçümler dahil)
    export_payload(
        &request,
        &outcome,
        verified_proof,
        pub_inputs_export,
        prover_ms,
    );

    let total_ms = t_total.elapsed().as_millis();
    print_summary(total_ms, request.risk_score, level_name, &outcome.rho_prime);
}

// ─────────────────────────────────────────────────────────────────────────────
// Entegrasyon Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_rho_prime_from_entropy() {
        let seed1 = generate_rho_prime_from_entropy(98.52, 1_000_000_000);
        let seed2 = generate_rho_prime_from_entropy(98.52, 1_000_000_001); // +1ns
        let seed3 = generate_rho_prime_from_entropy(50.00, 1_000_000_000); // farklı risk

        // Farklı girişler → farklı seed'ler
        assert_ne!(seed1, seed2, "Zaman farkı seed'i değiştirmeli");
        assert_ne!(seed1, seed3, "Risk skoru farkı seed'i değiştirmeli");

        // BULGU 11 REGRESYONU — aynı giriş, birebir aynı seed.
        //
        // Eski not burada şöyle diyordu: "Gerçek implementation'da process ID
        // kullanıldığından tam deterministik değil." Bu, kanıtın yeniden
        // üretilemez olduğunun kabulüydü. Artık `process::id()` yok ve
        // aşağıdaki eşitlik testi o davranış geri gelirse kırılır.
        let seed1b = generate_rho_prime_from_entropy(98.52, 1_000_000_000);
        assert_eq!(
            seed1, seed1b,
            "Aynı girdi aynı ρ''yü vermeli — süreç kimliği karışmış olabilir"
        );
        assert!(seed1b != [0u8; 32], "Seed sıfır dizisi olmamalı");
    }

    /// BULGU 9 REGRESYONU — ilan edilen güvenlik seviyesi GERÇEKTEN uygulanıyor.
    ///
    /// Bu test sayıyı yorumdan değil, kanıtın kendisinden alır:
    ///   • `STARK_SECURITY_BITS` seviyesinde doğrulama GEÇMELİ,
    ///   • daha yüksek bir seviyede doğrulama KALMALI.
    ///
    /// Böylece sabit gerçekte elde edilen seviyeden yüksek yazılırsa
    /// (README'nin "96" demesi gibi) test kırılır.
    #[test]
    fn test_guvenlik_biti_gercekten_uygulaniyor() {
        let istek = RunRequest {
            risk_score: 95.0,
            tau: 75.0,
            baseline: MlDsaSecurityLevel::Level44,
            user_op_hash: "0xguvenlik".to_string(),
            epoch_ns: 7_000_000_000,
            run_id: "guvenlik".to_string(),
            fresh_entropy: None,
            rho_override: None,
        };

        let outcome = pipeline::run(&istek).unwrap();
        let trace = pipeline::trace_table_for(&outcome).unwrap();

        let last_step = trace.length() - 1;
        let pub_inputs = QAdaptivePublicInputs {
            start_state: [
                trace.get(0, 0),
                trace.get(1, 0),
                trace.get(2, 0),
                trace.get(3, 0),
            ],
            final_state: [
                trace.get(0, last_step),
                trace.get(1, last_step),
                trace.get(2, last_step),
                trace.get(3, last_step),
            ],
        };

        let prover = QAdaptiveProver::new(get_proof_options());
        let proof = prover.prove(trace).unwrap();

        type H = Blake3_256<BaseElement>;

        // İlan edilen seviyede geçmeli.
        let ilan_edilen = AcceptableOptions::MinConjecturedSecurity(air::STARK_SECURITY_BITS);
        assert!(
            winter_verifier::verify::<QAdaptiveAir, H, DefaultRandomCoin<H>, MerkleTree<H>>(
                proof.clone(),
                pub_inputs.clone(),
                &ilan_edilen
            )
            .is_ok(),
            "Kanıt ilan edilen {} bit seviyesinde doğrulanamadı",
            air::STARK_SECURITY_BITS
        );

        // İlan edilenin üstünde KALMALI — aksi hâlde sabit gereğinden düşük.
        let cok_yuksek = AcceptableOptions::MinConjecturedSecurity(air::STARK_SECURITY_BITS + 40);
        assert!(
            winter_verifier::verify::<QAdaptiveAir, H, DefaultRandomCoin<H>, MerkleTree<H>>(
                proof,
                pub_inputs,
                &cok_yuksek
            )
            .is_err(),
            "Kanıt {} bit seviyesinde de geçti — STARK_SECURITY_BITS düşük yazılmış olabilir",
            air::STARK_SECURITY_BITS + 40
        );
    }

    #[test]
    fn test_parse_rho_prime_hex_valid() {
        let hex = "aabbccdd00112233aabbccdd00112233aabbccdd00112233aabbccdd00112233";
        let seed = parse_rho_prime_hex(hex).unwrap();
        assert_eq!(seed[0], 0xAA);
        assert_eq!(seed[1], 0xBB);
        assert_eq!(seed[31], 0x33);
    }

    #[test]
    fn test_parse_rho_prime_hex_invalid_length() {
        let result = parse_rho_prime_hex("aabbcc"); // Çok kısa
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_rho_prime_hex_invalid_chars() {
        let hex = "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ";
        let result = parse_rho_prime_hex(hex);
        assert!(result.is_err());
    }

    /// Uçtan uca: karar → kafes → iz → kanıt → JSON export.
    ///
    /// İz tablosu `pipeline::trace_table_from` ile üretiliyor; yani bu test
    /// aynı zamanda kanıtlanan tablonun gösterilen tablo olduğunu da koşuyor.
    #[test]
    fn test_full_bridge_integration_with_rho_prime() {
        let istek = RunRequest {
            risk_score: 95.0,
            tau: 75.0,
            baseline: MlDsaSecurityLevel::Level44,
            user_op_hash: "0xdeadbeefcafebabe".to_string(),
            epoch_ns: 42_000_000_000,
            run_id: "entegrasyon".to_string(),
            fresh_entropy: None,
            rho_override: None,
        };

        let outcome = pipeline::run(&istek).unwrap();
        assert!(
            outcome.decision.proof_required,
            "risk 95 > τ 75 → kanıt üretilmeli"
        );

        let rho_prime = outcome.rho_prime;
        let options = get_proof_options();
        let trace = pipeline::trace_table_for(&outcome).unwrap();

        let last_step = trace.length() - 1;
        let pub_inputs = QAdaptivePublicInputs {
            start_state: [
                trace.get(0, 0),
                trace.get(1, 0),
                trace.get(2, 0),
                trace.get(3, 0),
            ],
            final_state: [
                trace.get(0, last_step),
                trace.get(1, last_step),
                trace.get(2, last_step),
                trace.get(3, last_step),
            ],
        };

        let prover = QAdaptiveProver::new(options);
        let proof = prover.prove(trace).unwrap();

        let filepath = "test_proof_payload_rho.json";
        let proof_bytes = proof.to_bytes();
        let kayit = outcome.pqc.as_ref().unwrap();

        export_proof_payload(
            outcome.decision.status,
            istek.risk_score,
            &rho_prime,
            outcome.decision.level.name(),
            &proof_bytes,
            &pub_inputs,
            bridge::PayloadExtras {
                tau: istek.tau,
                run_id: istek.run_id.clone(),
                deterministic: outcome.deterministic,
                stark: bridge::StarkMetrics {
                    proof_bytes: proof_bytes.len(),
                    prover_ms: 0.0,
                    conjectured_security_bits: air::STARK_SECURITY_BITS,
                    field: "f128".to_string(),
                    num_queries: air::FRI_NUM_QUERIES,
                    blowup_factor: air::FRI_BLOWUP_FACTOR,
                },
                pqc: Some(bridge::PqcSummary {
                    tier: kayit.level.name().to_string(),
                    public_key_bytes: kayit.public_key_len,
                    secret_key_bytes: kayit.secret_key_len,
                    signature_bytes: kayit.signature_len,
                    public_key_commitment_hex: hex::encode(kayit.public_key_commitment),
                    signature_prefix_hex: kayit.signature_prefix_hex.clone(),
                    signature_verified: kayit.verified,
                    keygen_ms: kayit.keygen_ms,
                    sign_ms: kayit.sign_ms,
                    verify_ms: kayit.verify_ms,
                    tamper_rejected: kayit.tamper_rejected,
                    tamper_ms: kayit.tamper_ms,
                }),
                stages: outcome.stages.clone(),
                lattice: outcome.lattice.clone(),
                calldata: Some(bridge::CalldataRecord::compute(
                    bridge::CalldataRecord::DEFAULT_BATCH_SIZE,
                    kayit.signature_len,
                    proof_bytes.len(),
                )),
            },
            filepath,
        )
        .unwrap();

        let metadata = std::fs::metadata(filepath).unwrap();
        assert!(metadata.len() > 1000, "Payload en az 1KB olmalı");

        // rho_prime_hex alanı mevcut mu?
        let content = std::fs::read_to_string(filepath).unwrap();
        assert!(
            content.contains("rho_prime_hex"),
            "Payload rho_prime_hex içermeli"
        );

        std::fs::remove_file(filepath).unwrap();
    }
}
