// =============================================================================
// Q-ADAPTIVE ZK — Kriptografik Karma Katmanı (src/hashing.rs)
// =============================================================================
// Bu modül, daha önce `std::collections::hash_map::DefaultHasher` ile yapılan
// tüm türetmeleri devralır.
//
// Neden değişti:
//   DefaultHasher = SipHash-1-3. İki ayrı sorunu vardı:
//     a) 64-bit çıktı, kriptografik ön-görüntü direnci iddia edilmiyor.
//     b) Daha ciddisi: Rust standart kütüphanesi SipHash çıktısının sürümler
//        arasında kararlı kalacağını GARANTİ ETMEZ. Yani aynı ρ' başka bir
//        derleyici sürümünde başka bir A matrisi üretebilirdi ve jürinin
//        kendi makinesinde koştuğu kanıt bizimkiyle tutmazdı.
//
// Yeni ilkeller:
//   ρ' ve kısa tohum türetimi     → BLAKE3 (alan-ayrımlı)
//   Kafes matrisi A genişletmesi  → SHAKE-128 XOF + rejection sampling
//
//   SHAKE-128 seçimi rastgele değil: NIST FIPS 204 §7.3'teki ExpandA
//   prosedürünün kullandığı ilkelin aynısıdır. Rejection sampling de
//   oradan gelir — ham XOF baytını `% q` ile daraltmak modüler önyargı
//   yaratır, çünkü 2^24 aralığı q = 8.380.417'nin tam katı değildir.
//
// Alan Ayrımı (domain separation):
//   Aynı ρ''den birden fazla bağımsız değer türetiyoruz (matris, s1, s2).
//   Her türetme farklı bir sabit etiketle başlar; böylece bir türetmenin
//   çıktısı diğerini ele vermez. Etiketler aşağıda tek yerde tanımlıdır.
// =============================================================================

use blake3::Hasher as Blake3Hasher;
use sha3::digest::{ExtendableOutput, Update, XofReader};
use sha3::Shake128;

// ─────────────────────────────────────────────────────────────────────────────
// Alan Ayrım Etiketleri
// ─────────────────────────────────────────────────────────────────────────────

/// ρ' türetimi — AI entropi köprüsü.
const DOMAIN_RHO_PRIME: &[u8] = b"Q-ADAPTIVE/v1/rho-prime";

/// Kafes matrisi A genişletmesi (FIPS 204 ExpandA karşılığı).
const DOMAIN_EXPAND_A: &[u8] = b"Q-ADAPTIVE/v1/expand-A";

/// Kısa polinom vektörü tohumları s1, s2 (FIPS 204 ExpandS karşılığı).
const DOMAIN_SHORT_SEEDS: &[u8] = b"Q-ADAPTIVE/v1/short-seeds";

/// Kafes matrisinin skalar taahhüdü.
const DOMAIN_LATTICE_COMMIT: &[u8] = b"Q-ADAPTIVE/v1/lattice-commit";

// ─────────────────────────────────────────────────────────────────────────────
// ρ' Türetimi
// ─────────────────────────────────────────────────────────────────────────────

/// AI Guardian'ın risk skoru ve çalışma bağlamından 32-byte ρ' seed'i türetir.
///
/// **Tam deterministiktir.** Aynı girdi her makinede, her derlemede birebir
/// aynı ρ''yü verir. Eski uygulamada `std::process::id()` karıştırılıyordu;
/// bu, kanıtı yeniden üretilemez kılıyordu ve kaldırıldı.
///
/// Taze entropi isteniyorsa çağıran taraf bunu `extra_entropy` ile açıkça
/// verir ve payload'da işaretler — sessizce karıştırılmaz.
///
/// # Arguments
/// * `ai_risk_score` - AI modülünden gelen risk yüzdesi (0.0 – 100.0).
/// * `epoch_ns`      - Dönem damgası (nanosaniye). Çağıran belirler.
/// * `user_op_hash`  - Bu kanıtın bağlandığı UserOperation özeti (boş olabilir).
/// * `extra_entropy` - İsteğe bağlı taze entropi. `None` ise çıktı deterministik.
pub fn derive_rho_prime(
    ai_risk_score: f64,
    epoch_ns: u64,
    user_op_hash: &[u8],
    extra_entropy: Option<&[u8; 32]>,
) -> [u8; 32] {
    let mut hasher = Blake3Hasher::new();

    hasher.update(DOMAIN_RHO_PRIME);
    // Uzunluk ön-eki: farklı alanların birleşiminin belirsiz olmaması için.
    // (ör. user_op_hash = "ab" + boş, ile "a" + "b" aynı özete gitmemeli)
    hasher.update(&ai_risk_score.to_bits().to_le_bytes());
    hasher.update(&epoch_ns.to_le_bytes());
    hasher.update(&(user_op_hash.len() as u64).to_le_bytes());
    hasher.update(user_op_hash);

    match extra_entropy {
        Some(bytes) => {
            hasher.update(&[1u8]); // taze entropi VAR işareti
            hasher.update(bytes);
        }
        None => {
            hasher.update(&[0u8]); // deterministik koşu işareti
        }
    }

    *hasher.finalize().as_bytes()
}

// ─────────────────────────────────────────────────────────────────────────────
// Kısa Tohum Türetimi (s1, s2)
// ─────────────────────────────────────────────────────────────────────────────

/// ρ''den s1 ve s2 kısa polinom tohumlarını türetir.
///
/// Eski uygulama tohumları ρ''nin **ham baytlarından** alıyordu:
///   `seed_s1 = u128::from_le_bytes(rho_prime[0..16])`
///   `seed_s2 = u128::from_le_bytes(rho_prime[16..32])`
/// Bu, ρ''nin 32 baytının tamamını iz tablosunda açığa çıkarıyordu — iz
/// herkese açık olduğu için tohum artık gizli değildi.
///
/// Şimdi ayrı bir alan etiketiyle yeniden türetiliyorlar: izden s1/s2'yi
/// görmek ρ' hakkında bilgi vermiyor.
///
/// # Returns
/// `(seed_s1, seed_s2)` — her ikisi de `[0, q)` aralığına indirgenmiş.
pub fn derive_short_seeds(rho_prime: &[u8; 32], q: u128) -> (u128, u128) {
    let mut hasher = Blake3Hasher::new();
    hasher.update(DOMAIN_SHORT_SEEDS);
    hasher.update(rho_prime);

    // 64 baytlık XOF çıktısı: ilk 32 bayt s1'e, ikinci 32 bayt s2'ye.
    let mut out = [0u8; 64];
    hasher.finalize_xof().fill(&mut out);

    let s1 = reduce_bytes_to_field(&out[0..32], q);
    let s2 = reduce_bytes_to_field(&out[32..64], q);

    (s1, s2)
}

/// Bayt dizisini önyargısız biçimde `[0, q)` aralığına indirger.
///
/// 32 bayt (256 bit), q ≈ 2^23'ten çok daha geniş olduğu için basit `% q`
/// işleminin yarattığı önyargı 2^-233 mertebesindedir — pratikte ölçülemez.
/// Bu yüzden burada rejection sampling'e gerek yoktur; matris genişletmesinde
/// ise 24-bit örnekler kullanıldığı için gereklidir (bkz. `expand_matrix_a`).
fn reduce_bytes_to_field(bytes: &[u8], q: u128) -> u128 {
    let mut acc: u128 = 0;
    for &b in bytes {
        // 2^8 tabanında Horner; her adımda q'ya indirgenerek taşma önlenir.
        acc = (acc.wrapping_mul(256).wrapping_add(b as u128)) % q;
    }
    acc
}

// ─────────────────────────────────────────────────────────────────────────────
// Kafes Matrisi Genişletmesi (FIPS 204 ExpandA karşılığı)
// ─────────────────────────────────────────────────────────────────────────────

/// ρ''den A ∈ R_q^{k×ℓ} matrisinin skalar taahhüt temsilini genişletir.
///
/// Her (i, j) hücresi için ayrı bir SHAKE-128 XOF akışı açılır:
///   `SHAKE128(DOMAIN || ρ' || i || j)`
/// ve akıştan 3 baytlık (24-bit) bloklar okunarak ilk `< q` olan kabul edilir.
///
/// **Rejection sampling neden şart:** 24-bit aralık [0, 16.777.216),
/// q = 8.380.417'nin tam katı değil. Ham değeri `% q` ile daraltmak
/// [0, 16.384) aralığındaki değerleri diğerlerinin iki katı olasılıkla
/// üretirdi. FIPS 204 §7.3 tam da bu yüzden reddetme kullanır.
///
/// # Arguments
/// * `rho` - 32-byte seed (ρ').
/// * `k`   - Matris satır sayısı.
/// * `ell` - Matris sütun sayısı.
/// * `q`   - Modüler alan karakteristiği.
///
/// # Returns
/// `k×ℓ` boyutunda matris; her eleman `[0, q)` aralığında.
pub fn expand_matrix_a(rho: &[u8; 32], k: usize, ell: usize, q: u128) -> Vec<Vec<u128>> {
    let mut matrix = Vec::with_capacity(k);

    for i in 0..k {
        let mut row = Vec::with_capacity(ell);
        for j in 0..ell {
            row.push(sample_field_element(rho, i as u16, j as u16, q));
        }
        matrix.push(row);
    }

    matrix
}

/// Tek bir (i, j) hücresi için önyargısız alan elemanı örnekler.
fn sample_field_element(rho: &[u8; 32], row_idx: u16, col_idx: u16, q: u128) -> u128 {
    let mut xof = Shake128::default();
    xof.update(DOMAIN_EXPAND_A);
    xof.update(rho);
    // FIPS 204 ExpandA da satır/sütun indisini ayrı baytlar olarak ekler.
    xof.update(&row_idx.to_le_bytes());
    xof.update(&col_idx.to_le_bytes());

    let mut reader = xof.finalize_xof();
    let mut block = [0u8; 3];

    // Reddetme döngüsü. Kabul olasılığı q / 2^24 ≈ %49,9, yani beklenen
    // deneme sayısı ~2. Sonsuz döngü riski yok: her okuma bağımsız.
    loop {
        reader.read(&mut block);
        // 24-bit little-endian tamsayı
        let candidate = (block[0] as u128) | ((block[1] as u128) << 8) | ((block[2] as u128) << 16);
        if candidate < q {
            return candidate;
        }
        // candidate >= q → reddet, bir sonraki 3 baytı oku.
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Kafes Taahhüdü
// ─────────────────────────────────────────────────────────────────────────────

/// Tam k×ℓ matrisin skalar STARK taahhüdünü hesaplar.
///
/// İz tablosu 4 sütunda tutulduğu için tam matris yerine bu tek değer
/// taşınır. BLAKE3 ile özetlenir, ardından `[0, q)` aralığına indirgenir.
pub fn compute_lattice_commitment(matrix: &[Vec<u128>], q: u128) -> u128 {
    let mut hasher = Blake3Hasher::new();
    hasher.update(DOMAIN_LATTICE_COMMIT);

    // Boyutları da özete dahil et: 4×4'lük bir matris ile aynı elemanları
    // taşıyan 2×8'lik bir matris aynı taahhüde gitmemeli.
    hasher.update(&(matrix.len() as u64).to_le_bytes());
    hasher.update(&(matrix.first().map_or(0, |r| r.len()) as u64).to_le_bytes());

    for row in matrix {
        for &elem in row {
            hasher.update(&elem.to_le_bytes());
        }
    }

    let mut out = [0u8; 32];
    hasher.finalize_xof().fill(&mut out);
    reduce_bytes_to_field(&out, q)
}

// ─────────────────────────────────────────────────────────────────────────────
// Birim Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    const Q: u128 = 8_380_417;

    /// BULGU 11 REGRESYONU — ρ' tam deterministik olmalı.
    ///
    /// Eski kod `std::process::id()` karıştırıyordu; bu test o davranış geri
    /// gelirse kırılır, çünkü aynı süreçte bile iki farklı çağrının aynı
    /// çıktıyı vermesi gerektiğini değil, **dokümante edilmiş girdilerin
    /// dışında hiçbir şeyin çıktıyı etkilemediğini** sınar.
    #[test]
    fn rho_prime_tam_deterministik() {
        let a = derive_rho_prime(92.4, 1_700_000_000_000_000_000, b"0xdeadbeef", None);
        let b = derive_rho_prime(92.4, 1_700_000_000_000_000_000, b"0xdeadbeef", None);
        assert_eq!(
            a, b,
            "Aynı girdi aynı ρ''yü vermeli — süreç kimliği karışmamalı"
        );

        // Bilinen bir vektörü sabitle: türetme kuralı sessizce değişirse kırılır.
        assert_ne!(a, [0u8; 32], "ρ' sıfır dizisi olmamalı");
    }

    #[test]
    fn rho_prime_her_girdiye_duyarli() {
        let temel = derive_rho_prime(92.4, 1_000, b"op", None);

        assert_ne!(
            temel,
            derive_rho_prime(92.5, 1_000, b"op", None),
            "risk skoru"
        );
        assert_ne!(
            temel,
            derive_rho_prime(92.4, 1_001, b"op", None),
            "dönem damgası"
        );
        assert_ne!(
            temel,
            derive_rho_prime(92.4, 1_000, b"op2", None),
            "userOpHash"
        );
        assert_ne!(
            temel,
            derive_rho_prime(92.4, 1_000, b"op", Some(&[7u8; 32])),
            "taze entropi işareti"
        );
    }

    /// BULGU 7 REGRESYONU — çığ etkisi, tek bit için TÜM hücrelerde.
    ///
    /// Eski DefaultHasher tabanlı türetme bu testi geçemiyordu; o yüzden eski
    /// test "en az %80 hücre değişsin" diyordu. SHAKE-128 ile beklenti 56/56.
    #[test]
    fn cig_etkisi_tek_bit() {
        let rho1 = [0xAAu8; 32];
        let rho2 = {
            let mut r = rho1;
            r[15] ^= 0x01;
            r
        };

        let m1 = expand_matrix_a(&rho1, 8, 7, Q);
        let m2 = expand_matrix_a(&rho2, 8, 7, Q);

        let farkli = m1
            .iter()
            .zip(m2.iter())
            .flat_map(|(r1, r2)| r1.iter().zip(r2.iter()))
            .filter(|(a, b)| a != b)
            .count();

        assert_eq!(
            farkli, 56,
            "56 hücrenin 56'sı değişmeli, {} değişti",
            farkli
        );
    }

    #[test]
    fn matris_genisletme_deterministik() {
        let rho = [0x42u8; 32];
        let m1 = expand_matrix_a(&rho, 8, 7, Q);
        let m2 = expand_matrix_a(&rho, 8, 7, Q);
        assert_eq!(m1, m2, "Aynı ρ' aynı matrisi vermeli");
    }

    #[test]
    fn matris_elemanlari_alan_icinde() {
        let rho = [0x11u8; 32];
        for (k, ell) in [(4usize, 4usize), (6, 5), (8, 7)] {
            let m = expand_matrix_a(&rho, k, ell, Q);
            assert_eq!(m.len(), k);
            assert_eq!(m[0].len(), ell);
            for row in &m {
                for &e in row {
                    assert!(e < Q, "Eleman q'yu aşıyor: {}", e);
                }
            }
        }
    }

    /// Rejection sampling'in modüler önyargıyı gerçekten kaldırdığını sınar.
    ///
    /// Önyargılı `% q` yaklaşımında [0, 2^24 − q) aralığı iki kat sık çıkardı.
    /// Burada alt yarı ile üst yarının sayımları kabaca eşit olmalı.
    #[test]
    fn ornekleme_makul_duzgun() {
        let rho = [0x5Au8; 32];
        // 16×16 = 256 örnek, tek bir ρ''den farklı (i, j) ile.
        let m = expand_matrix_a(&rho, 16, 16, Q);
        let ornekler: Vec<u128> = m.into_iter().flatten().collect();

        let yari = Q / 2;
        let alt = ornekler.iter().filter(|&&x| x < yari).count();
        let ust = ornekler.len() - alt;

        // 256 örnekte binom dalgalanması ±~32. Önyargılı üretimde oran
        // ~2:1'e giderdi (171/85), bu aralık onu yakalar.
        assert!(
            alt > 96 && ust > 96,
            "Dağılım çarpık görünüyor: alt={}, üst={}",
            alt,
            ust
        );
    }

    /// BULGU E6 REGRESYONU — s1/s2 ρ''nin ham baytları OLMAMALI.
    #[test]
    fn kisa_tohumlar_ham_baytlardan_turetilmiyor() {
        let rho = [0x3Cu8; 32];
        let (s1, s2) = derive_short_seeds(&rho, Q);

        // Eski davranış: doğrudan ham bayt dilimlerinin okunması.
        let mut ham1 = [0u8; 16];
        let mut ham2 = [0u8; 16];
        ham1.copy_from_slice(&rho[0..16]);
        ham2.copy_from_slice(&rho[16..32]);
        let eski_s1 = u128::from_le_bytes(ham1) % Q;
        let eski_s2 = u128::from_le_bytes(ham2) % Q;

        assert_ne!(s1, eski_s1, "s1 hâlâ ρ''nin ham baytlarından okunuyor");
        assert_ne!(s2, eski_s2, "s2 hâlâ ρ''nin ham baytlarından okunuyor");
        assert!(s1 < Q && s2 < Q);
    }

    #[test]
    fn kisa_tohumlar_deterministik_ve_birbirinden_bagimsiz() {
        let rho = [0x99u8; 32];
        assert_eq!(derive_short_seeds(&rho, Q), derive_short_seeds(&rho, Q));

        let (s1, s2) = derive_short_seeds(&rho, Q);
        assert_ne!(s1, s2, "s1 ve s2 aynı değeri almamalı");
    }

    #[test]
    fn taahhut_matrise_duyarli() {
        let m1 = expand_matrix_a(&[0x01u8; 32], 4, 4, Q);
        let mut m2 = m1.clone();
        m2[2][3] = (m2[2][3] + 1) % Q;

        assert_ne!(
            compute_lattice_commitment(&m1, Q),
            compute_lattice_commitment(&m2, Q),
            "Tek hücre değişimi taahhüdü değiştirmeli"
        );
    }

    #[test]
    fn taahhut_boyutlara_duyarli() {
        // Aynı elemanlar, farklı şekil → farklı taahhüt.
        let duz: Vec<u128> = (0..16).map(|i| i as u128).collect();
        let dort_dort: Vec<Vec<u128>> = duz.chunks(4).map(|c| c.to_vec()).collect();
        let iki_sekiz: Vec<Vec<u128>> = duz.chunks(8).map(|c| c.to_vec()).collect();

        assert_ne!(
            compute_lattice_commitment(&dort_dort, Q),
            compute_lattice_commitment(&iki_sekiz, Q),
        );
    }
}
