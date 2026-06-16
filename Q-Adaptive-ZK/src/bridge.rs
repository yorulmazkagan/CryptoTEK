// =============================================================================
// Q-ADAPTIVE ZK — Entegrasyon Köprüsü (src/bridge.rs)
// =============================================================================
// Aşama 7: AI Guardian (Aşama 3/4) ve STARK (Aşama 5/6) sistemlerini birbirine
// bağlayarak Solidity akıllı sözleşmesinin tüketebileceği standart JSON çıktısı
// üretir.
// =============================================================================

use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::Write;
use winterfell::math::StarkField;
use crate::air::QAdaptivePublicInputs;

/// Solidity `validateUserOp` için gerekli olan sınır koşulları (Public Inputs).
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

/// Akıllı sözleşme veya Web3 istemcisine gönderilecek root JSON objesi.
#[derive(Serialize, Deserialize, Debug)]
pub struct ProofPayload {
    pub status: String,
    pub ai_risk_score: f64,
    pub pqc_armor_tier: String,
    pub stark_proof_bytes_hex: String,
    pub air_verification_metadata: AirVerificationMetadata,
}

/// STARK kanıtını ve durum verisini standart JSON olarak dışa aktarır.
pub fn export_proof_payload(
    status: &str,
    risk_score: f64,
    proof_bytes: &[u8],
    pub_inputs: &QAdaptivePublicInputs,
    filepath: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let hex_proof = hex::encode(proof_bytes);

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
        pqc_armor_tier: "ML-DSA-87 (Dilithium-5)".to_string(),
        stark_proof_bytes_hex: hex_proof,
        air_verification_metadata: metadata,
    };

    let json_data = serde_json::to_string_pretty(&payload)?;
    let mut file = File::create(filepath)?;
    file.write_all(json_data.as_bytes())?;

    Ok(())
}
