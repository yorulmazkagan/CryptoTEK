# =============================================================================
# Q-ADAPTIVE AI Guardian — Configuration Package
# =============================================================================
# Bu modül, projenin merkezi yapılandırma sabitlerini barındırır.
# Aşama 1: Altyapı ve Veri Seti Mühendisliği
# =============================================================================

# ── Veri Üretimi Sabitleri ──────────────────────────────────────────────────
RANDOM_SEED: int = 42          # Mutlak yeniden üretilebilirlik için sabit seed
TRAIN_SAMPLE_SIZE: int = 2000  # Eğitim veri seti satır sayısı

# Normal davranış dağılımı parametreleri (Gaussian)
NORMAL_LOC    = [1.5, 0.05, 0.1]    # Ortalama: [Islem_Sikligi, IP_Sapmasi, Gas_Sapmasi]
NORMAL_SCALE  = [0.5, 0.02, 0.05]   # Std. Sapma

# ── Feature Sütun İsimleri ──────────────────────────────────────────────────
FEATURE_COLUMNS = ["Islem_Sikligi", "IP_Sapmasi", "Gas_Sapmasi"]

# ── Çıktı Yolları ───────────────────────────────────────────────────────────
DATA_DIR         = "data"
TRAINING_CSV     = "training_data_normal.csv"

# ── Model Kalıcılığı (Aşama 3) ───────────────────────────────────────────────────
MODEL_DIR            = "models"
MODEL_ARTIFACT_NAME  = "q_adaptive_isolation_forest.joblib"  # Serileştirilmiş model

# ── ONNX Artefaktları (Aşama 4) ───────────────────────────────────────────────
ONNX_MODEL_NAME      = "q_adaptive_guardian.onnx"            # On-device çıkarım modeli
CALIBRATION_JSON     = "calibration_metadata.json"           # Z-skoru kalibrasyon parametreleri

# ── Test Senaryoları ────────────────────────────────────────────────────────
# Her senaryo, modele gerçek zamanlı beslenecek bir işlem vektörüdür.
SCENARIOS = {
    "Standart Kullanıcı (DeFi Swap İşlemi)": [[1.1, 0.02, 0.05]],
    "Bot Saldırısı (Yüksek Frekanslı Spam)": [[50.0, 0.05, 0.1]],
    "Private Key Çalınması (Farklı IP ve Fahiş Gas Fee)": [[2.0, 0.95, 15.5]],
}
