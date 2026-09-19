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

use winterfell::math::{fields::f128::BaseElement, StarkField};

// Kriptografik türetmelerin tamamı `hashing` modülünden gelir.
// Bu dosyada daha önce `DefaultHasher` (SipHash) kullanılıyordu; kaldırıldı.
// Gerekçe için bkz. src/hashing.rs başlığı.
pub use crate::hashing::{compute_lattice_commitment, expand_matrix_a};
use crate::hashing::derive_short_seeds;

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

    /// Kademelerin sıralamasını verir (44 < 65 < 87).
    ///
    /// Tek yönlü tırmanma kuralı bu sıralama üzerinden uygulanır:
    /// zırh yalnızca `rank` değeri artacak şekilde değişebilir.
    /// Bkz. `armor::decide` ve zincir tarafında `_applyArmorUpdate`.
    pub fn rank(&self) -> u8 {
        match self {
            MlDsaSecurityLevel::Level44 => 0,
            MlDsaSecurityLevel::Level65 => 1,
            MlDsaSecurityLevel::Level87 => 2,
        }
    }

    /// CLI argümanından güvenlik kademesini ayrıştırır.
    ///
    /// Eski uygulama `"87" | _ => Level87` deseniyle **geçersiz girdiyi
    /// sessizce en yüksek kademeye düşürüyordu**. Güvenli yöndeydi ama
    /// sessizdi: `--level abc` yazan bir yapılandırma hatası hiç fark
    /// edilmeden geçiyordu. Artık açık bir `Result` dönüyor ve CLI
    /// geçersiz girdide çıkış kodu 1 ile duruyor.
    pub fn parse(girdi: &str) -> Result<Self, String> {
        match girdi.trim() {
            "44" => Ok(MlDsaSecurityLevel::Level44),
            "65" => Ok(MlDsaSecurityLevel::Level65),
            "87" => Ok(MlDsaSecurityLevel::Level87),
            diger => Err(format!(
                "Geçersiz --level değeri: '{}'. Beklenen: 44, 65 veya 87.",
                diger
            )),
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

// Bu bölümdeki üç fonksiyon (`expand_matrix_a`, `deterministic_field_element`,
// `compute_lattice_commitment`) `src/hashing.rs`'e taşındı ve kriptografik
// ilkellerle yeniden yazıldı:
//
//   • Matris genişletmesi artık SHAKE-128 XOF + rejection sampling kullanıyor
//     — FIPS 204 §7.3 ExpandA'nın kullandığı ilkelin aynısı. Eski `% q`
//     daraltması modüler önyargı yaratıyordu.
//   • Taahhüt BLAKE3 ile hesaplanıyor; yorum "BLAKE3" diyordu ama kod
//     SipHash çalıştırıyordu.
//   • `deterministic_field_element` tamamen kaldırıldı.
//
// İsimler dosyanın başındaki `pub use` ile buradan erişilebilir kalmaya
// devam ediyor, böylece çağıran kod değişmedi.

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

    /// ρ''den tam payload'u türetir — kısa tohumlar dahil.
    ///
    /// **Tercih edilen kurucu budur.** `new_with_seed` çağıranın s1/s2'yi
    /// kendisinin üretmesini bekler; eski `main.rs` bunu ρ''nin ham
    /// baytlarını ikiye bölerek yapıyordu:
    ///
    /// ```text
    ///   seed_s1 = u128::from_le_bytes(rho_prime[0..16])   // HATA E6
    ///   seed_s2 = u128::from_le_bytes(rho_prime[16..32])
    /// ```
    ///
    /// Bu, ρ''nin 32 baytının tamamını herkese açık iz tablosunda açığa
    /// çıkarıyordu. Artık tohumlar ayrı bir alan etiketiyle SHAKE/BLAKE3'ten
    /// yeniden türetiliyor; izden s1/s2'yi okumak ρ' hakkında bilgi vermiyor.
    pub fn from_rho_prime(rho_prime: [u8; 32], level: MlDsaSecurityLevel) -> Self {
        let (seed_s1, seed_s2) = derive_short_seeds(&rho_prime, ML_DSA_Q);
        Self::new_with_seed(rho_prime, level, seed_s1, seed_s2)
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

        // ── HATA E2 DÜZELTMESİ: aritmetik artık ALAN aritmetiği ──────────────
        //
        // Bu tablo eskiden u128 üzerinde `wrapping_mul(...) % q` ile
        // hesaplanıyordu; kanıtlanan tablo (`pipeline::trace_table_from`) ise
        // f128 alan aritmetiği kullanıyor ve AIR kısıtı da alan aritmetiğini
        // doğruluyor (`next[3] - (next[0]*next[1] + next[2]) = 0`).
        //
        // Sonuç: sahnede jüriye gösterilen t sütunu, STARK'ın kanıtladığı t
        // sütunu DEĞİLDİ — `% q` yüzünden farklı sayılardı.
        //
        // Artık burada da `BaseElement` işlemleri kullanılıyor, yani bu tablo
        // kanıtlanan tablonun ta kendisi. `pipeline::trace_table_from` bunu
        // kopyalayarak Winterfell tablosunu üretir; iki temsil arasında
        // ayrışma imkânı kalmaz.
        let mut curr_s1 = BaseElement::new(payload.seed_s1 % q);
        let mut curr_s2 = BaseElement::new(payload.seed_s2 % q);

        for step in 0..length {
            // Köşegen kafes taahhüdü: adım başına farklı matris elemanı
            // Bu yaklaşım, 4 sütunlu STARK çerçevesinde tam k×ℓ matrisin
            // rotasyonal bir temsilini sağlar.
            let row_idx = step % k;
            let col_idx = step % ell;
            let a_elem  = BaseElement::new(payload.matrix_a[row_idx][col_idx] % q);

            // MLWE ilişkisi: t = A * s1 + s2 — AIR kısıtıyla birebir aynı ifade.
            let t_elem = a_elem * curr_s1 + curr_s2;

            col_a_commit.push(a_elem);
            col_s1.push(curr_s1);
            col_s2.push(curr_s2);
            col_t.push(t_elem);

            // s1 ve s2'yi sonraki adım için güncelle (deterministik evrim).
            // AIR: s1_next = s1_curr + 2, s2_next = s2_curr + 3.
            curr_s1 += BaseElement::new(2);
            curr_s2 += BaseElement::new(3);
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

    /// İz tablosundaki adım sayısı.
    ///
    /// `pipeline::trace_table_from` Winterfell tablosunu bu uzunlukta açar;
    /// iki tablonun boyutu da tek kaynaktan gelir.
    pub fn length(&self) -> usize {
        self.trace_len
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

        // Çığ etkisi: SHAKE-128 ile beklenti TÜM hücrelerin değişmesi.
        //
        // Bu eşik eskiden "%80" idi; DefaultHasher tabanlı türetme 56/56'yı
        // tutturamadığı için gevşetilmişti. Kriptografik XOF ile gevşetmeye
        // gerek yok — eşik sıkılaştırıldı ki zayıf bir karma geri gelirse
        // test kırılsın.
        let total = 8 * 7;
        assert_eq!(
            different_count, total,
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

        // MLWE ilişkisi her adımda sağlanmalı: t = A * s1 + s2
        //
        // Dikkat: burada `% q` YOK. AIR kısıtı da alan aritmetiğini doğrular
        // (bkz. air.rs::evaluate_transition). Bu testin `% q` ile yazılmış
        // hâli, gösterilen izin kanıtlanan izden ayrışmasını gizliyordu.
        for step in 0..8 {
            let a  = trace.get(step, 0);
            let s1 = trace.get(step, 1);
            let s2 = trace.get(step, 2);
            let t  = trace.get(step, 3);

            assert_eq!(
                t, a * s1 + s2,
                "MLWE ilişkisi adım {}'de bozuldu", step
            );
        }
    }

    /// HATA E5 REGRESYONU — geçersiz `--level` sessizce 87'ye düşmemeli.
    #[test]
    fn test_level_parse_gecersiz_girdiyi_reddediyor() {
        assert_eq!(MlDsaSecurityLevel::parse("44").unwrap(), MlDsaSecurityLevel::Level44);
        assert_eq!(MlDsaSecurityLevel::parse("65").unwrap(), MlDsaSecurityLevel::Level65);
        assert_eq!(MlDsaSecurityLevel::parse("87").unwrap(), MlDsaSecurityLevel::Level87);

        // Eski desen `"87" | _ => Level87` bunların hepsini 87 yapardı.
        for gecersiz in ["abc", "", "88", "-1", "44.0"] {
            assert!(
                MlDsaSecurityLevel::parse(gecersiz).is_err(),
                "'{}' sessizce kabul edildi — eski desen geri gelmiş olabilir",
                gecersiz
            );
        }
    }

    #[test]
    fn test_kademe_siralamasi() {
        assert!(MlDsaSecurityLevel::Level44.rank() < MlDsaSecurityLevel::Level65.rank());
        assert!(MlDsaSecurityLevel::Level65.rank() < MlDsaSecurityLevel::Level87.rank());
    }

    /// HATA E6 REGRESYONU — kısa tohumlar ρ''nin ham baytları olmamalı.
    #[test]
    fn test_from_rho_prime_kisa_tohumlari_turetiyor() {
        let rho = [0x6Bu8; 32];
        let payload = Dilithium5InjectionPayload::from_rho_prime(rho, MlDsaSecurityLevel::Level87);

        // Eski main.rs davranışı:
        let mut b1 = [0u8; 16];
        let mut b2 = [0u8; 16];
        b1.copy_from_slice(&rho[0..16]);
        b2.copy_from_slice(&rho[16..32]);
        let eski_s1 = u128::from_le_bytes(b1) % ML_DSA_Q;
        let eski_s2 = u128::from_le_bytes(b2) % ML_DSA_Q;

        assert_ne!(payload.seed_s1, eski_s1, "s1 hâlâ ρ''nin ham baytlarından");
        assert_ne!(payload.seed_s2, eski_s2, "s2 hâlâ ρ''nin ham baytlarından");
    }

    /// BULGU 4 REGRESYONU — kademe değişince kafes GERÇEKTEN büyüyor.
    #[test]
    fn test_kademe_matris_boyutunu_degistiriyor() {
        let rho = [0x2Du8; 32];

        let p44 = Dilithium5InjectionPayload::from_rho_prime(rho, MlDsaSecurityLevel::Level44);
        let p65 = Dilithium5InjectionPayload::from_rho_prime(rho, MlDsaSecurityLevel::Level65);
        let p87 = Dilithium5InjectionPayload::from_rho_prime(rho, MlDsaSecurityLevel::Level87);

        assert_eq!(p44.config.matrix_elements(), 16); // 4×4
        assert_eq!(p65.config.matrix_elements(), 30); // 6×5
        assert_eq!(p87.config.matrix_elements(), 56); // 8×7

        assert!(
            p44.config.matrix_elements() < p65.config.matrix_elements()
                && p65.config.matrix_elements() < p87.config.matrix_elements(),
            "Zırh kademesi kafes boyutunu artırmalı"
        );
    }

    #[test]
    fn test_payload_new_deprecated_backward_compat() {
        // Geriye uyumluluk: eski new(seed_a, seed_s1, seed_s2) arayüzü
        #[allow(deprecated)]
        let payload = Dilithium5InjectionPayload::new(42, 13, 7);
        let trace   = QAdaptiveTrace::new(&payload, 8);

        // Bu iddia eskiden `trace.get(0, 3).as_int() < ML_DSA_Q` idi.
        //
        // O iddia, t sütununun `% q` ile daraltıldığını varsayıyordu — yani
        // hata E2'nin kendisini sabitliyordu. AIR kısıtı `% q` uygulamaz
        // (`next[3] = next[0]*next[1] + next[2]`), dolayısıyla t doğal olarak
        // q'yu aşar. Doğru değişmez, MLWE ilişkisinin kendisidir:
        let a  = trace.get(0, 0);
        let s1 = trace.get(0, 1);
        let s2 = trace.get(0, 2);
        assert_eq!(trace.get(0, 3), a * s1 + s2);

        // A, s1 ve s2 girdileri ise hâlâ alan içinde olmalı.
        assert!(a.as_int()  < ML_DSA_Q);
        assert!(s1.as_int() < ML_DSA_Q);
        assert!(s2.as_int() < ML_DSA_Q);
    }
}
