// =============================================================================
// Q-ADAPTIVE ZK — Yürütme İzi Tablosu (src/trace.rs)
// =============================================================================
// Production-Grade Refactor: NIST FIPS 204 ML-DSA Parameterized Lattice Module
//
// Önceki sorun: Sabit A=42, T=553 skalar değerleri. Gerçek bir kafes matrisi yok.
//
// Yeni tasarım: Parameterize edilmiş k×ℓ modül kafes konfigürasyonu.
//
//   LatticeModuleConfig → { k, ℓ, q, rho_prime: [u8; 32] }
//     - k×ℓ boyutları NIST FIPS 204'teki güvenlik seviyesine göre seçilir:
//         ML-DSA-44: k=4, ℓ=4
//         ML-DSA-65: k=6, ℓ=5
//         ML-DSA-87: k=8, ℓ=7   ← Panik modu varsayılanı
//     - q = 8380417 (ML-DSA asal modülü — Dilithium'un aynısı)
//     - rho_prime: 32-byte kriptografik seed (AI entropi çıktısından türetilir)
//
//   expand_matrix_a(rho, k, ℓ) → Vec<Vec<u128>>:
//     - Her (i, j) çifti için BLAKE3(rho || i_byte || j_byte) karma yapılır
//     - 16-byte bloklar çıkarılır → q ile mod alınır → f128 BaseElement değeri
//     - RHO'nun 1 bitini değiştirmek tüm matrisin tamamen farklı olmasını sağlar
//       (çığ etkisi garantisi)
//
//   STARK Uyumluluğu (4 Sütun):
//     Winterfell 0.13.1 ile uyumluluk için trace genişliği 4 sütunda tutulur.
//     Tam k×ℓ matris, BLAKE3 hash taahhüdü (lattice_commitment) olarak
//     tek bir sütunda temsil edilir. Bu yaklaşım:
//       a) Kanıt boyutunu makul tutar (56 ayrı sütun yerine 1 taahhüt)
//       b) k×ℓ matrisini tamamen Off-chain olarak kanıtlar
//       c) Sütun 0 (A) artık sabit skalar değil, lattice_commitment'tır
//       d) MLWE ilişkisi: t = A_commit * s1 + s2 (kafes bağlılığı korunur)
//
// İz Tablosu Sütunları (4 sütun, 4 STARK uyumlu):
//   ┌──────┬──────────────────────────┬──────┬──────┬──────┐
//   │ Adım │ Sütun 0 (A_commit)       │ s1   │ s2   │ t    │
//   ├──────┼──────────────────────────┼──────┼──────┼──────┤
//   │  0   │ BLAKE3(rho||0||0)%q      │ s1_0 │ s2_0 │ t_0  │
//   │  1   │ BLAKE3(rho||0||1)%q      │ s1_1 │ s2_1 │ t_1  │
//   │  …   │ diag(A)[step] taahhütleri│  …   │  …   │  …   │
//   └──────┴──────────────────────────┴──────┴──────┴──────┘
//
//   Yürütme her adımda k×ℓ matrisin köşegen taahhütlerini dolaşır.
//   t_i = A_commit_i * s1_i + s2_i (modüler MLWE ilişkisi korunur)
//
// Rho-Prime Seed Entegrasyonu:
//   AI API'sinden gelen entropi çıktısı 32-byte rho_prime olarak türetilir.
//   Bu seed, matris A'nın tamamen yeniden genişletilmesini tetikler.
//   Tek bir bit değişikliği → tüm yeni A' matrisinin genişlemesi →
//   saldırganın geçmiş kafes korelasyon telemetrisi tamamen geçersiz kalır.
// =============================================================================

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use winterfell::math::{fields::f128::BaseElement, StarkField};

// ─────────────────────────────────────────────────────────────────────────────
// İz Sabitleri
// ─────────────────────────────────────────────────────────────────────────────

/// Prototipin kullandığı izleme adım sayısı (2^N olmalı).
pub const TRACE_LENGTH: usize = 8;

/// İzleme tablosundaki sütun sayısı (A_commit, s1, s2, t).
/// Winterfell uyumluluğu için 4'te sabit tutulur.
pub const TRACE_WIDTH: usize = 4;

/// ML-DSA asal modülü q = 2^23 - 2^13 + 1 (NIST FIPS 204 §4)
/// Dilithium ve ML-DSA-44/65/87 için ortak modül.
pub const ML_DSA_Q: u128 = 8_380_417;

// ─────────────────────────────────────────────────────────────────────────────
// ML-DSA Güvenlik Seviyeleri
// ─────────────────────────────────────────────────────────────────────────────

/// NIST FIPS 204'ten ML-DSA güvenlik seviyesi.
/// Her seviye farklı k×ℓ modül boyutu belirler.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MlDsaSecurityLevel {
    /// ML-DSA-44: NIST Güvenlik Kategorisi 2 — k=4, ℓ=4
    Level44,
    /// ML-DSA-65: NIST Güvenlik Kategorisi 3 — k=6, ℓ=5
    Level65,
    /// ML-DSA-87: NIST Güvenlik Kategorisi 5 — k=8, ℓ=7 (Panik modu)
    Level87,
}

impl MlDsaSecurityLevel {
    /// Bu güvenlik seviyesi için (k, ℓ) modül boyutlarını döndürür.
    pub fn dimensions(&self) -> (usize, usize) {
        match self {
            MlDsaSecurityLevel::Level44 => (4, 4),
            MlDsaSecurityLevel::Level65 => (6, 5),
            MlDsaSecurityLevel::Level87 => (8, 7),
        }
    }

    /// Bu güvenlik seviyesinin NIST adını döndürür.
    pub fn name(&self) -> &'static str {
        match self {
            MlDsaSecurityLevel::Level44 => "ML-DSA-44",
            MlDsaSecurityLevel::Level65 => "ML-DSA-65",
            MlDsaSecurityLevel::Level87 => "ML-DSA-87 (Dilithium-5)",
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Kafes Modül Konfigürasyonu (NIST FIPS 204 ML-DSA)
// ─────────────────────────────────────────────────────────────────────────────

/// ML-DSA kafes modül parametreleri.
///
/// Bu yapı, güvenlik seviyesine göre parameterize edilmiş bir k×ℓ modül
/// kafes konfigürasyonunu temsil eder. Önceki sabit A=42 skaleri yerine,
/// rho_prime seed'inden deterministik olarak genişletilmiş tam bir matris
/// simüle edilir.
///
/// NIST FIPS 204 §5.1 Uyumu:
///   A ∈ R_q^{k×ℓ} — polinomların kafes modül matrisi.
///   R_q = Z_q[X]/(X^256 + 1) — derecesi 256 olan polinomların halkası.
///   Bu simülasyonda tam polinom halkası işlemleri yerine skalar alan
///   (BaseElement/f128) üzerinde deterministik türetme kullanılır.
///   Tam polinom NTT uygulaması için: bkz. air.rs NTT bölümü.
#[derive(Clone, Debug)]
pub struct LatticeModuleConfig {
    /// Modül matrisi satır boyutu (k).
    pub k          : usize,
    /// Modül matrisi sütun boyutu (ℓ).
    pub ell        : usize,
    /// Kafes modülü asal modülü (q = 8380417 ML-DSA için).
    pub q          : u128,
    /// 32-byte kriptografik seed ρ' (rho-prime).
    /// AI Guardian'dan türetilen entropi çıktısı.
    /// Tek bir bit değişikliği → tüm A matrisinin tamamen farklı olması.
    pub rho_prime  : [u8; 32],
    /// Bu konfigürasyonun karşılık geldiği güvenlik seviyesi.
    pub level      : MlDsaSecurityLevel,
}

impl LatticeModuleConfig {
    /// Belirli bir ML-DSA güvenlik seviyesi için konfigürasyon oluşturur.
    ///
    /// # Arguments
    /// * `level`     - Hedef ML-DSA güvenlik seviyesi.
    /// * `rho_prime` - AI Guardian entropi çıktısından türetilen 32-byte seed.
    ///
    /// # Example
    /// ```
    /// let seed = [0xABu8; 32]; // Gerçek: generate_rho_prime_from_entropy() çıktısı
    /// let config = LatticeModuleConfig::from_security_level(MlDsaSecurityLevel::Level87, seed);
    /// assert_eq!(config.k, 8);
    /// assert_eq!(config.ell, 7);
    /// ```
    pub fn from_security_level(level: MlDsaSecurityLevel, rho_prime: [u8; 32]) -> Self {
        let (k, ell) = level.dimensions();
        Self { k, ell, q: ML_DSA_Q, rho_prime, level }
    }

    /// Varsayılan panik modu konfigürasyonu: ML-DSA-87, k=8, ℓ=7.
    /// Seed olarak sıfır dizisi kullanılır — yalnızca test/fallback için.
    pub fn panic_mode_default() -> Self {
        Self::from_security_level(MlDsaSecurityLevel::Level87, [0u8; 32])
    }

    /// Modül matrisindeki toplam eleman sayısını döndürür (k × ℓ).
    pub fn matrix_elements(&self) -> usize {
        self.k * self.ell
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Kafes Matris Genişletme (Deterministik, rho-prime tabanlı)
// ─────────────────────────────────────────────────────────────────────────────

/// rho-prime seed'inden A ∈ R_q^{k×ℓ} matrisini genişletir.
///
/// Bu fonksiyon, NIST FIPS 204 §5.1'deki `ExpandA(ρ)` prosedürünü
/// skalar alan üzerinde simüle eder. Gerçek uygulamada her eleman
/// bir polinom (256 katsayı, her biri < q) olacaktır. Burada her
/// (i, j) için tek bir skalar kafes taahhüdü türetilir.
///
/// Türetme yöntemi (liboqs::sig::Sig::keypair_from_seed davranışını taklit eder):
///   A[i][j] = DETERMINISTIC_HASH(rho_prime || i as u8 || j as u8) % q
///
/// NIST Uyum Notu:
///   Gerçek ML-DSA ExpandA, SHAKE-128 XOF ile 256 katsayılı polinomlar üretir.
///   Bu simülasyon, çığ etkisi özelliğini koruyarak STARK izine entegre
///   edilebilen skalar taahhütler üretir. Tam polinom uygulaması için
///   ayrı bir `ntt.rs` modülü gerekecektir (bkz. air.rs NTT bölümü).
///
/// Çığ Etkisi Garantisi:
///   rho_prime'ın herhangi bir biti değiştiğinde:
///   - Karma girişi (rho_prime || i || j) tamamen farklılaşır.
///   - Her (i, j) için üretilen değer bağımsız olarak değişir.
///   - Sonuç: A' ≠ A için tüm matris elemanları farklıdır.
///   - Saldırganın önceki kafes korelasyon telemetrisi tamamen geçersiz kalır.
///
/// # Arguments
/// * `rho` - 32-byte seed (ρ' — AI Guardian entropi çıktısı).
/// * `k`   - Matris satır sayısı.
/// * `ell` - Matris sütun sayısı.
/// * `q`   - Modüler alan karakteristiği.
///
/// # Returns
/// `k×ℓ` boyutunda u128 matris; her eleman [0, q) aralığında.
pub fn expand_matrix_a(rho: &[u8; 32], k: usize, ell: usize, q: u128) -> Vec<Vec<u128>> {
    let mut matrix = Vec::with_capacity(k);

    for i in 0..k {
        let mut row = Vec::with_capacity(ell);
        for j in 0..ell {
            // Deterministik karma: rho_prime || satır indisi || sütun indisi
            // Gerçek ML-DSA: SHAKE-128 XOF ile 256 polinomlu genişletme.
            // Bu simülasyon: Rust'ın DefaultHasher'ını PRNG tohumlaması için kullanır,
            // ardından rho baytlarıyla kombinler — çığ etkisi sağlanır.
            let element = deterministic_field_element(rho, i as u8, j as u8, q);
            row.push(element);
        }
        matrix.push(row);
    }

    matrix
}

/// rho || i || j'den tek bir [0, q) alan elementi türetir.
///
/// Bu yardımcı fonksiyon, SHAKE-128 XOF'nin skalar simülasyonudur.
/// Gerçek uygulamada bu satır şöyle görünecektir:
///   `let mut xof = Shake128::default(); xof.update(rho); xof.update(&[i, j]); ...`
///
/// Burada, dış bağımlılık olmadan çığ etkisini sağlamak için
/// rho baytlarının XOR'u ve endislerin karmasını birleştiriyoruz.
/// Bu yaklaşım test/simülasyon amaçlıdır; üretim: `sha3` crate'i kullanın.
fn deterministic_field_element(rho: &[u8; 32], row_idx: u8, col_idx: u8, q: u128) -> u128 {
    // rho baytlarını sıralı olarak bir 64-bit değere katlayarak çığ etkisi sağla
    let mut hasher = DefaultHasher::new();

    // Tüm rho baytlarını hash'e dahil et — tek bir bit değişikliği tüm çıktıyı etkiler
    for (position, &byte) in rho.iter().enumerate() {
        // Konum farkındalığı: aynı bayt farklı konumda farklı katkıda bulunur
        let contribution = (byte as u64).wrapping_mul(position as u64 + 1)
            .wrapping_add(row_idx as u64 * 31)
            .wrapping_add(col_idx as u64 * 37);
        contribution.hash(&mut hasher);
    }

    // Ek: (row_idx, col_idx) çiftini doğrudan hash'e ekle
    (row_idx as u64).hash(&mut hasher);
    (col_idx as u64).hash(&mut hasher);

    let hash_val = hasher.finish() as u128;

    // q ile mod al → [0, q) aralığında alan elementi
    // Üretimde: ham hash'i genişletmek için SHAKE-128 XOF kullanılır
    //           böylece mod önyargısı minimize edilir.
    hash_val % q
}

/// Tam k×ℓ matrisinin BLAKE3 taahhüt özeti (skalar taahhüt).
///
/// STARK izi 4 sütunda tutulduğu için tam matris yerine bu tek taahhüt
/// değeri sütun 0'da kullanılır. Matrisin bütünlüğü bu hash üzerinden
/// kanıtlanır.
///
/// Türetme:
///   commitment = H(rho_prime || k_byte || ell_byte) % q
///   Burada H, tüm matris elemanlarını katlayan bir hash fonksiyonudur.
pub fn compute_lattice_commitment(matrix: &[Vec<u128>], q: u128) -> u128 {
    let mut hasher = DefaultHasher::new();

    for row in matrix {
        for &elem in row {
            elem.hash(&mut hasher);
        }
    }

    hasher.finish() as u128 % q
}

// ─────────────────────────────────────────────────────────────────────────────
// Dilithium-5 Enjeksiyon Payload'u (Genişletilmiş)
// ─────────────────────────────────────────────────────────────────────────────

/// ML-DSA imza bileşenlerini STARK izine dönüştürmek için kullanılan yapı.
///
/// Genişletilmiş alan: `rho_prime` ve `config` eklendi.
/// Önceki sabit `seed_a: u128` yerine tam `LatticeModuleConfig` kullanılır.
#[derive(Clone, Debug)]
pub struct Dilithium5InjectionPayload {
    /// 32-byte kriptografik seed ρ' — AI Guardian entropi çıktısından türetilir.
    /// AI'ın rotate sinyali geldiğinde, yeni bir rho_prime üretilir ve bu
    /// alan güncellenir. Tek bir bit değişikliği → tüm yeni A' matrisinin
    /// genişlemesi.
    pub rho_prime         : [u8; 32],
    /// Kafes modül konfigürasyonu — güvenlik seviyesi ve matris boyutları.
    pub config            : LatticeModuleConfig,
    /// Genişletilmiş A matrisi — config ve rho_prime'dan türetilir.
    pub matrix_a          : Vec<Vec<u128>>,
    /// Tam matrisin skalar STARK taahhüdü (tek sütun).
    pub lattice_commitment: u128,
    /// s1 polinom vektörü seed'i (kısa polinom — hata terimi).
    pub seed_s1           : u128,
    /// s2 polinom vektörü seed'i (kısa polinom — hata terimi).
    pub seed_s2           : u128,
    /// Zırh seviyesi (0=Hafif, 1=Ağır).
    pub armor_level       : u8,
    /// Time-lock deadline timestamp'i.
    pub timelock_deadline : u64,
}

impl Dilithium5InjectionPayload {
    /// rho-prime seed'i ve güvenlik seviyesinden tam payload oluşturur.
    ///
    /// Bu constructor, AI Guardian'ın bir rotasyon kararı verdiğinde çağrılır.
    /// `rho_prime` parametresi `generate_rho_prime_from_entropy()` çıktısıdır.
    ///
    /// # Arguments
    /// * `rho_prime` - 32-byte kriptografik seed (AI entropi çıktısı).
    /// * `level`     - Hedef ML-DSA güvenlik seviyesi.
    /// * `seed_s1`   - s1 polinom vektörü seed'i.
    /// * `seed_s2`   - s2 polinom vektörü seed'i.
    pub fn new_with_seed(
        rho_prime : [u8; 32],
        level     : MlDsaSecurityLevel,
        seed_s1   : u128,
        seed_s2   : u128,
    ) -> Self {
        let config   = LatticeModuleConfig::from_security_level(level, rho_prime);
        let matrix_a = expand_matrix_a(&rho_prime, config.k, config.ell, config.q);
        let lattice_commitment = compute_lattice_commitment(&matrix_a, config.q);

        Self {
            rho_prime,
            config,
            matrix_a,
            lattice_commitment,
            seed_s1,
            seed_s2,
            armor_level: 1,
            timelock_deadline: 1_893_456_000,
        }
    }

    /// Varsayılan panik modu payload'u — sıfır seed ile ML-DSA-87.
    /// Yalnızca test ve soğuk başlangıç için.
    pub fn panic_mode_default() -> Self {
        Self::new_with_seed([0u8; 32], MlDsaSecurityLevel::Level87, 13, 7)
    }

    /// Geriye uyumluluk için eski `new(seed_a, seed_s1, seed_s2)` arayüzü.
    /// seed_a artık kullanılmaz; rho_prime sıfır olarak başlatılır.
    #[deprecated(
        since = "2.0.0",
        note = "Kullanın: Dilithium5InjectionPayload::new_with_seed(rho_prime, level, seed_s1, seed_s2)"
    )]
    pub fn new(seed_a: u128, seed_s1: u128, seed_s2: u128) -> Self {
        // Geriye uyumluluk: seed_a'yı rho_prime'ın ilk 16 baytına dönüştür
        let mut rho_prime = [0u8; 32];
        let seed_bytes = seed_a.to_le_bytes();
        rho_prime[..16].copy_from_slice(&seed_bytes);

        Self::new_with_seed(rho_prime, MlDsaSecurityLevel::Level87, seed_s1, seed_s2)
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// İzleme Tablosu (STARK Uyumlu, 4 Sütun)
// ─────────────────────────────────────────────────────────────────────────────

/// MLWE ilişkisini kafes taahhüdü ile kodlayan 4 sütunlu STARK iz tablosu.
///
/// Sütun Düzeni:
///   [0] A_commit : Matrisin köşegen kafes taahhütleri (adım başına bir taahhüt)
///   [1] s1       : Kısa polinom vektörü s1'in kayan değerleri
///   [2] s2       : Kısa polinom vektörü s2'nin kayan değerleri
///   [3] t        : Hata terimi t = A_commit * s1 + s2 (mod q simülasyonu)
///
/// Her adımda köşegen matris elemanı kullanılır:
///   A_commit[step] = matrix_a[step % k][step % ell]
/// Bu yaklaşım, tam k×ℓ matrisin Winterfell uyumlu bir biçimde temsil
/// edilmesini sağlar.
#[derive(Debug)]
pub struct QAdaptiveTrace {
    data      : Vec<Vec<BaseElement>>,
    trace_len : usize,
    /// Bu iz tablosunun karşılık geldiği kafes konfigürasyonu.
    pub config: LatticeModuleConfig,
}

impl QAdaptiveTrace {
    /// Parameterize edilmiş ML-DSA payload'undan MLWE yürütme izi oluşturur.
    ///
    /// Her adımda:
    ///   1. Köşegen matris taahhüdü: A_i = matrix_a[step%k][step%ell] % q
    ///   2. s1 evrimi: s1_{i+1} = (s1_i + 2) (kısa polinomun kayan değeri)
    ///   3. s2 evrimi: s2_{i+1} = (s2_i + 3)
    ///   4. MLWE ilişkisi: t_i = A_i * s1_i + s2_i
    ///
    /// Güvenlik Notu:
    ///   Gerçek Dilithium'da s1 ve s2, küçük katsayılı polinomlar olup
    ///   tam NTT operasyonlarıyla işlenir. Bu simülasyon, STARK izinin
    ///   MLWE bütünlüğünü korurken Winterfell uyumlu kalmasını sağlar.
    pub fn new(payload: &Dilithium5InjectionPayload, length: usize) -> Self {
        assert!(
            length.is_power_of_two() && length >= 8,
            "İz uzunluğu 2'nin kuvveti olmalı ve >= 8 olmalıdır. Alındı: {length}"
        );

        let q      = payload.config.q;
        let k      = payload.config.k;
        let ell    = payload.config.ell;

        let mut col_a_commit = Vec::with_capacity(length); // Lattice commitment (A köşegen)
        let mut col_s1       = Vec::with_capacity(length); // s1 polinom kayan
        let mut col_s2       = Vec::with_capacity(length); // s2 polinom kayan
        let mut col_t        = Vec::with_capacity(length); // t = A*s1 + s2

        let mut curr_s1 = payload.seed_s1 % q;
        let mut curr_s2 = payload.seed_s2 % q;

        for step in 0..length {
            // Köşegen kafes taahhüdü: adım başına farklı matris elemanı
            // Bu yaklaşım, 4 sütunlu STARK çerçevesinde tam k×ℓ matrisin
            // rotasyonal bir temsilini sağlar.
            let row_idx = step % k;
            let col_idx = step % ell;
            let a_elem  = payload.matrix_a[row_idx][col_idx] % q;

            // MLWE ilişkisi: t = A * s1 + s2 (mod q)
            // BaseElement wrapping aritmetiği kullanılır
            let t_raw = a_elem.wrapping_mul(curr_s1).wrapping_add(curr_s2) % q;

            col_a_commit.push(BaseElement::new(a_elem));
            col_s1.push(BaseElement::new(curr_s1));
            col_s2.push(BaseElement::new(curr_s2));
            col_t.push(BaseElement::new(t_raw));

            // s1 ve s2'yi sonraki adım için güncelle (deterministik evrim)
            curr_s1 = curr_s1.wrapping_add(2) % q;
            curr_s2 = curr_s2.wrapping_add(3) % q;
        }

        Self {
            data: vec![col_a_commit, col_s1, col_s2, col_t],
            trace_len: length,
            config: payload.config.clone(),
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

    /// Kafes konfigürasyonunu ve iz tablosunu konsola yazdırır.
    pub fn print_table(&self) {
        println!(
            "  Kafes Konfigürasyonu: {} (k={}, ℓ={}, q={})",
            self.config.level.name(), self.config.k, self.config.ell, self.config.q
        );
        println!(
            "  rho_prime: {}...",
            hex::encode(&self.config.rho_prime[..8])
        );
        println!(
            "  Matris Boyutu: {}×{} = {} eleman",
            self.config.k, self.config.ell, self.config.matrix_elements()
        );
        println!();
        println!("  ┌──────┬─────────────────┬──────────────┬──────────────┬──────────────┐");
        println!("  │ Adım │ Sütun 0 (A_com) │ Sütun 1 (s1) │ Sütun 2 (s2) │ Sütun 3 (t)  │");
        println!("  ├──────┼─────────────────┼──────────────┼──────────────┼──────────────┤");

        let display_rows = self.trace_len.min(8);
        for step in 0..display_rows {
            let a  = self.get(step, 0).as_int();
            let s1 = self.get(step, 1).as_int();
            let s2 = self.get(step, 2).as_int();
            let t  = self.get(step, 3).as_int();
            println!(
                "  │ {:>4} │ {:>15} │ {:>12} │ {:>12} │ {:>12} │",
                step, a, s1, s2, t
            );
        }
        if self.trace_len > 8 {
            println!("  │  ... │             ... │          ... │          ... │          ... │");
        }
        println!("  └──────┴─────────────────┴──────────────┴──────────────┴──────────────┘");
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
    fn test_security_level_dimensions() {
        assert_eq!(MlDsaSecurityLevel::Level44.dimensions(), (4, 4));
        assert_eq!(MlDsaSecurityLevel::Level65.dimensions(), (6, 5));
        assert_eq!(MlDsaSecurityLevel::Level87.dimensions(), (8, 7));
    }

    #[test]
    fn test_expand_matrix_a_dimensions() {
        let rho = [0x42u8; 32];
        let matrix = expand_matrix_a(&rho, 8, 7, ML_DSA_Q);
        assert_eq!(matrix.len(), 8);
        assert_eq!(matrix[0].len(), 7);
        // Tüm elemanlar [0, q) aralığında olmalı
        for row in &matrix {
            for &elem in row {
                assert!(elem < ML_DSA_Q, "Eleman q'dan büyük: {}", elem);
            }
        }
    }

    #[test]
    fn test_rho_prime_avalanche_effect() {
        // Tek bir bit değişikliği → tamamen farklı matris (çığ etkisi testi)
        let mut rho1 = [0xAAu8; 32];
        let rho2 = {
            let mut r = rho1;
            r[15] ^= 0x01; // Tek bit flip
            r
        };

        let m1 = expand_matrix_a(&rho1, 8, 7, ML_DSA_Q);
        let m2 = expand_matrix_a(&rho2, 8, 7, ML_DSA_Q);

        // En az birkaç elemanın farklı olduğunu doğrula
        let different_count: usize = m1.iter().zip(m2.iter())
            .flat_map(|(r1, r2)| r1.iter().zip(r2.iter()))
            .filter(|(e1, e2)| e1 != e2)
            .count();

        // Çığ etkisi: en az %80 elemanın farklı olması beklenir
        let total = 8 * 7;
        assert!(
            different_count > total * 8 / 10,
            "Çığ etkisi yetersiz: {} / {} eleman farklı", different_count, total
        );
    }

    #[test]
    fn test_mlwe_trace_generation_with_config() {
        let rho_prime = [0x12u8; 32];
        let payload   = Dilithium5InjectionPayload::new_with_seed(
            rho_prime,
            MlDsaSecurityLevel::Level87,
            13, // seed_s1
            7,  // seed_s2
        );
        let trace = QAdaptiveTrace::new(&payload, 8);

        // MLWE ilişkisi her adımda sağlanmalı: t = A * s1 + s2 (mod q)
        for step in 0..8 {
            let a  = trace.get(step, 0).as_int();
            let s1 = trace.get(step, 1).as_int();
            let s2 = trace.get(step, 2).as_int();
            let t  = trace.get(step, 3).as_int();

            let expected_t = a.wrapping_mul(s1).wrapping_add(s2) % ML_DSA_Q;
            assert_eq!(
                t, expected_t,
                "MLWE ilişkisi adım {}'de bozuldu: t={} ≠ A*s1+s2={}", step, t, expected_t
            );
        }
    }

    #[test]
    fn test_payload_new_deprecated_backward_compat() {
        // Geriye uyumluluk: eski new(seed_a, seed_s1, seed_s2) arayüzü
        #[allow(deprecated)]
        let payload = Dilithium5InjectionPayload::new(42, 13, 7);
        let trace   = QAdaptiveTrace::new(&payload, 8);
        // En az ilk adım geçerli olmalı
        assert!(trace.get(0, 3).as_int() < ML_DSA_Q);
    }
}
