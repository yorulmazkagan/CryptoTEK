# =============================================================================
# Q-ADAPTIVE AI Guardian — Pipeline Giriş Noktası (run_pipeline.py)
# =============================================================================
# Bu dosya Aşama 1 + Aşama 2'yi tek, tutarlı bir yürütme akışında birleştirir.
# Komut satırından çalıştırılır:
#
#   python run_pipeline.py
#
# Yürütme Adımları:
#   [ADIM 1] QDataSimulator başlatılır ve eğitim verisi üretilir/yüklenir.
#   [ADIM 2] IsolationForest modeli eğitilir.
#   [ADIM 3] 3 test senaryosu sırayla çalıştırılır; risk skorları ve
#            otonom sistem tepkileri gerçek zamanlı yazdırılır.
# =============================================================================

import sys
import os

# Proje kökünü Python yoluna ekle (paket bağımsız çalışabilmek için)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import glob
from pathlib import Path

import numpy as np
import pandas as pd

# ── Proje Modülleri ───────────────────────────────────────────────────────────
from src.data_engineering import QDataSimulator
from src.model import QAnomalyDetector
from src.utils import (
    SEPARATOR,
    THIN_SEP,
    print_banner,
    print_section,
    print_step,
    setup_logger,
)
from config import DATA_DIR, FEATURE_COLUMNS

logger = setup_logger("Q-ADAPTIVE.Pipeline")


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı: Mevcut En Yeni CSV'yi Yükle veya Yeniden Üret
# ─────────────────────────────────────────────────────────────────────────────

def _load_or_generate_training_data(simulator: QDataSimulator) -> pd.DataFrame:
    """
    data/ klasöründeki en son training CSV'yi yükler.
    Hiç CSV yoksa Aşama 1'i tekrar çalıştırarak yeni bir veri seti üretir.

    Args:
        simulator : QDataSimulator örneği.

    Returns:
        pd.DataFrame: Eğitim verisi.
    """
    csv_pattern = str(Path(DATA_DIR) / "training_data_normal_*.csv")
    existing_files = sorted(glob.glob(csv_pattern), reverse=True)

    if existing_files:
        latest_csv = existing_files[0]
        logger.info("Mevcut eğitim verisi yükleniyor: '%s'", latest_csv)
        df = pd.read_csv(latest_csv)
        print(f"  -> Mevcut CSV yüklendi: '{latest_csv}' ({len(df)} satır)")
        return df
    else:
        logger.warning("CSV bulunamadı. Aşama 1 tekrar çalıştırılıyor...")
        print("  -> CSV bulunamadı; veri yeniden üretiliyor...")
        dataset = simulator.generate_training_data(save=True)
        return dataset.dataframe


# ─────────────────────────────────────────────────────────────────────────────
# Ana Pipeline Fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Q-ADAPTIVE Aşama 1 + Aşama 2 + Aşama 3 (model kaydetme) pipeline'ını yürütür.

    İş akışı:
        1. Eğitim verisi üretilir veya mevcut CSV yüklenir.
        2. IsolationForest eğitilir ve models/ klasörüne kaydedilir.
        3. 3 test senaryosu çalıştırılır; risk skorları + otonom tepkiler yazdırılır.
    """

    # ── Açılış Banner'ı ───────────────────────────────────────────────────────
    print()
    print(SEPARATOR)
    print("  Q-ADAPTIVE: YAPAY ZEKA (İZOLE ORMAN) SİMÜLASYONU BAŞLIYOR...")
    print(SEPARATOR)

    # ─────────────────────────────────────────────────────────────────────────
    # ADIM 1: Veri Hazırlığı (Aşama 1 Entegrasyonu)
    # ─────────────────────────────────────────────────────────────────────────
    print_step(1, "Simülasyon Veri Seti Hazırlanıyor...")

    simulator  = QDataSimulator(data_dir=DATA_DIR)
    df_train   = _load_or_generate_training_data(simulator)

    # İlk 3 satır önizlemesi (PDF Bölüm 6 çıktısıyla birebir uyum)
    print(f"\n  -> {len(df_train)} adet 'Normal' kullanıcı işlemi hazır.")
    print()
    print(df_train.head(3).to_string())

    # ─────────────────────────────────────────────────────────────────────────
    # ADIM 2: Model Eğitimi (Aşama 2 — IsolationForest)
    # ─────────────────────────────────────────────────────────────────────────
    print_step(2, "Isolation Forest Modeli Eğitiliyor...")

    detector = QAnomalyDetector()
    detector.train(df_train)

    print("  -> Model başarıyla eğitildi ve profil çıkarma işlemi tamamlandı!")

    # ─────────────────────────────────────────────────────────────────────────
    # ADIM 2.5: Model Artefaktını Kaydet (Aşama 3 için FastAPI hazırlığı)
    # ─────────────────────────────────────────────────────────────────────────
    print_step("2.5", "Model artefaktı 'models/' klasörüne kaydediliyor...")
    artifact_path = detector.save()
    print(f"  -> Model artefaktı kaydedildi: '{artifact_path}'")
    print(f"  -> FastAPI sunucusu bu artefaktı yükleyecektir.")

    # Eğitilen model özeti
    detector.summary()

    # ─────────────────────────────────────────────────────────────────────────
    # ADIM 3: Test Senaryoları — Canlı Simülasyon
    # ─────────────────────────────────────────────────────────────────────────
    print_step(3, "Test Senaryoları (Canlı Simülasyon) Çalıştırılıyor...")

    # Aşama 1 simülatöründen senaryo vektörlerini al
    scenarios = simulator.get_test_scenarios()

    # Her senaryoyu sırayla çalıştır ve sonuçları yazdır
    results = detector.run_all_scenarios(scenarios)

    for idx, result in enumerate(results, start=1):
        detector.print_result(result, index=idx)

    # ─────────────────────────────────────────────────────────────────────────
    # Sonuç Özeti Tablosu
    # ─────────────────────────────────────────────────────────────────────────
    _print_summary_table(results)

    # ── Kapanış ───────────────────────────────────────────────────────────────
    print()
    print(SEPARATOR)
    print("  Q-ADAPTIVE SİMÜLASYONU BAŞARIYLA TAMAMLANDI.")
    print(SEPARATOR)
    print()
    print("  Sonraki adım → Aşama 3: FastAPI REST Servisi & MTD Entegrasyonu")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı: Sonuç Özet Tablosu
# ─────────────────────────────────────────────────────────────────────────────

def _print_summary_table(results: list) -> None:
    """
    Tüm senaryo sonuçlarını tek bir karşılaştırma tablosunda gösterir.

    Args:
        results : QAnomalyDetector.run_all_scenarios() çıktısı.
    """
    print_section("SONUÇ ÖZETİ — KARŞILAŞTIRMALI TABLO")

    rows = []
    for idx, r in enumerate(results, start=1):
        durum = "🔴 ALARM" if r.is_anomaly else "✅ Güvenli"
        zirh  = "AĞIR ZIRH (Dilithium-5)" if r.is_anomaly else "HAFİF ZIRH (ML-DSA-44)"
        rows.append({
            "#"         : idx,
            "Senaryo"   : r.scenario_name[:38],          # Tablo sığdırma
            "Risk %"    : f"{r.risk_score:.2f}%",
            "Ham Skor"  : f"{r.raw_score:.4f}",
            "Durum"     : durum,
            "PQC Zırh"  : zirh,
        })

    df_summary = pd.DataFrame(rows).set_index("#")
    print(df_summary.to_string())
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Giriş Noktası
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_pipeline()
