// =============================================================================
// Q-ADAPTIVE ZK — Yürütme İzi Tablosu (src/trace.rs)
// =============================================================================
// Aşama 6: MLWE (Module Learning With Errors) Kuantum Payload Entegrasyonu
//
// Bu modül STARK kanıt sisteminin temelini oluşturan 4 sütunlu izleme
// tablosunu tanımlar:
//
//   ┌────────┬──────────────┬──────────────┬──────────────┬──────────────┐
//   │  Adım  │ Sütun 0 (A)  │ Sütun 1 (s1) │ Sütun 2 (s2) │ Sütun 3 (t)  │
//   ├────────┼──────────────┼──────────────┼──────────────┼──────────────┤
//   │   0    │      A_0     │     s1_0     │     s2_0     │     t_0      │
//   │   1    │      A_1     │     s1_1     │     s2_1     │     t_1      │
//   │  ...   │      ...     │      ...     │      ...     │     ...      │
//   └────────┴──────────────┴──────────────┴──────────────┴──────────────┘
//
// MLWE İlişkisi: t_i = A_i * s1_i + s2_i
// =============================================================================

use winterfell::math::{fields::f128::BaseElement, FieldElement, StarkField};

// ─────────────────────────────────────────────────────────────────────────────
// İz Sabitleri
// ─────────────────────────────────────────────────────────────────────────────

/// Prototipin kullandığı izleme adım sayısı (2^N olmalı).
pub const TRACE_LENGTH: usize = 8;

/// İzleme tablosundaki sütun sayısı (A, s1, s2, t).
pub const TRACE_WIDTH: usize = 4;

// ─────────────────────────────────────────────────────────────────────────────
// Dilithium-5 Enjeksiyon Verisi (Payload)
// ─────────────────────────────────────────────────────────────────────────────

/// Dilithium-5 imza bileşenlerini STARK izine dönüştürmek için kullanılan yapı.
#[derive(Clone, Debug)]
pub struct Dilithium5InjectionPayload {
    pub seed_a: u128,
    pub seed_s1: u128,
    pub seed_s2: u128,
    pub armor_level: u8,
    pub timelock_deadline: u64,
}

impl Dilithium5InjectionPayload {
    pub fn new(seed_a: u128, seed_s1: u128, seed_s2: u128) -> Self {
        Self {
            seed_a,
            seed_s1,
            seed_s2,
            armor_level: 1,           // Heavy Armor
            timelock_deadline: 1893456000, // Varsayılan timestamp
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// İzleme Tablosu Görselleştirici (Debug Amaçlı)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug)]
pub struct QAdaptiveTrace {
    data      : Vec<Vec<BaseElement>>,
    trace_len : usize,
}

impl QAdaptiveTrace {
    /// Payload kullanarak 4 sütunlu MLWE yürütme izi oluşturur.
    pub fn new(payload: &Dilithium5InjectionPayload, length: usize) -> Self {
        assert!(
            length.is_power_of_two() && length >= 8,
            "İz uzunluğu 2'nin kuvveti olmalı ve >= 8 olmalıdır. Alındı: {length}"
        );

        let mut col0 = Vec::with_capacity(length); // A
        let mut col1 = Vec::with_capacity(length); // s1
        let mut col2 = Vec::with_capacity(length); // s2
        let mut col3 = Vec::with_capacity(length); // t

        let mut curr_a  = BaseElement::new(payload.seed_a);
        let mut curr_s1 = BaseElement::new(payload.seed_s1);
        let mut curr_s2 = BaseElement::new(payload.seed_s2);
        // t = A * s1 + s2
        let mut curr_t  = curr_a * curr_s1 + curr_s2;

        col0.push(curr_a);
        col1.push(curr_s1);
        col2.push(curr_s2);
        col3.push(curr_t);

        for _ in 1..length {
            // Deterministik simülasyon adımları (gelecekte PRNG/Hash olacak)
            curr_a  = curr_a + BaseElement::new(1);
            curr_s1 = curr_s1 + BaseElement::new(2);
            curr_s2 = curr_s2 + BaseElement::new(3);
            
            // Gerçek MLWE bileşeni
            curr_t  = curr_a * curr_s1 + curr_s2;

            col0.push(curr_a);
            col1.push(curr_s1);
            col2.push(curr_s2);
            col3.push(curr_t);
        }

        Self {
            data: vec![col0, col1, col2, col3],
            trace_len: length,
        }
    }

    pub fn get(&self, step: usize, col: usize) -> BaseElement {
        self.data[col][step]
    }

    pub fn final_state(&self) -> [BaseElement; 4] {
        let last = self.trace_len - 1;
        [
            self.get(last, 0),
            self.get(last, 1),
            self.get(last, 2),
            self.get(last, 3),
        ]
    }

    pub fn print_table(&self) {
        println!("  ┌──────┬──────────────┬──────────────┬──────────────┬──────────────┐");
        println!("  │ Adım │ Sütun 0 (A)  │ Sütun 1 (s1) │ Sütun 2 (s2) │ Sütun 3 (t)  │");
        println!("  ├──────┼──────────────┼──────────────┼──────────────┼──────────────┤");

        let display_rows = self.trace_len.min(8);
        for step in 0..display_rows {
            let a  = self.get(step, 0).as_int();
            let s1 = self.get(step, 1).as_int();
            let s2 = self.get(step, 2).as_int();
            let t  = self.get(step, 3).as_int();
            println!("  │ {:>4} │ {:>12} │ {:>12} │ {:>12} │ {:>12} │", step, a, s1, s2, t);
        }
        if self.trace_len > 8 {
            println!("  │  ... │          ... │          ... │          ... │          ... │");
        }
        println!("  └──────┴──────────────┴──────────────┴──────────────┴──────────────┘");
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
    fn test_mlwe_trace_generation() {
        let payload = Dilithium5InjectionPayload::new(10, 5, 2);
        let trace = QAdaptiveTrace::new(&payload, 8);
        
        // Adım 0
        assert_eq!(trace.get(0, 0).as_int(), 10);
        assert_eq!(trace.get(0, 1).as_int(), 5);
        assert_eq!(trace.get(0, 2).as_int(), 2);
        assert_eq!(trace.get(0, 3).as_int(), 10 * 5 + 2); // 52
        
        // Adım 1
        assert_eq!(trace.get(1, 0).as_int(), 11);
        assert_eq!(trace.get(1, 1).as_int(), 7);
        assert_eq!(trace.get(1, 2).as_int(), 5);
        assert_eq!(trace.get(1, 3).as_int(), 11 * 7 + 5); // 82
    }
}
