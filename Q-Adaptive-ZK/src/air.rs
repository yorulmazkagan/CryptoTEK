// =============================================================================
// Q-ADAPTIVE ZK — AIR Kısıtlama Motoru (src/air.rs)
// =============================================================================
// Aşama 6: MLWE Kuantum Payload Entegrasyonu
//
// Bu modül 4 sütunlu izleme tablosunun (A, s1, s2, t) cebirsel kısıtlamalarını
// (AIR) tanımlar ve t = A * s1 + s2 ilişkisini doğrular.
// =============================================================================

use winterfell::{
    math::{fields::f128::BaseElement, FieldElement, ToElements},
    Air, AirContext, Assertion, BatchingMethod, EvaluationFrame,
    FieldExtension, ProofOptions, TraceInfo, TransitionConstraintDegree,
};

// ─────────────────────────────────────────────────────────────────────────────
// Kanıt Seçenekleri (Güvenlik Parametreleri)
// ─────────────────────────────────────────────────────────────────────────────

pub fn get_proof_options() -> ProofOptions {
    ProofOptions::new(
        28,                         // num_queries
        8,                          // blowup_factor
        16,                         // grinding_factor
        FieldExtension::None,
        8,                          // FRI folding factor
        31,                         // FRI remainder max degree
        BatchingMethod::Linear,
        BatchingMethod::Linear,
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// Kanıt Genel Girişi (Public Inputs)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Clone, Debug)]
pub struct QAdaptivePublicInputs {
    pub start_state: [BaseElement; 4],
    pub final_state: [BaseElement; 4],
}

impl ToElements<BaseElement> for QAdaptivePublicInputs {
    fn to_elements(&self) -> Vec<BaseElement> {
        let mut elements = Vec::with_capacity(8);
        elements.extend_from_slice(&self.start_state);
        elements.extend_from_slice(&self.final_state);
        elements
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// AIR Yapısı (MLWE Kısıtlamaları)
// ─────────────────────────────────────────────────────────────────────────────

pub struct QAdaptiveAir {
    context    : AirContext<BaseElement>,
    pub_inputs : QAdaptivePublicInputs,
}

impl Air for QAdaptiveAir {
    type BaseField    = BaseElement;
    type PublicInputs = QAdaptivePublicInputs;

    fn new(trace_info: TraceInfo, pub_inputs: QAdaptivePublicInputs, options: ProofOptions) -> Self {
        // 4 geçiş kısıtlaması:
        // 0: A_next = A_curr + 1        (Derece 1)
        // 1: s1_next = s1_curr + 2      (Derece 1)
        // 2: s2_next = s2_curr + 3      (Derece 1)
        // 3: t_next = A_next * s1_next + s2_next (Derece 2)
        let degrees = vec![
            TransitionConstraintDegree::new(1),
            TransitionConstraintDegree::new(1),
            TransitionConstraintDegree::new(1),
            TransitionConstraintDegree::new(2),
        ];

        // 8 sınır kısıtlaması (4 başlangıç, 4 bitiş)
        let num_assertions = 8;
        let context = AirContext::new(trace_info, degrees, num_assertions, options);

        Self { context, pub_inputs }
    }

    fn evaluate_transition<E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        frame     : &EvaluationFrame<E>,
        _period   : &[E],
        result    : &mut [E],
    ) {
        let current = frame.current();
        let next    = frame.next();

        // Deterministik tohum evrimi (mock)
        result[0] = next[0] - (current[0] + E::from(1_u8)); // A_next = A_curr + 1
        result[1] = next[1] - (current[1] + E::from(2_u8)); // s1_next = s1_curr + 2
        result[2] = next[2] - (current[2] + E::from(3_u8)); // s2_next = s2_curr + 3

        // MLWE İlişkisi: t = A * s1 + s2
        result[3] = next[3] - (next[0] * next[1] + next[2]); 
    }

    fn get_assertions(&self) -> Vec<Assertion<Self::BaseField>> {
        let last_step = self.trace_length() - 1;
        vec![
            // Başlangıç sınırları
            Assertion::single(0, 0, self.pub_inputs.start_state[0]),
            Assertion::single(1, 0, self.pub_inputs.start_state[1]),
            Assertion::single(2, 0, self.pub_inputs.start_state[2]),
            Assertion::single(3, 0, self.pub_inputs.start_state[3]),
            // Bitiş sınırları
            Assertion::single(0, last_step, self.pub_inputs.final_state[0]),
            Assertion::single(1, last_step, self.pub_inputs.final_state[1]),
            Assertion::single(2, last_step, self.pub_inputs.final_state[2]),
            Assertion::single(3, last_step, self.pub_inputs.final_state[3]),
        ]
    }

    fn context(&self) -> &AirContext<Self::BaseField> {
        &self.context
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Birim Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use winterfell::math::StarkField;

    #[test]
    fn test_public_inputs() {
        let pi = QAdaptivePublicInputs {
            start_state: [BaseElement::new(1), BaseElement::new(2), BaseElement::new(3), BaseElement::new(4)],
            final_state: [BaseElement::new(5), BaseElement::new(6), BaseElement::new(7), BaseElement::new(8)],
        };
        let elems = pi.to_elements();
        assert_eq!(elems.len(), 8);
        assert_eq!(elems[7].as_int(), 8);
    }
}
