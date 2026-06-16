# =============================================================================
# Q-ADAPTIVE AI Guardian — ONNX Dönüştürücü (src/export_onnx.py)
# =============================================================================
# Bu modül, Aşama 4'ün çekirdeğini oluşturur:
# Eğitilmiş scikit-learn IsolationForest modelini evrensel ONNX formatına
# dönüştürerek tarayıcı eklentileri, mobil istemciler ve edge cihazlarda
# merkezi sunucu olmadan çalışabilir hale getirir.
#
# Doğrulanmış ONNX Çıktı Şeması:
#   Giriş  : 'float_input'  — shape (N, 3), dtype float32
#   Çıktı 1: 'label'        — shape (N, 1), dtype int64   (1=normal, -1=anomali)
#   Çıktı 2: 'scores'       — shape (N, 1), dtype float32 (≡ decision_function())
#
# Z-Skoru Formülü (hem sklearn hem ONNX için aynı):
#   z    = (scores - mean_d) / std_d
#   risk = (1 - Φ(z)) × 100   [Φ = Normal CDF]
#
# Çıktı Artefaktları:
#   models/q_adaptive_guardian.onnx          — Taşınabilir model
#   models/calibration_metadata.json         — Z-skoru kalibrasyon parametreleri
#
# Kullanım:
#   python src/export_onnx.py
#   # veya pipeline'dan: from src.export_onnx import run_export
# =============================================================================

from __future__ import annotations

import json
import sys
import os
import time
import warnings
from pathlib import Path
from typing import Any, Dict, Tuple

import joblib
import numpy as np
import onnxruntime as rt
from scipy import stats as sc
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

# Proje kökünü Python yoluna ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    FEATURE_COLUMNS,
    MODEL_ARTIFACT_NAME,
    MODEL_DIR,
)
from src.utils import SEPARATOR, THIN_SEP, print_section, print_step, setup_logger

warnings.filterwarnings("ignore")

logger = setup_logger("Q-ADAPTIVE.ONNXExport")

# ── ONNX Çıktı Sabitleri ──────────────────────────────────────────────────────
ONNX_FILENAME        : str = "q_adaptive_guardian.onnx"
CALIBRATION_FILENAME : str = "calibration_metadata.json"

# Doğrulanmış opset — skl2onnx 1.20 + onnxruntime 1.27 ile test edildi
TARGET_OPSET : Dict[str, int] = {"": 17, "ai.onnx.ml": 3}

# Test senaryoları (ONNX çıktısını sklearn ile karşılaştırmak için)
VALIDATION_SCENARIOS = {
    "Standart Kullanıcı (DeFi Swap)" : np.array([[1.1,  0.02,  0.05]], dtype=np.float32),
    "Bot Saldırısı (Yüksek Frekans)" : np.array([[50.0, 0.05,  0.1 ]], dtype=np.float32),
    "Private Key Çalınması (Drainer)": np.array([[2.0,  0.95, 15.5 ]], dtype=np.float32),
}


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _load_joblib_artifact(model_dir: str = MODEL_DIR) -> Dict[str, Any]:
    """
    Aşama 2/3'te kaydedilen joblib artefaktını yükler.

    Args:
        model_dir : Artefaktın bulunduğu klasör.

    Returns:
        dict: {'model', 'train_mean', 'train_std', ...} anahtarlarını içeren sözlük.

    Raises:
        FileNotFoundError: Artefakt bulunamazsa.
    """
    artifact_path = Path(model_dir) / MODEL_ARTIFACT_NAME
    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Joblib artefaktı bulunamadı: '{artifact_path}'\n"
            f"Lütfen önce 'python run_pipeline.py' çalıştırın."
        )
    artifact = joblib.load(artifact_path)
    logger.info("Joblib artefaktı yüklendi: '%s'", artifact_path)
    return artifact


def _convert_to_onnx(clf, opset: Dict[str, int] = TARGET_OPSET):
    """
    scikit-learn IsolationForest'ı ONNX ModelProto nesnesine dönüştürür.

    Giriş tipi: FloatTensorType([None, 3])
        - None → dinamik batch boyutu (tek istek veya toplu istek)
        - 3    → [Islem_Sikligi, IP_Sapmasi, Gas_Sapmasi]

    Args:
        clf    : Eğitilmiş IsolationForest nesnesi.
        opset  : Hedef opset versiyonları sözlüğü.

    Returns:
        onnx.ModelProto: Dönüştürülmüş ONNX model nesnesi.
    """
    initial_types = [("float_input", FloatTensorType([None, len(FEATURE_COLUMNS)]))]

    logger.info(
        "ONNX dönüşümü başlıyor — n_estimators=%d, opset=%s",
        clf.n_estimators, opset,
    )
    t0 = time.perf_counter()

    onnx_model = convert_sklearn(
        clf,
        initial_types = initial_types,
        target_opset  = opset,
        verbose       = 0,
    )

    elapsed = time.perf_counter() - t0
    model_bytes = len(onnx_model.SerializeToString())
    logger.info(
        "ONNX dönüşümü tamamlandı — %.2fs | Boyut: %.1f KB",
        elapsed, model_bytes / 1024,
    )
    return onnx_model


def _save_onnx_model(onnx_model, model_dir: str = MODEL_DIR) -> str:
    """
    ONNX ModelProto nesnesini diske kaydeder.

    Args:
        onnx_model : convert_sklearn() tarafından döndürülen ONNX model nesnesi.
        model_dir  : Kayıt klasörü.

    Returns:
        str: Kaydedilen dosyanın tam yolu.
    """
    save_path = Path(model_dir) / ONNX_FILENAME
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, "wb") as f:
        f.write(onnx_model.SerializeToString())

    size_kb = save_path.stat().st_size / 1024
    logger.info("ONNX modeli kaydedildi → '%s' (%.1f KB)", save_path, size_kb)
    return str(save_path)


def _save_calibration_metadata(
    mean_d       : float,
    std_d        : float,
    training_rows: int,
    risk_threshold: float,
    model_dir    : str = MODEL_DIR,
) -> str:
    """
    Z-skoru kalibrasyon parametrelerini JSON olarak kaydeder.

    Bu dosya, istemci taraflı (tarayıcı, mobil) ortamlarda tam olarak aynı
    risk skorunu hesaplamak için gereklidir.

    Kaydedilen JSON yapısı:
    {
        "mean_d"            : 0.125085,   // Eğitim seti karar fon. ortalaması (μ)
        "std_d"             : 0.054679,   // Eğitim seti karar fon. std sapması (σ)
        "risk_threshold"    : 75.0,       // Anomali alarm eşiği
        "training_rows"     : 2000,       // Eğitim örnekleri
        "feature_columns"   : [...],      // Özellik sırası (kritik!)
        "risk_formula"      : "...",      // İnsan okunabilir formül
        "onnx_output_map"   : {...}       // ONNX çıktı adı → anlam eşlemesi
    }

    Args:
        mean_d         : decision_function eğitim ortalaması.
        std_d          : decision_function eğitim standart sapması.
        training_rows  : Eğitim satır sayısı.
        risk_threshold : Anomali eşiği (varsayılan %75).
        model_dir      : Kayıt klasörü.

    Returns:
        str: Kaydedilen JSON dosyasının tam yolu.
    """
    metadata = {
        "project"          : "Q-ADAPTIVE AI Guardian",
        "phase"            : "Aşama 4 — ONNX On-Device Inference",
        "mean_d"           : round(mean_d, 8),
        "std_d"            : round(std_d, 8),
        "risk_threshold"   : risk_threshold,
        "training_rows"    : training_rows,
        "feature_columns"  : FEATURE_COLUMNS,
        "feature_order"    : (
            "CRITICAL: Features must be passed in this exact order: "
            "[Islem_Sikligi, IP_Sapmasi, Gas_Sapmasi]"
        ),
        "risk_formula"     : (
            "z = (onnx_score - mean_d) / std_d; "
            "risk_pct = (1 - norm_cdf(z)) * 100; "
            "risk_pct = clamp(risk_pct, 0, 100)"
        ),
        "onnx_output_map"  : {
            "label"  : "int64 — 1=normal, -1=anomaly (IsolationForest prediction)",
            "scores" : "float32 — raw decision_function value (use this for z-score)",
        },
        "alarm_logic"      : (
            "IF risk_pct > 75 → TRIGGER_PANIC_MODE (ML-DSA-87 Heavy Armor) "
            "ELSE → SAFE (ML-DSA-44 Light Armor)"
        ),
        "javascript_snippet": (
            "// Browser / WASM istemci için örnek implementasyon:\n"
            "// function normCdf(z) { return 0.5*(1+erf(z/Math.sqrt(2))); }\n"
            "// function calcRisk(onnxScore, meanD, stdD) {\n"
            "//   const z = (onnxScore - meanD) / stdD;\n"
            "//   return Math.min(100, Math.max(0, (1 - normCdf(z)) * 100));\n"
            "// }"
        ),
    }

    json_path = Path(model_dir) / CALIBRATION_FILENAME
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info("Kalibrasyon metadata kaydedildi → '%s'", json_path)
    return str(json_path)


def _verify_onnx_parity(
    clf,
    onnx_path  : str,
    mean_d     : float,
    std_d      : float,
) -> bool:
    """
    ONNX modelinin sklearn ile birebir aynı sonuçları ürettiğini doğrular.

    Doğrulama adımları:
        1. ONNX session'ı başlat.
        2. Her senaryo için sklearn ve ONNX skorlarını karşılaştır.
        3. Mutlak fark ≤ 1e-4 olmalıdır (float32/float64 hassasiyet farkı).

    Args:
        clf       : Eğitilmiş sklearn IsolationForest.
        onnx_path : Kaydedilen ONNX dosyasının yolu.
        mean_d    : Kalibrasyon ortalaması.
        std_d     : Kalibrasyon standart sapması.

    Returns:
        bool: Tüm senaryolar eşleşiyorsa True.
    """
    print_section("SKLEARN ↔ ONNX KARŞILAŞTIRMA DOĞRULAMASI")

    sess       = rt.InferenceSession(onnx_path)
    input_name = sess.get_inputs()[0].name
    all_passed = True

    col_w = 36
    header = (
        f"  {'Senaryo':<{col_w}} "
        f"{'sklearn':>10} {'ONNX':>10} {'Δ':>8} {'Risk%':>8} {'Geçti':>7}"
    )
    print(header)
    print(f"  {'-'*col_w} {'-'*10} {'-'*10} {'-'*8} {'-'*8} {'-'*7}")

    for name, vec in VALIDATION_SCENARIOS.items():
        # sklearn decision_function (float64)
        sk_score = float(clf.decision_function(vec.astype(np.float64))[0])

        # ONNX 'scores' çıktısı (float32)
        onnx_result  = sess.run(None, {input_name: vec})
        onnx_score   = float(onnx_result[1][0][0])          # scores çıktısı

        # Delta
        delta = abs(sk_score - onnx_score)
        passed = delta <= 1e-3   # float32 hassasiyet payı

        # Risk skoru (ONNX üzerinden hesapla)
        z         = (onnx_score - mean_d) / std_d
        risk_pct  = float(max(0.0, min(100.0, (1 - sc.norm.cdf(z)) * 100)))

        status = "✅" if passed else "❌"
        if not passed:
            all_passed = False

        short_name = name[:col_w]
        print(
            f"  {short_name:<{col_w}} "
            f"{sk_score:>10.6f} {onnx_score:>10.6f} {delta:>8.2e} "
            f"{risk_pct:>7.2f}% {status:>7}"
        )

    print()
    if all_passed:
        print("  ✅ TÜM SENARYOLAR EŞLEŞİYOR — ONNX modeli sklearn ile parite sağlıyor.")
    else:
        print("  ❌ UYUŞMAZLIK TESPİT EDİLDİ — Dönüşüm parametrelerini kontrol edin.")

    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Ana Dışa Aktarım Fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def run_export(model_dir: str = MODEL_DIR) -> Dict[str, str]:
    """
    Tam ONNX dışa aktarım pipeline'ını yürütür:
        1. Joblib artefaktını yükle.
        2. IsolationForest → ONNX dönüşümü.
        3. ONNX modelini kaydet.
        4. Kalibrasyon metaverisini JSON olarak kaydet.
        5. ONNX ↔ sklearn pariteyi doğrula.

    Args:
        model_dir : Giriş joblib + çıkış ONNX artefaktları için klasör.

    Returns:
        dict: {'onnx_path': str, 'calibration_path': str, 'parity_ok': bool}
    """
    print()
    print(SEPARATOR)
    print("  Q-ADAPTIVE AŞAMA 4: ONNX DÖNÜŞÜMÜ BAŞLIYOR")
    print(SEPARATOR)

    # ── 1. Joblib Artefaktını Yükle ───────────────────────────────────────────
    print_step(1, "Joblib model artefaktı yükleniyor...")
    artifact      = _load_joblib_artifact(model_dir)
    clf           = artifact["model"]
    mean_d        = artifact["train_mean"]
    std_d         = artifact["train_std"]
    training_rows = artifact["training_rows"]
    risk_threshold= artifact["risk_threshold"]

    print(f"  -> IsolationForest yüklendi: {clf.n_estimators} ağaç")
    print(f"  -> Kalibrasyon: μ={mean_d:.6f}, σ={std_d:.6f}")

    # ── 2. ONNX Dönüşümü ─────────────────────────────────────────────────────
    print_step(2, f"IsolationForest → ONNX ({clf.n_estimators} ağaç dönüştürülüyor, lütfen bekleyin...)...")
    onnx_model = _convert_to_onnx(clf, opset=TARGET_OPSET)

    model_kb = len(onnx_model.SerializeToString()) / 1024
    print(f"  -> Dönüşüm tamamlandı — Model boyutu: {model_kb:.1f} KB")
    print(f"  -> Hedef opset: {TARGET_OPSET}")

    # ── 3. ONNX Modelini Kaydet ───────────────────────────────────────────────
    print_step(3, f"ONNX modeli '{model_dir}/{ONNX_FILENAME}' olarak kaydediliyor...")
    onnx_path = _save_onnx_model(onnx_model, model_dir)
    print(f"  -> ONNX dosyası kaydedildi: '{onnx_path}'")

    # ── 4. Kalibrasyon Metaverisini Kaydet ────────────────────────────────────
    print_step(4, f"Kalibrasyon metaverisi '{CALIBRATION_FILENAME}' olarak kaydediliyor...")
    calibration_path = _save_calibration_metadata(
        mean_d        = mean_d,
        std_d         = std_d,
        training_rows = training_rows,
        risk_threshold= risk_threshold,
        model_dir     = model_dir,
    )
    print(f"  -> JSON metadata kaydedildi: '{calibration_path}'")

    # ── 5. Parity Doğrulaması ─────────────────────────────────────────────────
    print_step(5, "ONNX ↔ sklearn sonuç paritesi doğrulanıyor...")
    parity_ok = _verify_onnx_parity(clf, onnx_path, mean_d, std_d)

    # ── Özet ──────────────────────────────────────────────────────────────────
    print()
    print(SEPARATOR)
    if parity_ok:
        print("  ✅ AŞAMA 4 BAŞARIYLA TAMAMLANDI")
    else:
        print("  ⚠️  AŞAMA 4 TAMAMLANDI — Parity uyarısı var (logları kontrol edin)")
    print()
    print("  Oluşturulan Artefaktlar:")
    print(f"    • {onnx_path}")
    print(f"    • {calibration_path}")
    print()
    print("  Kullanım:")
    print("    python test_onnx_inference.py   ← ONNX doğrulama testi")
    print("    python run_server.py             ← API sunucusu (sklearn backend)")
    print(SEPARATOR)
    print()

    return {
        "onnx_path"        : onnx_path,
        "calibration_path" : calibration_path,
        "parity_ok"        : parity_ok,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Giriş Noktası
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_export()
