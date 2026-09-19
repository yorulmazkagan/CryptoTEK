// =============================================================================
// Q-ADAPTIVE ZK — Zırh Kararı (src/armor.rs)
// =============================================================================
// Eşik kuralının TEK tanımı. Bu dosyadaki `decide` fonksiyonu, kriptografik
// katmanın tek karar noktasıdır ve Python tarafındaki `armor.py::decide` ile
// birebir aynı politikayı uygular.
//
// Neden bu modül var:
//   Önceden karar İKİ AYRI YERDE, İKİ AYRI KURALLA veriliyordu:
//     • Rust  : `if ai_risk_score > 90.0` — sabit, AI'dan habersiz eşik.
//     • Python: `risk_pct >= dynamic_threshold` — τ(t), kayan pencereden.
//
//   risk = 82, τ = 75 senaryosunda Python "panik" diyor, Rust ise 90'ı
//   aşmadığı için kanıt üretmeden çıkıyordu. API bunu hata saymıyor, diskteki
//   ESKİ `proof_payload.json`'ı okuyup yanıta koyuyordu. Yani sahnede
//   "bakın kanıt üretildi" denilen şey bayat bir dosya olabilirdi.
//
//   Bu sessiz hatanın kaynağı kuralın iki yerde olmasıydı. Çözüm: kural tek
//   yerde, τ dışarıdan argümanla geliyor, sabit yok.
//
// Tek yönlü tırmanma:
//   Zırh yalnızca YÜKSELEBİLİR. Manipüle edilmiş düşük bir risk skoru bile
//   kademeyi tabanın altına indiremez. Aynı kural zincirde de uygulanır
//   (QAdaptiveAccount._applyArmorUpdate).
// =============================================================================

use crate::trace::MlDsaSecurityLevel;

// ─────────────────────────────────────────────────────────────────────────────
// Politika Sabitleri
// ─────────────────────────────────────────────────────────────────────────────
//
// Bu üç sayı kuralın tamamıdır. Python tarafı aynı değerleri kullanır ve
// `test_layer_parity.py` her CI koşusunda iki katmanı karşılaştırır.

/// τ'nun bu kadar üstüne çıkan risk ML-DSA-87'yi tetikler.
pub const ESIK_ASIMI_L87: f64 = 15.0;

/// τ'nun bu kadar üstüne çıkan risk ML-DSA-65'i tetikler.
pub const ESIK_ASIMI_L65: f64 = 5.0;

/// τ verilmediğinde kullanılan varsayılan eşik.
///
/// **90.0 DEĞİLDİR** ve bilinçli olarak öyle seçilmiştir: eski sabit eşiğin
/// sessizce geri gelmesi hâlinde `varsayilan_tau_eski_sabit_degil` testi
/// kırılsın diye. τ'yu çağıran taraf (`--tau`) vermelidir; bu değer yalnızca
/// argümansız elle koşular için bir taban sağlar.
pub const VARSAYILAN_TAU: f64 = 75.0;

// ─────────────────────────────────────────────────────────────────────────────
// Karar Çıktısı
// ─────────────────────────────────────────────────────────────────────────────

/// Bir risk/τ çiftinin ürettiği zırh kararı.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArmorDecision {
    /// Uygulanacak ML-DSA kademesi.
    pub level: MlDsaSecurityLevel,
    /// STARK kanıtı üretilmeli mi?
    pub proof_required: bool,
    /// Zincire ve JSON'a yazılan durum metni.
    pub status: &'static str,
    /// Riskin τ'yu aşma miktarı (aşmıyorsa 0.0).
    pub asim: f64,
}

/// Panik durumunun metinsel karşılığı — JSON ve zincir tarafıyla paylaşılır.
pub const STATUS_PANIC: &str = "PANIC_MODE_ACTIVATED";
/// Normal durumun metinsel karşılığı.
pub const STATUS_NORMAL: &str = "NORMAL";

// ─────────────────────────────────────────────────────────────────────────────
// Karar Fonksiyonu — TEK KURAL
// ─────────────────────────────────────────────────────────────────────────────

/// Risk skoru, dinamik eşik ve taban kademeden zırh kararını üretir.
///
/// Kural:
/// ```text
///   risk <  τ            → taban kademe, kanıt üretilmez
///   risk >= τ            → panik; aşım miktarına göre kademe seçilir:
///                            aşım >= 15 → ML-DSA-87
///                            aşım >=  5 → ML-DSA-65
///                            aksi halde → ML-DSA-44
///   her durumda          → kademe taban kademenin altına DÜŞEMEZ
/// ```
///
/// # Arguments
/// * `risk`  - AI'ın ürettiği risk yüzdesi (0.0 – 100.0).
/// * `tau`   - Dinamik eşik τ(t). Kayan pencereden Python tarafında hesaplanır.
/// * `taban` - Hesabın mevcut taban zırhı; kademe bunun altına inemez.
pub fn decide(risk: f64, tau: f64, taban: MlDsaSecurityLevel) -> ArmorDecision {
    // NaN savunması: karşılaştırmalar NaN ile her zaman false döner, bu da
    // sessizce "normal" kararına düşmek demektir. Açıkça panik tarafına al.
    if risk.is_nan() || tau.is_nan() {
        return ArmorDecision {
            level: yukseği_al(MlDsaSecurityLevel::Level87, taban),
            proof_required: true,
            status: STATUS_PANIC,
            asim: 0.0,
        };
    }

    if risk < tau {
        return ArmorDecision {
            level: taban,
            proof_required: false,
            status: STATUS_NORMAL,
            asim: 0.0,
        };
    }

    let asim = risk - tau;

    let onerilen = if asim >= ESIK_ASIMI_L87 {
        MlDsaSecurityLevel::Level87
    } else if asim >= ESIK_ASIMI_L65 {
        MlDsaSecurityLevel::Level65
    } else {
        MlDsaSecurityLevel::Level44
    };

    ArmorDecision {
        level: yukseği_al(onerilen, taban),
        proof_required: true,
        status: STATUS_PANIC,
        asim,
    }
}

/// İki kademeden yüksek olanı döndürür — tek yönlü tırmanmanın uygulayıcısı.
fn yukseği_al(a: MlDsaSecurityLevel, b: MlDsaSecurityLevel) -> MlDsaSecurityLevel {
    if a.rank() >= b.rank() {
        a
    } else {
        b
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Birim Testleri
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    const TABAN: MlDsaSecurityLevel = MlDsaSecurityLevel::Level44;

    /// BULGU 3 REGRESYONU — sabit 90.0 eşiği artık yok.
    ///
    /// Denetimin yakaladığı tam senaryo: risk = 82, τ = 75.
    /// Eski Rust kodu `82 > 90` yanlış olduğu için "normal" diyordu ve kanıt
    /// üretmiyordu; Python ise aynı anda "panik" diyordu. Bu test, kararın
    /// τ'ya bağlı olduğunu ve iki katmanın aynı yanıtı verdiğini sabitler.
    #[test]
    fn bulgu3_esik_uyusmazligi_kapandi() {
        let karar = decide(82.0, 75.0, TABAN);
        assert!(karar.proof_required, "risk 82 > τ 75 iken kanıt üretilmeli");
        assert_eq!(karar.status, STATUS_PANIC);

        // Sabit 90.0 geri gelirse bu iki durum ayrışır:
        let hemen_altinda = decide(89.9, 75.0, TABAN);
        assert!(
            hemen_altinda.proof_required,
            "89.9 hâlâ τ'nun üstünde — 90.0 sabiti geri gelmiş olabilir"
        );
    }

    /// τ değişince kararın da değiştiğini sınar (τ gerçekten kullanılıyor mu).
    #[test]
    fn tau_karari_gercekten_etkiliyor() {
        assert!(decide(80.0, 75.0, TABAN).proof_required, "80 > 75 → panik");
        assert!(
            !decide(80.0, 85.0, TABAN).proof_required,
            "80 < 85 → normal"
        );
    }

    #[test]
    fn esik_tam_sinirda_panik_sayilir() {
        // risk == τ dahil edilir (>=), Python tarafı da öyle.
        let karar = decide(75.0, 75.0, TABAN);
        assert!(karar.proof_required);
        assert_eq!(karar.asim, 0.0);
        assert_eq!(karar.level, MlDsaSecurityLevel::Level44);
    }

    #[test]
    fn asim_kademeyi_belirliyor() {
        assert_eq!(decide(76.0, 75.0, TABAN).level, MlDsaSecurityLevel::Level44); // aşım 1
        assert_eq!(decide(80.0, 75.0, TABAN).level, MlDsaSecurityLevel::Level65); // aşım 5
        assert_eq!(decide(90.0, 75.0, TABAN).level, MlDsaSecurityLevel::Level87);
        // aşım 15
    }

    #[test]
    fn kademe_sinirlari_tam_degerlerde() {
        // Sınırlar kapalı aralık: >= 5 ve >= 15.
        assert_eq!(
            decide(79.99, 75.0, TABAN).level,
            MlDsaSecurityLevel::Level44
        );
        assert_eq!(decide(80.0, 75.0, TABAN).level, MlDsaSecurityLevel::Level65);
        assert_eq!(
            decide(89.99, 75.0, TABAN).level,
            MlDsaSecurityLevel::Level65
        );
        assert_eq!(decide(90.0, 75.0, TABAN).level, MlDsaSecurityLevel::Level87);
    }

    /// BULGU E4 REGRESYONU — zırh tabanın altına inemez.
    #[test]
    fn taban_altina_inilmiyor() {
        // Risk düşük, ama taban zaten 87 → 87'de kalmalı.
        let karar = decide(10.0, 75.0, MlDsaSecurityLevel::Level87);
        assert_eq!(karar.level, MlDsaSecurityLevel::Level87);
        assert!(!karar.proof_required, "düşük risk kanıt gerektirmez");

        // Panik var ama aşım küçük (44 önerirdi); taban 87 olduğu için 87.
        let panik = decide(76.0, 75.0, MlDsaSecurityLevel::Level87);
        assert_eq!(panik.level, MlDsaSecurityLevel::Level87);
    }

    #[test]
    fn tirmanma_tek_yonlu() {
        // Her taban için, her risk seviyesinde kademe asla tabanın altına inmez.
        for taban in [
            MlDsaSecurityLevel::Level44,
            MlDsaSecurityLevel::Level65,
            MlDsaSecurityLevel::Level87,
        ] {
            for risk in [0.0, 50.0, 75.0, 76.0, 82.0, 99.9] {
                let karar = decide(risk, 75.0, taban);
                assert!(
                    karar.level.rank() >= taban.rank(),
                    "risk={} taban={} iken kademe düştü: {}",
                    risk,
                    taban.name(),
                    karar.level.name()
                );
            }
        }
    }

    /// Varsayılan τ'nun eski sabit eşik OLMADIĞINI sabitler.
    #[test]
    fn varsayilan_tau_eski_sabit_degil() {
        assert_ne!(
            VARSAYILAN_TAU, 90.0,
            "Varsayılan τ 90.0'a döndü — bulgu 3 geri gelmiş olabilir"
        );
    }

    /// NaN sessizce "normal"e düşmemeli.
    #[test]
    fn nan_guvenli_tarafa_dusuyor() {
        let karar = decide(f64::NAN, 75.0, TABAN);
        assert!(karar.proof_required, "NaN risk panik tarafına alınmalı");
        assert_eq!(karar.level, MlDsaSecurityLevel::Level87);
    }
}
