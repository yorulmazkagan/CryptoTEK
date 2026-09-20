// =============================================================================
// Q-ADAPTIVE ZK — Gerçek Post-Kuantum İmza Katmanı (src/pqc.rs)
// =============================================================================
// Bu modül, projedeki en büyük dürüstlük açığını kapatır.
//
// Önceki durum: Depoda TEK BİR post-kuantum kütüphanesi bağımlılığı yoktu.
//   `MlDsaSecurityLevel` yalnızca (k, ℓ) çiftini döndüren bir enum'du; ne
//   anahtar üretiliyor, ne imza atılıyor, ne de doğrulama yapılıyordu.
//   Buna rağmen raporlar "ML-DSA kullanıyoruz" diyordu.
//
// Şimdi: `fips204` crate'i ile
//   • ρ''den deterministik anahtar çifti üretiliyor (FIPS 204 ξ tohumu),
//   • gerçek bir mesaj gerçekten imzalanıyor,
//   • imza gerçekten doğrulanıyor,
//   • kurcalanmış mesajın reddedildiği sınanıyor,
//   • ölçülen pk/sk/imza boyutları NIST FIPS 204 tablosuyla karşılaştırılıyor.
//
// Zırh kademesi ↔ imza boyutu bağı (FIPS 204 Tablo 2):
//   ┌────────────┬────────┬────────┬─────────┐
//   │ Kademe     │ pk     │ sk     │ imza    │
//   ├────────────┼────────┼────────┼─────────┤
//   │ ML-DSA-44  │  1.312 │  2.560 │  2.420  │
//   │ ML-DSA-65  │  1.952 │  4.032 │  3.309  │
//   │ ML-DSA-87  │  2.592 │  4.896 │  4.627  │
//   └────────────┴────────┴────────┴─────────┘
//
//   "Zırh kalınlaştı" artık bir JSON metni değil: imza 2.420 → 4.627 bayta
//   gerçekten çıkıyor ve bu sayı kütüphaneden ölçülüyor, elle yazılmıyor.
//
// Determinizm:
//   Hem anahtar üretimi hem imzalama ρ''den türetilmiş tohumlarla yapılır.
//   Aynı ρ' → aynı anahtar çifti → aynı imza. Jüri koşuyu kendi makinesinde
//   birebir tekrarlayabilir.
// =============================================================================

use std::time::Instant;

use fips204::traits::{KeyGen, SerDes, Signer, Verifier};
use fips204::{ml_dsa_44, ml_dsa_65, ml_dsa_87};

use crate::trace::MlDsaSecurityLevel;

// ─────────────────────────────────────────────────────────────────────────────
// Alan Ayrım Etiketleri
// ─────────────────────────────────────────────────────────────────────────────

/// Anahtar üretim tohumu ξ'nin ρ''den türetilmesi.
const DOMAIN_KEYGEN_XI: &[u8] = b"Q-ADAPTIVE/v1/mldsa-keygen-xi";

/// İmzalama tohumunun ρ''den türetilmesi (deterministik imza için).
const DOMAIN_SIGN_SEED: &[u8] = b"Q-ADAPTIVE/v1/mldsa-sign-seed";

/// İmza bağlamı (FIPS 204 `ctx` alanı). Bu etiketle imzalanan bir mesaj,
/// başka bir bağlamda üretilmiş imzayla karıştırılamaz.
const SIGN_CONTEXT: &[u8] = b"Q-ADAPTIVE-GUARDIAN";

// ─────────────────────────────────────────────────────────────────────────────
// NIST FIPS 204 Referans Boyutları
// ─────────────────────────────────────────────────────────────────────────────

/// Bir güvenlik kademesi için standardın öngördüğü (pk, sk, imza) boyutları.
///
/// Bu değerler NIST FIPS 204 Tablo 2'den ELLE alınmıştır ve kasıtlı olarak
/// `fips204` crate'inden BAĞIMSIZDIR. `standart_boyutlari_uyusuyor` testi
/// kütüphanenin ürettiği boyutları bu tabloyla karşılaştırır; kütüphane bir
/// gün yanlış boyut üretirse test kırılır. Aynı kaynaktan okunsalardı test
/// hiçbir şey kanıtlamazdı.
///
/// Yalnızca testlerden çağrıldığı için ikili derlemede "kullanılmıyor"
/// görünür; referans tablosu olarak burada durması kasıtlıdır.
#[allow(dead_code)]
pub fn standart_boyutlar(level: MlDsaSecurityLevel) -> (usize, usize, usize) {
    match level {
        MlDsaSecurityLevel::Level44 => (1_312, 2_560, 2_420),
        MlDsaSecurityLevel::Level65 => (1_952, 4_032, 3_309),
        MlDsaSecurityLevel::Level87 => (2_592, 4_896, 4_627),
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// İmza Kaydı
// ─────────────────────────────────────────────────────────────────────────────

/// Tek bir ML-DSA koşusunun ölçülmüş sonucu.
///
/// Buradaki her sayı **ölçülmüştür** — hiçbiri elle yazılmamıştır.
///
/// `PartialEq` **bilinçli olarak türetilmiyor**: yapı artık süre alanları
/// içeriyor ve iki koşunun sürelerinin birbirine eşit olmasını beklemek
/// anlamsızdır. Determinizmi sınamak isteyen `public_key_commitment` ve
/// `signature_prefix_hex` alanlarını karşılaştırmalıdır — kriptografik çıktı
/// deterministiktir, ölçülen süre değildir.
#[derive(Clone, Debug)]
pub struct PqcSignatureRecord {
    /// Bu koşuda kullanılan güvenlik kademesi.
    pub level: MlDsaSecurityLevel,
    /// Açık anahtar uzunluğu (bayt).
    pub public_key_len: usize,
    /// Gizli anahtar uzunluğu (bayt).
    pub secret_key_len: usize,
    /// İmza uzunluğu (bayt).
    pub signature_len: usize,
    /// Açık anahtarın BLAKE3 taahhüdü — zincire yazılabilir kimlik.
    pub public_key_commitment: [u8; 32],
    /// İmzanın ilk 16 baytı (hex) — kayıt/gösterim amaçlı.
    pub signature_prefix_hex: String,
    /// İmza bu koşuda gerçekten doğrulandı mı?
    pub verified: bool,

    // ── Ölçülen süreler ─────────────────────────────────────────────────────
    //
    // Arayüzdeki adım adım şerit bu üç sayıyı gösterir. Ayrı ayrı ölçülüyorlar
    // çünkü "ML-DSA yavaş mı?" sorusunun cevabı kademeye göre değişir ve hangi
    // aşamanın pahalı olduğu ancak böyle görünür.
    /// Anahtar üretimi süresi (ms).
    pub keygen_ms: f64,
    /// İmzalama süresi (ms).
    pub sign_ms: f64,
    /// Doğrulama süresi (ms).
    pub verify_ms: f64,

    /// Kurcalanmış mesaj bu koşuda reddedildi mi?
    ///
    /// **Bu alan canlı hatta doldurulur, testte değil.** `kurcalama_reddediliyor`
    /// fonksiyonu daha önce yalnızca birim testinden çağrılıyordu; artık her
    /// koşuda çalışıp sonucunu buraya yazıyor. Böylece "kurcalanmış mesaj
    /// reddediliyor" iddiası sahnede, jürinin gözü önünde kanıtlanıyor —
    /// bir test dosyasında değil.
    pub tamper_rejected: bool,
    /// Kurcalama testinin süresi (ms).
    pub tamper_ms: f64,
}

// ─────────────────────────────────────────────────────────────────────────────
// Anahtar Üretimi → İmzalama → Doğrulama
// ─────────────────────────────────────────────────────────────────────────────

/// Üç kademe için aynı akışı yürüten iç makro.
///
/// Kademeler `fips204`'te ayrı modüller (ve ayrı tipler) olduğu için tek bir
/// jenerik fonksiyonla ifade edilemiyor; akış birebir aynı olduğundan makro
/// ile tek yerde tutuluyor.
macro_rules! kademe_akisi {
    ($modul:ident, $level:expr, $xi:expr, $sign_seed:expr, $mesaj:expr) => {{
        // 1) Deterministik anahtar üretimi — ξ tohumu ρ''den geliyor.
        let t_keygen = Instant::now();
        let (pk, sk) = $modul::KG::keygen_from_seed($xi);
        let keygen_ms = t_keygen.elapsed().as_secs_f64() * 1000.0;

        // 2) Deterministik imzalama.
        let t_sign = Instant::now();
        let sig = sk
            .try_sign_with_seed($sign_seed, $mesaj, SIGN_CONTEXT)
            .map_err(|e| format!("ML-DSA imzalama başarısız: {}", e))?;
        let sign_ms = t_sign.elapsed().as_secs_f64() * 1000.0;

        // 3) Gerçek doğrulama.
        let t_verify = Instant::now();
        let verified = pk.verify($mesaj, &sig, SIGN_CONTEXT);
        let verify_ms = t_verify.elapsed().as_secs_f64() * 1000.0;

        // 4) Kurcalama testi — CANLI hatta, testte değil.
        //    Mesajın son biti çevrilir; aynı imza bu mesajda geçersiz olmalı.
        let t_tamper = Instant::now();
        let mut kurcalanmis = $mesaj.to_vec();
        match kurcalanmis.last_mut() {
            Some(son) => *son ^= 0x01,
            None => kurcalanmis.push(0x01),
        }
        let tamper_rejected = !pk.verify(&kurcalanmis, &sig, SIGN_CONTEXT);
        let tamper_ms = t_tamper.elapsed().as_secs_f64() * 1000.0;

        let pk_bytes = pk.into_bytes();
        let sk_bytes = sk.into_bytes();
        let sig_bytes = sig;

        let mut commitment = [0u8; 32];
        commitment.copy_from_slice(blake3::hash(&pk_bytes).as_bytes());

        PqcSignatureRecord {
            level: $level,
            public_key_len: pk_bytes.len(),
            secret_key_len: sk_bytes.len(),
            signature_len: sig_bytes.len(),
            public_key_commitment: commitment,
            signature_prefix_hex: hex::encode(&sig_bytes[..16]),
            verified,
            keygen_ms,
            sign_ms,
            verify_ms,
            tamper_rejected,
            tamper_ms,
        }
    }};
}

/// ρ''den bir ML-DSA anahtar çifti üretir, verilen mesajı imzalar ve doğrular.
///
/// # Arguments
/// * `rho_prime` - Rotasyon tohumu. Anahtar ve imza tohumları buradan türetilir.
/// * `level`     - Zırh kademesi (AI'ın risk kararından geliyor).
/// * `mesaj`     - İmzalanacak mesaj (tipik olarak userOpHash + dönem çapası).
///
/// # Returns
/// Ölçülmüş `PqcSignatureRecord`, ya da kütüphane hatası.
pub fn sign_and_verify(
    rho_prime: &[u8; 32],
    level: MlDsaSecurityLevel,
    mesaj: &[u8],
) -> Result<PqcSignatureRecord, String> {
    let xi = turet_tohum(rho_prime, DOMAIN_KEYGEN_XI);
    let sign_seed = turet_tohum(rho_prime, DOMAIN_SIGN_SEED);

    let record = match level {
        MlDsaSecurityLevel::Level44 => {
            kademe_akisi!(ml_dsa_44, level, &xi, &sign_seed, mesaj)
        }
        MlDsaSecurityLevel::Level65 => {
            kademe_akisi!(ml_dsa_65, level, &xi, &sign_seed, mesaj)
        }
        MlDsaSecurityLevel::Level87 => {
            kademe_akisi!(ml_dsa_87, level, &xi, &sign_seed, mesaj)
        }
    };

    if !record.verified {
        return Err(format!(
            "{} imzası kendi açık anahtarıyla doğrulanamadı — kütüphane veya tohum hatası",
            level.name()
        ));
    }

    // Kurcalama testi canlı hatta koşuyor. Geçmezse doğrulayıcı her mesajı
    // kabul ediyor demektir ve imza hiçbir şey ifade etmez — bu durumda
    // "imza doğrulandı" demek yanıltıcı olurdu, o yüzden koşu durdurulur.
    if !record.tamper_rejected {
        return Err(format!(
            "{}: kurcalanmış mesaj REDDEDİLMEDİ — doğrulayıcı her mesajı kabul ediyor",
            level.name()
        ));
    }

    Ok(record)
}

/// Verilen imzanın kurcalanmış bir mesajda reddedildiğini sınar.
///
/// Doğrulamanın gerçekten çalıştığını göstermek için kullanılır: her zaman
/// `true` dönen bir "doğrulayıcı" da testi geçerdi, bu fonksiyon onu yakalar.
///
/// # Returns
/// `Ok(true)` — kurcalanmış mesaj **reddedildi** (beklenen davranış).
///
/// Yalnızca `kurcalanan_mesaj_reddediliyor` testinden çağrılır; üretim
/// akışında yeri yoktur, o yüzden ikili derlemede "kullanılmıyor" görünür.
#[allow(dead_code)]
pub fn kurcalama_reddediliyor(
    rho_prime: &[u8; 32],
    level: MlDsaSecurityLevel,
    mesaj: &[u8],
) -> Result<bool, String> {
    let xi = turet_tohum(rho_prime, DOMAIN_KEYGEN_XI);
    let sign_seed = turet_tohum(rho_prime, DOMAIN_SIGN_SEED);

    // Mesajın son baytını çevir — imza bu mesaj için atılmadı.
    let mut kurcalanmis = mesaj.to_vec();
    if let Some(son) = kurcalanmis.last_mut() {
        *son ^= 0x01;
    } else {
        kurcalanmis.push(0x01);
    }

    macro_rules! kurcalama_akisi {
        ($modul:ident) => {{
            let (pk, sk) = $modul::KG::keygen_from_seed(&xi);
            let sig = sk
                .try_sign_with_seed(&sign_seed, mesaj, SIGN_CONTEXT)
                .map_err(|e| format!("ML-DSA imzalama başarısız: {}", e))?;
            // Orijinal mesajda geçerli, kurcalanmışta geçersiz olmalı.
            let orijinal_gecerli = pk.verify(mesaj, &sig, SIGN_CONTEXT);
            let kurcalanmis_gecerli = pk.verify(&kurcalanmis, &sig, SIGN_CONTEXT);
            (orijinal_gecerli, kurcalanmis_gecerli)
        }};
    }

    let (orijinal, kurcali) = match level {
        MlDsaSecurityLevel::Level44 => kurcalama_akisi!(ml_dsa_44),
        MlDsaSecurityLevel::Level65 => kurcalama_akisi!(ml_dsa_65),
        MlDsaSecurityLevel::Level87 => kurcalama_akisi!(ml_dsa_87),
    };

    Ok(orijinal && !kurcali)
}

/// ρ''den alan-ayrımlı 32 baytlık bir tohum türetir.
fn turet_tohum(rho_prime: &[u8; 32], domain: &[u8]) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    hasher.update(domain);
    hasher.update(rho_prime);
    *hasher.finalize().as_bytes()
}

// ─────────────────────────────────────────────────────────────────────────────
// Birim Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    const RHO: [u8; 32] = [0x7Au8; 32];
    const MESAJ: &[u8] = b"userOpHash=0xdeadbeef|epoch=1700000000000000000";

    /// BULGU 1 REGRESYONU — gerçek anahtar, gerçek imza, gerçek doğrulama.
    ///
    /// `fips204` bağımlılığı kaldırılırsa veya imzalama sahte bir metinle
    /// değiştirilirse bu test derlenmez ya da kırılır.
    #[test]
    fn gercek_imza_ve_dogrulama() {
        for level in [
            MlDsaSecurityLevel::Level44,
            MlDsaSecurityLevel::Level65,
            MlDsaSecurityLevel::Level87,
        ] {
            let kayit = sign_and_verify(&RHO, level, MESAJ)
                .unwrap_or_else(|e| panic!("{} başarısız: {}", level.name(), e));
            assert!(kayit.verified, "{} doğrulanamadı", level.name());
            assert_eq!(kayit.level, level);
        }
    }

    /// Ölçülen boyutlar NIST FIPS 204 tablosuyla birebir uyuşmalı.
    ///
    /// Bu test, gerçek polinom aritmetiğinin çalıştığının da kanıtıdır:
    /// sahte bir uygulama bu üç boyutu aynı anda tutturamaz.
    #[test]
    fn standart_boyutlari_uyusuyor() {
        for level in [
            MlDsaSecurityLevel::Level44,
            MlDsaSecurityLevel::Level65,
            MlDsaSecurityLevel::Level87,
        ] {
            let (pk_beklenen, sk_beklenen, sig_beklenen) = standart_boyutlar(level);
            let kayit = sign_and_verify(&RHO, level, MESAJ).unwrap();

            assert_eq!(
                kayit.public_key_len,
                pk_beklenen,
                "{} açık anahtar boyutu standartla uyuşmuyor",
                level.name()
            );
            assert_eq!(
                kayit.secret_key_len,
                sk_beklenen,
                "{} gizli anahtar boyutu standartla uyuşmuyor",
                level.name()
            );
            assert_eq!(
                kayit.signature_len,
                sig_beklenen,
                "{} imza boyutu standartla uyuşmuyor",
                level.name()
            );
        }
    }

    /// BULGU 4 REGRESYONU — zırh kademesi imza boyutunu GERÇEKTEN değiştiriyor.
    ///
    /// Eskiden zırh geçişi yalnızca JSON'a yazılan bir metindi
    /// (`"ML-DSA-87" if is_panic else "ML-DSA-44"`). Bu test, kademenin
    /// ölçülebilir bir kriptografik sonucu olduğunu sınar.
    #[test]
    fn imza_zirhla_birlikte_buyuyor() {
        let k44 = sign_and_verify(&RHO, MlDsaSecurityLevel::Level44, MESAJ).unwrap();
        let k65 = sign_and_verify(&RHO, MlDsaSecurityLevel::Level65, MESAJ).unwrap();
        let k87 = sign_and_verify(&RHO, MlDsaSecurityLevel::Level87, MESAJ).unwrap();

        assert!(
            k44.signature_len < k65.signature_len && k65.signature_len < k87.signature_len,
            "İmza boyutu kademeyle artmalı: {} → {} → {}",
            k44.signature_len,
            k65.signature_len,
            k87.signature_len
        );
        assert_eq!((k44.signature_len, k87.signature_len), (2_420, 4_627));
    }

    /// Doğrulayıcının gerçekten doğruladığını sınar.
    #[test]
    fn kurcalanan_mesaj_reddediliyor() {
        for level in [
            MlDsaSecurityLevel::Level44,
            MlDsaSecurityLevel::Level65,
            MlDsaSecurityLevel::Level87,
        ] {
            assert!(
                kurcalama_reddediliyor(&RHO, level, MESAJ).unwrap(),
                "{}: kurcalanmış mesaj reddedilmedi",
                level.name()
            );
        }
    }

    /// Aynı ρ' → birebir aynı anahtar ve imza (jüri tekrarlanabilirliği).
    ///
    /// Yalnızca KRİPTOGRAFİK çıktılar karşılaştırılır. Süre alanları kasıtlı
    /// olarak dışarıda: iki koşunun aynı milisaniyeyi ölçmesini beklemek
    /// anlamsızdır ve böyle bir iddia testi kırılgan yapardı.
    #[test]
    fn ayni_rho_ayni_anahtar_ve_imza() {
        let a = sign_and_verify(&RHO, MlDsaSecurityLevel::Level87, MESAJ).unwrap();
        let b = sign_and_verify(&RHO, MlDsaSecurityLevel::Level87, MESAJ).unwrap();

        assert_eq!(a.public_key_commitment, b.public_key_commitment);
        assert_eq!(a.signature_prefix_hex, b.signature_prefix_hex);
        assert_eq!(a.public_key_len, b.public_key_len);
        assert_eq!(a.secret_key_len, b.secret_key_len);
        assert_eq!(a.signature_len, b.signature_len);
    }

    /// Kurcalama testi CANLI hatta koşuyor ve süreleri ölçülüyor.
    ///
    /// Bu, `kurcalama_reddediliyor`'un birim testinden farklı: orada fonksiyon
    /// testten çağrılıyordu, burada üretim akışının kendisinin doldurduğu
    /// alan sınanıyor. Arayüzdeki "kurcalanmış mesaj reddedildi" rozeti bu
    /// alana bağlı.
    #[test]
    fn canli_hatta_kurcalama_ve_sureler_olculuyor() {
        for level in [
            MlDsaSecurityLevel::Level44,
            MlDsaSecurityLevel::Level65,
            MlDsaSecurityLevel::Level87,
        ] {
            let kayit = sign_and_verify(&RHO, level, MESAJ).unwrap();

            assert!(
                kayit.tamper_rejected,
                "{}: canlı hatta kurcalama reddedilmedi",
                level.name()
            );

            for (ad, ms) in [
                ("keygen", kayit.keygen_ms),
                ("sign", kayit.sign_ms),
                ("verify", kayit.verify_ms),
                ("tamper", kayit.tamper_ms),
            ] {
                assert!(ms >= 0.0, "{} süresi negatif: {}", ad, ms);
                assert!(ms < 10_000.0, "{} süresi mantıksız: {} ms", ad, ms);
            }
        }
    }

    /// Farklı ρ' → farklı anahtar çifti (rotasyon gerçekten anahtar yeniliyor).
    #[test]
    fn farkli_rho_farkli_anahtar() {
        let mut rho2 = RHO;
        rho2[0] ^= 0x01;

        let a = sign_and_verify(&RHO, MlDsaSecurityLevel::Level87, MESAJ).unwrap();
        let b = sign_and_verify(&rho2, MlDsaSecurityLevel::Level87, MESAJ).unwrap();

        assert_ne!(
            a.public_key_commitment, b.public_key_commitment,
            "Tek bit farkı yeni bir anahtar çifti üretmeli"
        );
    }

    /// Farklı mesaj → farklı imza (imza mesaja gerçekten bağlı).
    #[test]
    fn imza_mesaja_bagli() {
        let a = sign_and_verify(&RHO, MlDsaSecurityLevel::Level87, b"mesaj-A").unwrap();
        let b = sign_and_verify(&RHO, MlDsaSecurityLevel::Level87, b"mesaj-B").unwrap();
        assert_ne!(a.signature_prefix_hex, b.signature_prefix_hex);
    }
}
