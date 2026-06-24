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

use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::Write;
use winterfell::math::StarkField;
use crate::air::QAdaptivePublicInputs;

/// Solidity `validateUserOp` için gerekli olan sınır koşulları.
#[derive(Serialize, Deserialize, Debug)]
pub struct AirVerificationMetadata {
    pub start_a : String,
    pub start_s1: String,
    pub start_s2: String,
    pub start_t : String,
    pub final_a : String,
    pub final_s1: String,
    pub final_s2: String,
    pub final_t : String,
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
    pub status                   : String,
    pub ai_risk_score            : f64,
    pub pqc_armor_tier           : String,
    /// ρ' (rho-prime) seed'inin 64 karakterlik hex kodlaması.
    /// AI rotasyon kararının kriptografik kanıtı.
    pub rho_prime_hex            : String,
    pub stark_proof_bytes_hex    : String,
    pub air_verification_metadata: AirVerificationMetadata,
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
pub fn export_proof_payload(
    status      : &str,
    risk_score  : f64,
    rho_prime   : &[u8; 32],
    armor_tier  : &str,
    proof_bytes : &[u8],
    pub_inputs  : &QAdaptivePublicInputs,
    filepath    : &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let hex_proof     = hex::encode(proof_bytes);
    let rho_prime_hex = hex::encode(rho_prime);

    let metadata = AirVerificationMetadata {
        start_a : pub_inputs.start_state[0].as_int().to_string(),
        start_s1: pub_inputs.start_state[1].as_int().to_string(),
        start_s2: pub_inputs.start_state[2].as_int().to_string(),
        start_t : pub_inputs.start_state[3].as_int().to_string(),
        final_a : pub_inputs.final_state[0].as_int().to_string(),
        final_s1: pub_inputs.final_state[1].as_int().to_string(),
        final_s2: pub_inputs.final_state[2].as_int().to_string(),
        final_t : pub_inputs.final_state[3].as_int().to_string(),
    };

    let payload = ProofPayload {
        status                    : status.to_string(),
        ai_risk_score             : risk_score,
        pqc_armor_tier            : armor_tier.to_string(),
        rho_prime_hex,
        stark_proof_bytes_hex     : hex_proof,
        air_verification_metadata : metadata,
    };

    let json_data = serde_json::to_string_pretty(&payload)?;
    let mut file  = File::create(filepath)?;
    file.write_all(json_data.as_bytes())?;

    Ok(())
}
