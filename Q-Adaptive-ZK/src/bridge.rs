// =============================================================================
// Q-ADAPTIVE ZK — Entegrasyon Köprüsü (src/bridge.rs)
// =============================================================================
// Production-Grade Refactor: rho_prime_hex alanı eklendi.
//
// AI Guardian (Python) → Rust ZK-STARK → Solidity akıllı sözleşme köprüsü.
// JSON payload artık proof + AIR boundary + rho_prime_hex içerir.
//
// api.py bu dosyayı okur ve:
//   1. air_verification_metadata → EVM sınır koşulları için
//   2. stark_proof_bytes_hex    → Solidity validateUserOp için
//   3. rho_prime_hex            → Rotasyon doğrulaması + updateQuantumArmor için
// =============================================================================

use crate::air::QAdaptivePublicInputs;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::Write;
use winterfell::math::StarkField;

/// Solidity `validateUserOp` için gerekli olan sınır koşulları.
#[derive(Serialize, Deserialize, Debug)]
pub struct AirVerificationMetadata {
    pub start_a: String,
    pub start_s1: String,
    pub start_s2: String,
    pub start_t: String,
    pub final_a: String,
    pub final_s1: String,
    pub final_s2: String,
    pub final_t: String,
}

// ─────────────────────────────────────────────────────────────────────────────
// Calldata Tasarrufu — TEK TANIM
// ─────────────────────────────────────────────────────────────────────────────

/// Bir STARK kanıtının, aynı işlemleri tek tek imzalamaya kıyasla
/// calldata'da sağladığı tasarruf.
///
/// **Neden bu yapı var:** Aynı "%97,98" sayısı daha önce İKİ FARKLI FORMÜLLE
/// üretiliyordu:
///
///   (a) `api.py`  : `1 − kanıt / (4608 + kanıt)` — `raw_sig_bytes = 4608.0`
///                   diye uydurulmuş bir tek-imza tabanı üzerinden.
///   (b) raporlar  : 50 işlemlik parti (229.750 B → 4.640 B) üzerinden.
///
/// İkisi tesadüfen birbirine yakın sayılar veriyordu, ama "hangisi doğru?"
/// sorusunun cevabı yoktu. Tanım artık tek: parti başına kanıt, partideki
/// imzaların toplamına oranlanır. Formül, girdileriyle birlikte payload'a
/// yazılır ki okuyan kişi yeniden hesaplayabilsin.
///
/// **Dürüst ek:** ECDSA bu karşılaştırmada bizi yener. 50 ECDSA imzası
/// 50 × 65 = 3.250 bayttır, yani tek bir STARK kanıtından küçüktür. Takas
/// post-kuantum güvenliğidir, calldata değil. Bu da payload'a yazılır.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct CalldataRecord {
    /// Partideki işlem sayısı.
    pub batch_size: usize,
    /// Bu zırh kademesinde tek bir ML-DSA imzasının boyutu (bayt).
    pub single_signature_bytes: usize,
    /// Parti tek tek imzalansaydı taşınacak toplam bayt.
    pub naive_batch_bytes: usize,
    /// Partinin yerine geçen tek STARK kanıtının boyutu (bayt).
    pub stark_proof_bytes: usize,
    /// Tasarruf yüzdesi.
    pub savings_pct: f64,
    /// Aynı partinin ECDSA ile maliyeti — karşılaştırma dürüstlüğü için.
    pub ecdsa_batch_bytes: usize,
    /// STARK kanıtı ECDSA partisinden küçük mü? (Beklenen yanıt: hayır.)
    pub beats_ecdsa: bool,
    /// Formülün metinsel hâli — sayı yeniden hesaplanabilir olsun diye.
    pub formula: String,
}

impl CalldataRecord {
    /// Raporlarda kullanılan standart parti boyutu.
    pub const DEFAULT_BATCH_SIZE: usize = 50;

    /// Tek bir ECDSA (secp256k1) imzasının calldata boyutu: r ‖ s ‖ v.
    pub const ECDSA_SIGNATURE_BYTES: usize = 65;

    /// Tasarrufu tek formülden hesaplar.
    ///
    /// ```text
    ///   tasarruf% = (1 − STARK_kanıtı / (parti × ML-DSA_imza_boyutu)) × 100
    /// ```
    pub fn compute(
        batch_size: usize,
        single_signature_bytes: usize,
        stark_proof_bytes: usize,
    ) -> Self {
        let naive_batch_bytes = batch_size * single_signature_bytes;
        let ecdsa_batch_bytes = batch_size * Self::ECDSA_SIGNATURE_BYTES;

        let savings_pct = if naive_batch_bytes > 0 {
            (1.0 - (stark_proof_bytes as f64 / naive_batch_bytes as f64)) * 100.0
        } else {
            0.0
        };

        Self {
            batch_size,
            single_signature_bytes,
            naive_batch_bytes,
            stark_proof_bytes,
            savings_pct,
            ecdsa_batch_bytes,
            beats_ecdsa: stark_proof_bytes < ecdsa_batch_bytes,
            formula: format!(
                "(1 - {} / ({} x {})) * 100",
                stark_proof_bytes, batch_size, single_signature_bytes
            ),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Ölçülmüş Kriptografik Özet
// ─────────────────────────────────────────────────────────────────────────────

/// Bu koşuda gerçekten üretilmiş ML-DSA anahtar/imza ölçümleri.
///
/// Her alan `fips204`ten ölçülür; hiçbiri belgeden kopyalanmaz.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct PqcSummary {
    pub tier: String,
    pub public_key_bytes: usize,
    pub secret_key_bytes: usize,
    pub signature_bytes: usize,
    pub public_key_commitment_hex: String,
    pub signature_prefix_hex: String,
    pub signature_verified: bool,
}

/// Bu koşuda ölçülmüş STARK metrikleri.
///
/// Prover süresi ve kanıt boyutu **her koşuda yeniden ölçülür**. Raporlarda
/// sabitlenmiş "18.52 ms" / "3.85 KB" değerleri tek bir makinedeki tek bir
/// koşudan geliyordu; kanıt boyutu zırh kademesine, süre de donanıma göre
/// değişir.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct StarkMetrics {
    pub proof_bytes: usize,
    pub prover_ms: f64,
    pub conjectured_security_bits: u32,
    pub field: String,
    pub num_queries: usize,
    pub blowup_factor: usize,
}

/// Akıllı sözleşme veya Web3 istemcisine gönderilecek root JSON objesi.
///
/// Yeni alan: `rho_prime_hex`
///   - 32-byte kriptografik seed'in hex kodlaması
///   - API katmanı bunu Solidity'deki `updateQuantumArmor(newTier, newPublicKey)`
///     çağrısı için kullanır
///   - keccak256(rho_prime_hex) → yeni quantumPublicKey taahhüdü hesaplanır
#[derive(Serialize, Deserialize, Debug)]
pub struct ProofPayload {
    pub status: String,
    pub ai_risk_score: f64,
    /// Bu koşuda uygulanan dinamik eşik τ(t).
    /// Kararın hangi eşiğe göre verildiği payload'dan okunabilmeli.
    pub tau: f64,
    pub pqc_armor_tier: String,
    /// ρ' (rho-prime) seed'inin 64 karakterlik hex kodlaması.
    /// AI rotasyon kararının kriptografik kanıtı.
    pub rho_prime_hex: String,
    /// Koşu tam deterministik miydi? `--fresh-entropy` verildiyse `false`.
    /// Jüri koşuyu tekrarlayabilmek için bu alana bakar.
    pub deterministic_run: bool,
    /// Koşu kimliği — log ↔ payload eşleştirmesi için.
    pub run_id: String,
    pub stark_proof_bytes_hex: String,
    /// Ölçülmüş STARK metrikleri (sabit değil).
    pub stark: StarkMetrics,
    /// Ölçülmüş ML-DSA anahtar/imza bilgileri.
    pub pqc: Option<PqcSummary>,
    /// Calldata tasarrufu — tek tanım, girdileriyle birlikte.
    pub calldata: Option<CalldataRecord>,
    pub air_verification_metadata: AirVerificationMetadata,
}

/// `export_proof_payload`'a geçirilen ölçüm paketi.
///
/// Ayrı bir yapı olarak tutuluyor ki yeni bir ölçüm eklendiğinde fonksiyon
/// imzası her seferinde uzamasın.
pub struct PayloadExtras {
    pub tau: f64,
    pub run_id: String,
    pub deterministic: bool,
    pub stark: StarkMetrics,
    pub pqc: Option<PqcSummary>,
    pub calldata: Option<CalldataRecord>,
}

/// STARK kanıtını ve durum verisini standart JSON olarak dışa aktarır.
///
/// # Arguments
/// * `status`        - "PANIC_MODE_ACTIVATED" veya "NORMAL"
/// * `risk_score`    - AI risk yüzdesi (0.0 - 100.0)
/// * `rho_prime`     - 32-byte kriptografik rotasyon seed'i
/// * `armor_tier`    - Güvenlik seviyesi adı (ör. "ML-DSA-87 (Dilithium-5)")
/// * `proof_bytes`   - Ham STARK kanıt baytları
/// * `pub_inputs`    - STARK AIR başlangıç/bitiş durumları
/// * `filepath`      - Çıktı JSON dosyası yolu
///
/// # Not
///
/// Sekiz argüman clippy'nin yedi sınırını aşıyor. Ölçümler zaten
/// `PayloadExtras` altında gruplandı; kalanlar (durum, risk, ρ', kademe,
/// kanıt, genel girdiler, dosya yolu) birbirinden bağımsız alanlar ve bir
/// yapıya daha sarmak okunurluğu artırmıyor — bu bir dışa aktarma sınırı.
#[allow(clippy::too_many_arguments)]
pub fn export_proof_payload(
    status: &str,
    risk_score: f64,
    rho_prime: &[u8; 32],
    armor_tier: &str,
    proof_bytes: &[u8],
    pub_inputs: &QAdaptivePublicInputs,
    extras: PayloadExtras,
    filepath: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let hex_proof = hex::encode(proof_bytes);
    let rho_prime_hex = hex::encode(rho_prime);

    let metadata = AirVerificationMetadata {
        start_a: pub_inputs.start_state[0].as_int().to_string(),
        start_s1: pub_inputs.start_state[1].as_int().to_string(),
        start_s2: pub_inputs.start_state[2].as_int().to_string(),
        start_t: pub_inputs.start_state[3].as_int().to_string(),
        final_a: pub_inputs.final_state[0].as_int().to_string(),
        final_s1: pub_inputs.final_state[1].as_int().to_string(),
        final_s2: pub_inputs.final_state[2].as_int().to_string(),
        final_t: pub_inputs.final_state[3].as_int().to_string(),
    };

    let payload = ProofPayload {
        status: status.to_string(),
        ai_risk_score: risk_score,
        tau: extras.tau,
        pqc_armor_tier: armor_tier.to_string(),
        rho_prime_hex,
        deterministic_run: extras.deterministic,
        run_id: extras.run_id,
        stark_proof_bytes_hex: hex_proof,
        stark: extras.stark,
        pqc: extras.pqc,
        calldata: extras.calldata,
        air_verification_metadata: metadata,
    };

    let json_data = serde_json::to_string_pretty(&payload)?;
    let mut file = File::create(filepath)?;
    file.write_all(json_data.as_bytes())?;

    Ok(())
}

// ─────────────────────────────────────────────────────────────────────────────
// Birim Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// BULGU 13 REGRESYONU — calldata tanımı tek ve yeniden hesaplanabilir.
    ///
    /// Eski `api.py` uydurma bir `raw_sig_bytes = 4608.0` tabanı kullanıyordu.
    /// Bu test, tabanın gerçek ML-DSA imza boyutu × parti olduğunu ve
    /// yayımlanan yüzdenin formülden yeniden üretilebildiğini sabitler.
    #[test]
    fn calldata_tanimi_tek_ve_yeniden_hesaplanabilir() {
        // ML-DSA-87: 4.627 baytlık imza, 50'lik parti, ~4 KB kanıt.
        let kayit = CalldataRecord::compute(50, 4_627, 4_096);

        assert_eq!(kayit.naive_batch_bytes, 231_350);
        assert_eq!(kayit.formula, "(1 - 4096 / (50 x 4627)) * 100");

        // Yüzde formülden yeniden hesaplanabilmeli.
        let yeniden = (1.0 - 4_096.0 / 231_350.0) * 100.0;
        assert!((kayit.savings_pct - yeniden).abs() < 1e-9);
        assert!(kayit.savings_pct > 98.0 && kayit.savings_pct < 98.5);

        // Uydurma 4608 tabanı geri gelirse taban bu değere düşerdi.
        assert_ne!(
            kayit.naive_batch_bytes, 4_608,
            "raw_sig_bytes = 4608 tabanı geri gelmiş olabilir"
        );
    }

    /// Taban zırh kademesiyle birlikte değişiyor mu?
    #[test]
    fn calldata_tabani_kademeye_bagli() {
        let k44 = CalldataRecord::compute(50, 2_420, 4_096);
        let k87 = CalldataRecord::compute(50, 4_627, 4_096);

        assert!(
            k44.naive_batch_bytes < k87.naive_batch_bytes,
            "Taban kademeye göre değişmeli"
        );
        assert!(
            k44.savings_pct < k87.savings_pct,
            "Daha büyük imzalar daha yüksek tasarruf oranı verir"
        );
    }

    /// Dürüstlük kontrolü — ECDSA bu karşılaştırmada bizi yeniyor.
    ///
    /// "ECDSA'dan daha az calldata" demek YANLIŞ olurdu; bu test o iddianın
    /// sessizce doğru sayılmasını engeller.
    #[test]
    fn ecdsa_karsilastirmasi_durust() {
        let kayit = CalldataRecord::compute(50, 4_627, 4_096);

        assert_eq!(kayit.ecdsa_batch_bytes, 3_250);
        assert!(
            !kayit.beats_ecdsa,
            "50 ECDSA imzası 3.250 bayt — STARK kanıtından küçük. \
             'ECDSA'dan az calldata' iddiası kurulamaz."
        );
    }

    #[test]
    fn sifir_partide_bolme_hatasi_yok() {
        let kayit = CalldataRecord::compute(0, 4_627, 4_096);
        assert_eq!(kayit.savings_pct, 0.0);
    }
}
