# =============================================================================
# Q-ADAPTIVE AI Guardian — ONNX Çıkarım Doğrulama Testi (test_onnx_inference.py)
# =============================================================================
# Bu betik, dışa aktarılan ONNX modelinin scikit-learn referans modeliyle
# tamamen aynı sonuçları ürettiğini kapsamlı biçimde doğrular.
#
# Doğrulama Adımları:
#   1. models/q_adaptive_guardian.onnx         → ONNXRuntime ile yükle
#   2. models/calibration_metadata.json        → Z-skoru parametrelerini al
#   3. 3 senaryo vektörünü ONNX session'a ver  → 'scores' çıktısını oku
#   4. Z-skoru formülünü uygula                → risk_pct hesapla
#   5. sklearn referans değerleriyle karşılaştır → parity doğrula
#   6. Karşılaştırma tablosunu ve sonucu yazdır
#
# Kullanım:
#   python test_onnx_inference.py
#
# Ön Koşul:
#   python run_pipeline.py       ← modeli eğit ve kaydet
#   python src/export_onnx.py    ← ONNX'e dönüştür
#
# ONNX Z-Skoru Risk Formülü (calibration_metadata.json'dan alınır):
#   z         = (onnx_score - mean_d) / std_d
#   risk_pct  = (1 - Φ(z)) × 100   [Φ = Normal CDF]
#   risk_pct  = clamp(risk_pct, 0, 100)
# =============================================================================

from __future__ import annotations

import json
import math
import sys
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import onnxruntime as rt
from scipy import stats as sc

# Proje kökünü Python yoluna ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils import SEPARATOR, THIN_SEP, print_section, setup_logger

logger = setup_logger("Q-ADAPTIVE.ONNXTest")

# ── Artefakt Yolları ──────────────────────────────────────────────────────────
MODELS_DIR         : str = "models"
ONNX_FILENAME      : str = "q_adaptive_guardian.onnx"
CALIBRATION_FILE   : str = "calibration_metadata.json"

ONNX_PATH          : str = str(Path(MODELS_DIR) / ONNX_FILENAME)
CALIBRATION_PATH   : str = str(Path(MODELS_DIR) / CALIBRATION_FILE)

# ── Test Senaryoları ──────────────────────────────────────────────────────────
# Sklearn referans değerleri: Aşama 2'de doğrulanmış sonuçlar
TEST_SCENARIOS: List[Dict[str, Any]] = [
    {
        "name"            : "Standart Kullanıcı (DeFi Swap İşlemi)",
        "vector"          : np.array([[1.1,  0.02,  0.05]], dtype=np.float32),
        "sklearn_risk_ref": 72.36,    # Aşama 2'de doğrulanmış referans değer
        "expected_action" : "SAFE",
        "expected_anomaly": False,
    },
    {
        "name"            : "Bot Saldırısı (Yüksek Frekanslı Spam)",
        "vector"          : np.array([[50.0, 0.05,  0.1 ]], dtype=np.float32),
        "sklearn_risk_ref": 98.52,
        "expected_action" : "TRIGGER_PANIC_MODE",
        "expected_anomaly": True,
    },
    {
        "name"            : "Private Key Çalınması (Drainer Saldırısı)",
        "vector"          : np.array([[2.0,  0.95, 15.5 ]], dtype=np.float32),
        "sklearn_risk_ref": 100.00,
        "expected_action" : "TRIGGER_PANIC_MODE",
        "expected_anomaly": True,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Matematiksel Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

def _norm_cdf_scipy(z: float) -> float:
    """
    SciPy'nin hassas Normal CDF implementasyonu.
    Sunucu tarafı doğrulama için kullanılır.
    """
    return float(sc.norm.cdf(z))


def _norm_cdf_approx(z: float) -> float:
    """
    Saf Python ile Normal CDF yaklaşımı — scipy gerektirmez.
    Tarayıcı (WASM/JS) istemci ortamları için JavaScript eşdeğerini gösterir.

    Hata fonksiyonu erf() kullanan formül:
        Φ(z) = 0.5 × (1 + erf(z / √2))

    Python'un math.erf() fonksiyonu, standart C99 erf() implementasyonudur.
    JavaScript'te Math.erf() yoktur — oraya özel polyfill gerekir.
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _calc_risk_score(onnx_score: float, mean_d: float, std_d: float) -> Tuple[float, float]:
    """
    ONNX 'scores' çıktısından Z-skoru ve risk yüzdesi hesaplar.

    Formül (calibration_metadata.json → risk_formula alanından):
        z        = (onnx_score - mean_d) / std_d
        risk_pct = (1 - Φ(z)) × 100
        risk_pct = clamp(risk_pct, 0.0, 100.0)

    Args:
        onnx_score : ONNX 'scores' çıktısının skaleri (float32 → float64).
        mean_d     : Eğitim seti decision_function ortalaması (μ).
        std_d      : Eğitim seti decision_function standart sapması (σ).

    Returns:
        Tuple[float, float]: (z_score, risk_pct)
    """
    z        = (onnx_score - mean_d) / std_d
    cdf_val  = _norm_cdf_scipy(z)          # Hassas hesaplama için scipy
    risk_pct = (1.0 - cdf_val) * 100.0
    risk_pct = max(0.0, min(100.0, risk_pct))
    return z, risk_pct


def _determine_action(risk_pct: float, threshold: float = 75.0) -> Tuple[str, str]:
    """
    Risk yüzdesine göre MTD eylemini ve PQC zırh profilini belirler.

    Args:
        risk_pct  : 0-100 arasında risk puanı.
        threshold : Anomali eşiği (varsayılan %75).

    Returns:
        Tuple[str, str]: (action, pqc_tier)
    """
    if risk_pct > threshold:
        return "TRIGGER_PANIC_MODE", "ML-DSA-87 (Heavy Armor)"
    return "SAFE", "ML-DSA-44 (Light Armor)"


# ─────────────────────────────────────────────────────────────────────────────
# Ön Koşul Kontrolü
# ─────────────────────────────────────────────────────────────────────────────

def _check_prerequisites() -> None:
    """
    ONNX ve kalibrasyon dosyalarının varlığını doğrular.

    Raises:
        SystemExit: Dosyalar eksikse açıklayıcı mesaj ile çıkar.
    """
    missing = []
    if not Path(ONNX_PATH).exists():
        missing.append(f"  • ONNX modeli bulunamadı: '{ONNX_PATH}'")
    if not Path(CALIBRATION_PATH).exists():
        missing.append(f"  • Kalibrasyon dosyası bulunamadı: '{CALIBRATION_PATH}'")

    if missing:
        print()
        print("=" * 65)
        print("  ❌ ÖN KOŞUL HATASI — Eksik Dosyalar:")
        for m in missing:
            print(m)
        print()
        print("  Çözüm — Sırayla çalıştırın:")
        print("    1. python run_pipeline.py     ← Modeli eğit & joblib'e kaydet")
        print("    2. python src/export_onnx.py  ← ONNX'e dönüştür")
        print("=" * 65)
        print()
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Ana Test Fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def run_onnx_inference_test() -> None:
    """
    ONNX modelini yükler, 3 test senaryosu çalıştırır ve sklearn ile karşılaştırır.
    """
    print()
    print(SEPARATOR)
    print("  Q-ADAPTIVE AŞAMA 4: ONNX ÇIKARIM DOĞRULAMA TESTİ")
    print(SEPARATOR)

    # ── Ön Koşul Kontrolü ─────────────────────────────────────────────────────
    _check_prerequisites()

    # ── 1. Kalibrasyon Metaverisini Yükle ─────────────────────────────────────
    print()
    print("[ADIM 1] Kalibrasyon metadata yükleniyor...")
    with open(CALIBRATION_PATH, encoding="utf-8") as f:
        meta = json.load(f)

    mean_d         = float(meta["mean_d"])
    std_d          = float(meta["std_d"])
    risk_threshold = float(meta["risk_threshold"])
    feature_cols   = meta["feature_columns"]

    print(f"  -> μ (mean_d)       : {mean_d:.8f}")
    print(f"  -> σ (std_d)        : {std_d:.8f}")
    print(f"  -> Risk Eşiği       : %{risk_threshold}")
    print(f"  -> Özellik Sırası   : {feature_cols}")
    print(f"  -> Formül           : {meta['risk_formula']}")

    # ── 2. ONNX Session Başlat ────────────────────────────────────────────────
    print()
    print("[ADIM 2] ONNXRuntime InferenceSession başlatılıyor...")
    t0 = time.perf_counter()
    sess = rt.InferenceSession(ONNX_PATH)
    load_ms = (time.perf_counter() - t0) * 1000

    input_name   = sess.get_inputs()[0].name
    input_shape  = sess.get_inputs()[0].shape
    output_names = [o.name for o in sess.get_outputs()]

    print(f"  -> ONNX dosyası     : '{ONNX_PATH}'")
    print(f"  -> Giriş adı        : '{input_name}' — shape {input_shape}")
    print(f"  -> Çıktı adları     : {output_names}")
    print(f"  -> Yükleme süresi   : {load_ms:.2f} ms")
    print(f"  -> ONNXRuntime ver. : {rt.__version__}")

    # ── 3. Senaryo Çıkarımları ─────────────────────────────────────────────────
    print()
    print("[ADIM 3] Test senaryoları ONNX üzerinden çalıştırılıyor...")
    print(THIN_SEP)

    results_log = []

    for idx, scenario in enumerate(TEST_SCENARIOS, start=1):
        name      = scenario["name"]
        vector    = scenario["vector"]
        sk_ref    = scenario["sklearn_risk_ref"]
        exp_action= scenario["expected_action"]

        # ── ONNX Çıkarımı ─────────────────────────────────────────────────────
        t_infer = time.perf_counter()
        onnx_outputs = sess.run(None, {input_name: vector})
        infer_ms = (time.perf_counter() - t_infer) * 1000

        onnx_label = int(onnx_outputs[0][0][0])   # 'label': 1=normal, -1=anomali
        onnx_score = float(onnx_outputs[1][0][0]) # 'scores': decision_function eşdeğeri

        # ── Risk Skoru Hesabı ─────────────────────────────────────────────────
        z_score, risk_pct = _calc_risk_score(onnx_score, mean_d, std_d)

        # Scipy ile karşılaştırma için alternatif hesap (approx)
        z_approx     = z_score
        cdf_approx   = _norm_cdf_approx(z_approx)
        risk_approx  = max(0.0, min(100.0, (1.0 - cdf_approx) * 100.0))

        # ── Eylem Kararı ──────────────────────────────────────────────────────
        action, pqc_tier = _determine_action(risk_pct, risk_threshold)
        action_match = (action == exp_action)

        # ── Sklearn ile Fark ──────────────────────────────────────────────────
        delta_risk   = abs(risk_pct - sk_ref)
        parity_ok    = delta_risk <= 0.5   # ≤ 0.5% float32 hassasiyet toleransı

        results_log.append({
            "name"         : name,
            "onnx_score"   : onnx_score,
            "onnx_label"   : onnx_label,
            "z_score"      : z_score,
            "risk_pct"     : risk_pct,
            "risk_approx"  : risk_approx,
            "sk_ref"       : sk_ref,
            "delta_risk"   : delta_risk,
            "action"       : action,
            "pqc_tier"     : pqc_tier,
            "action_match" : action_match,
            "parity_ok"    : parity_ok,
            "infer_ms"     : infer_ms,
        })

        # ── Detaylı Çıktı ─────────────────────────────────────────────────────
        print(f"\n  --- Senaryo {idx}: {name} ---")
        print(f"  Giriş Vektörü     : {vector.tolist()}")
        print(f"  ONNX 'label'      : {onnx_label}  (1=normal, -1=anomali)")
        print(f"  ONNX 'scores'     : {onnx_score:.8f}  (≡ decision_function)")
        print(f"  Z-Skoru           : {z_score:.6f}")
        print(f"  Risk (scipy CDF)  : %{risk_pct:.4f}")
        print(f"  Risk (math.erf)   : %{risk_approx:.4f}  ← WASM/Browser eşdeğeri")
        print(f"  sklearn Referans  : %{sk_ref:.2f}")
        print(f"  Δ Risk            : {delta_risk:.4f}%  {'✅' if parity_ok else '❌'}")
        print(f"  Çıkarım Süresi    : {infer_ms:.3f} ms")
        print(f"  Eylem             : {action}")
        print(f"  PQC Zırh          : {pqc_tier}")
        print(f"  Eylem Doğru mu?   : {'✅' if action_match else '❌'} (beklenen: {exp_action})")

    # ── 4. Karşılaştırma Tablosu ───────────────────────────────────────────────
    print()
    print_section("SKLEARN ↔ ONNX KARŞILAŞTIRMALI ÖZET TABLO")

    col = 38
    print(f"  {'Senaryo':<{col}} {'sklearn%':>9} {'ONNX%':>8} {'Δ%':>7} {'Eylem':<22} {'Süre':>7} {'OK':>4}")
    print(f"  {'-'*col} {'-'*9} {'-'*8} {'-'*7} {'-'*22} {'-'*7} {'-'*4}")

    all_parity  = True
    all_action  = True
    total_ms    = 0.0

    for r in results_log:
        parity_sym = "✅" if r["parity_ok"]   else "❌"
        action_sym = "✅" if r["action_match"] else "❌"
        combined   = "✅" if (r["parity_ok"] and r["action_match"]) else "❌"

        if not r["parity_ok"]:   all_parity = False
        if not r["action_match"]: all_action = False
        total_ms += r["infer_ms"]

        short = r["name"][:col]
        print(
            f"  {short:<{col}} "
            f"{r['sk_ref']:>8.2f}% "
            f"{r['risk_pct']:>7.2f}% "
            f"{r['delta_risk']:>6.3f}% "
            f"{r['action']:<22} "
            f"{r['infer_ms']:>6.2f}ms "
            f"{combined:>4}"
        )

    print()

    # ── 5. Genel Değerlendirme ────────────────────────────────────────────────
    avg_ms = total_ms / len(results_log)
    overall_ok = all_parity and all_action

    print(SEPARATOR)
    if overall_ok:
        print("  ✅ TÜM TESTLER BAŞARILI")
        print("  ONNX modeli sklearn ile tam parity sağlıyor.")
        print("  Model tarayıcı / mobil / edge dağıtımına hazır! 🚀")
    else:
        print("  ⚠️  BAZI TESTLER BAŞARISIZ")
        if not all_parity:
            print("  → Risk skoru paritesi: ❌ (Δ > 0.5%)")
        if not all_action:
            print("  → Eylem eşleşmesi: ❌")

    print()
    print(f"  Toplam Senaryo      : {len(results_log)}")
    print(f"  Ortalama Çıkarım    : {avg_ms:.3f} ms (sunucu gecikmesi yok!)")
    print(f"  ONNX Modeli         : {ONNX_PATH}")
    print(f"  Kalibrasyon JSON    : {CALIBRATION_PATH}")
    print(SEPARATOR)
    print()

    sys.exit(0 if overall_ok else 1)


# ─────────────────────────────────────────────────────────────────────────────
# Giriş Noktası
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_onnx_inference_test()
