# =============================================================================
# Q-ADAPTIVE AI Guardian — Veri Mühendisliği Motoru (data_engineering.py)
# =============================================================================
# Bu modül, Q-ADAPTIVE projesinin Aşama 1 çekirdeğini oluşturur.
# QDataSimulator sınıfı; eğitim verisi üretimini, dışa aktarmayı ve
# Moving Target Defense (MTD) sistemine beslenecek test senaryolarını yönetir.
#
# Referans PDF: Q_ADAPTIVE_AI_Simulasyon_Rehberi.pdf
# Veri özellikleri:
#   - Islem_Sikligi : Saniyedeki işlem sayısı   (Normal: 1-2, Anomali: 50+)
#   - IP_Sapmasi    : Coğrafi IP sapması 0-1    (1.0 → imkânsız seyahat)
#   - Gas_Sapmasi   : Ağ ortalamasından Gas farkı (10-20x → saldırı)
# =============================================================================

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

# Proje içi bağımlılıklar
from config import (
    DATA_DIR,
    FEATURE_COLUMNS,
    NORMAL_LOC,
    NORMAL_SCALE,
    RANDOM_SEED,
    SCENARIOS,
    TRAINING_CSV,
    TRAIN_SAMPLE_SIZE,
)
from src.utils import (
    build_timestamped_filename,
    ensure_directory,
    print_section,
    print_step,
    setup_logger,
    validate_dataframe,
)

warnings.filterwarnings("ignore")

logger = setup_logger("Q-ADAPTIVE.DataEngineering")


# ─────────────────────────────────────────────────────────────────────────────
# Veri Sınıfı: Üretilmiş Veri Setinin Sarmalayıcısı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GeneratedDataset:
    """
    QDataSimulator.generate_training_data() tarafından döndürülen veri kabı.

    Attributes:
        dataframe  : Ham eğitim DataFrame'i.
        csv_path   : Kaydedilen CSV dosyasının tam yolu.
        num_rows   : Toplam satır sayısı.
        statistics : Özellik bazlı tanımlayıcı istatistikler.
    """
    dataframe : pd.DataFrame
    csv_path  : str
    num_rows  : int
    statistics: pd.DataFrame = field(default_factory=pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# Ana Sınıf: QDataSimulator
# ─────────────────────────────────────────────────────────────────────────────

class QDataSimulator:
    """
    Q-ADAPTIVE Moving Target Defense sistemi için sentetik veri üreticisi.

    Bu sınıf iki temel sorumluluğa sahiptir:

    1. **Eğitim Verisi Üretimi**: Gaussian dağılımına dayalı 'Normal'
       kullanıcı davranışını simüle eden 2000 satırlık bir veri seti oluşturur
       ve CSV olarak kalıcı hale getirir.

    2. **Test Senaryoları**: Modelin değerlendirileceği 3 farklı saldırı/normal
       senaryosunu temsil eden numpy dizileri döndürür.

    Kullanım:
        simulator = QDataSimulator()
        dataset   = simulator.generate_training_data()
        scenarios = simulator.get_test_scenarios()
    """

    # ── Sınıf Sabitleri ───────────────────────────────────────────────────────

    _SEED        : int  = RANDOM_SEED
    _SAMPLE_SIZE : int  = TRAIN_SAMPLE_SIZE
    _LOC         : List[float] = NORMAL_LOC
    _SCALE       : List[float] = NORMAL_SCALE
    _COLUMNS     : List[str]   = FEATURE_COLUMNS

    def __init__(self, data_dir: str = DATA_DIR) -> None:
        """
        QDataSimulator'ı başlatır.

        Args:
            data_dir : CSV çıktılarının kaydedileceği klasör yolu.
                       Klasör yoksa otomatik olarak oluşturulur.
        """
        self._data_dir: Path = ensure_directory(data_dir)
        logger.info(
            "QDataSimulator başlatıldı. Çıktı dizini: '%s'", self._data_dir
        )

    # ── Genel API ─────────────────────────────────────────────────────────────

    def generate_training_data(self, save: bool = True) -> GeneratedDataset:
        """
        Gaussian dağılımına göre 'Normal' kullanıcı davranışı verisi üretir.

        Matematiksel Parametreler (PDF Aşama 1 tanımına uygun):
            np.random.seed(42)
            np.random.normal(
                loc   = [1.5, 0.05, 0.1],
                scale = [0.5, 0.02, 0.05],
                size  = (2000, 3)
            )

        Args:
            save : True ise veriyi data/ klasörüne CSV olarak kaydeder.

        Returns:
            GeneratedDataset: Üretilen DataFrame ve meta verisini içeren nesne.
        """
        logger.info(
            "Eğitim verisi üretiliyor — %d satır, seed=%d",
            self._SAMPLE_SIZE, self._SEED,
        )

        # ── Çekirdek Veri Üretimi ─────────────────────────────────────────────
        np.random.seed(self._SEED)
        raw_array: np.ndarray = np.random.normal(
            loc   = self._LOC,
            scale = self._SCALE,
            size  = (self._SAMPLE_SIZE, 3),
        )

        # ── DataFrame Oluşturma ───────────────────────────────────────────────
        df = pd.DataFrame(raw_array, columns=self._COLUMNS)

        # Gerçekçilik kısıtı: IP sapması 0-1 aralığına sıkıştırılır
        df["IP_Sapmasi"] = df["IP_Sapmasi"].clip(lower=0.0, upper=1.0)

        # Gerçekçilik kısıtı: İşlem sıklığı ve Gas sapması negatif olamaz
        df["Islem_Sikligi"] = df["Islem_Sikligi"].clip(lower=0.0)
        df["Gas_Sapmasi"]   = df["Gas_Sapmasi"].clip(lower=0.0)

        # ── Doğrulama ─────────────────────────────────────────────────────────
        validate_dataframe(df, expected_columns=self._COLUMNS, min_rows=self._SAMPLE_SIZE)

        # ── CSV Kaydetme ──────────────────────────────────────────────────────
        csv_path: str = ""
        if save:
            csv_path = self._save_to_csv(df)

        statistics = df.describe()

        logger.info(
            "Eğitim verisi hazır: %d satır × %d özellik. CSV: '%s'",
            len(df), len(df.columns), csv_path or "kaydedilmedi",
        )

        return GeneratedDataset(
            dataframe  = df,
            csv_path   = csv_path,
            num_rows   = len(df),
            statistics = statistics,
        )

    def get_test_scenarios(self) -> Dict[str, np.ndarray]:
        """
        MTD motorunu test edecek 3 saldırı/normal senaryosunu döndürür.

        Senaryo tanımları (PDF Section 4'e uygun):
            Senaryo 1 — Standart Kullanıcı (DeFi Swap)  : [[1.1, 0.02, 0.05]]
            Senaryo 2 — Bot Saldırısı (Yüksek Frekans)  : [[50.0, 0.05, 0.1]]
            Senaryo 3 — Private Key Çalınması (Drainer)  : [[2.0, 0.95, 15.5]]

        Returns:
            Dict[str, np.ndarray]: Senaryo adı → numpy vektörü eşlemesi.
        """
        logger.info("Test senaryoları oluşturuluyor (%d senaryo)...", len(SCENARIOS))

        scenarios_as_arrays: Dict[str, np.ndarray] = {
            name: np.array(data, dtype=np.float64)
            for name, data in SCENARIOS.items()
        }

        logger.info("Test senaryoları hazır.")
        return scenarios_as_arrays

    # ── Özel Yardımcı Metodlar ────────────────────────────────────────────────

    def _save_to_csv(self, df: pd.DataFrame) -> str:
        """
        DataFrame'i zaman damgalı bir CSV olarak data/ klasörüne kaydeder.

        Args:
            df : Kaydedilecek pandas DataFrame.

        Returns:
            str: Kaydedilen dosyanın tam yolu.
        """
        filename  = build_timestamped_filename(
            base_name = TRAINING_CSV.replace(".csv", ""),
            extension = "csv",
        )
        full_path = self._data_dir / filename
        df.to_csv(full_path, index=False, float_format="%.6f")
        logger.info("CSV kaydedildi → '%s'", full_path)
        return str(full_path)

    def describe(self, dataset: GeneratedDataset) -> None:
        """
        Üretilen veri seti hakkında özet istatistikleri konsola yazdırır.

        Args:
            dataset : generate_training_data() tarafından döndürülen nesne.
        """
        print_section("VERİ SETİ ÖZET İSTATİSTİKLERİ")
        print(dataset.statistics.to_string())
        print()
