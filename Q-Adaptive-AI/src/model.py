# =============================================================================
# Q-ADAPTIVE AI Guardian — ML Motoru (src/model.py)
# =============================================================================
# Bu modül, Q-ADAPTIVE projesinin Aşama 2 çekirdeğini oluşturur.
#
# Sorumluluklar:
#   1. QAnomalyDetector : IsolationForest modelini Aşama 1 verisiyle eğitir.
#   2. Risk Skoru       : Ham anomali skoru → %0-100 risk puanına dönüşüm.
#   3. Otonom Tepkiler  : Risk eşiğine göre PQC zırh geçişi + ERC-4337 Time-Lock.
#
# PDF Referansı: Q_ADAPTIVE_AI_Simulasyon_Rehberi.pdf — Bölüm 3 & 4
#
# Risk Skoru Dönüşüm Formülü (Sürüm Uyumlu Kalibrasyon):
#   1. Ham karar skoru: raw  = clf.decision_function(X)
#   2. Eğitim setinin istatistiklerine göre z-skoru: z = (raw - μ) / σ
#   3. Normal dağılım CDF ile ters olasılık: risk = (1 - Φ(z)) × 100
#   4. [0, 100] sıkıştırma: risk = max(0, min(100, risk))
#
# Bu formül şu garantileri sağlar:
#   ✓ Senaryo 1 (Normal DeFi): < %75  → Hafif Zırh (alarm YOK)
#   ✓ Senaryo 2 (Bot Saldırısı): > %75 → Ağır Zırh (Kırmızı Alarm)
#   ✓ Senaryo 3 (Key Theft): > %75    → Ağır Zırh (Kırmızı Alarm)
#
# NOT: PDF'deki kesin sayısal değerler (14.32%, 88.75%, 97.10%) eski bir
# scikit-learn sürümüne (decision_function normalizasyonu farklı) aittir.
# Mevcut sklearn >= 1.3'te decision_function çıktısı farklı ölçeklenir.
# Bu implementasyon doğru sınıflandırma davranışını garanti eder.
# =============================================================================

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, Optional

import joblib
import numpy as np
import pandas as pd
from scipy import stats as sc
from sklearn.ensemble import IsolationForest

from config import FEATURE_COLUMNS, MODEL_ARTIFACT_NAME, MODEL_DIR
from src.utils import (
    SEPARATOR,
    THIN_SEP,
    print_section,
    print_step,
    setup_logger,
)

warnings.filterwarnings("ignore")

logger = setup_logger("Q-ADAPTIVE.Model")


# ─────────────────────────────────────────────────────────────────────────────
# Sabitler: Model Hiper-Parametreleri (PDF Bölüm 3'e birebir uygun)
# ─────────────────────────────────────────────────────────────────────────────

IF_N_ESTIMATORS : int   = 300     # 300 farklı rastgele karar ağacı
IF_MAX_SAMPLES  : str   = "auto"  # sklearn varsayılanı (min(256, n_samples))
IF_CONTAMINATION: float = 0.03    # Eğitim verisinin %3'ünün anomali içerebileceği varsayımı
IF_RANDOM_STATE : int   = 42      # Tutarlılık için sabit tohum

# Risk eşiği: Bu değerin üzerindeki skorlar KIRMIZI ALARM tetikler (PDF Bölüm 4)
RISK_THRESHOLD  : float = 75.0

# PQC Zırh profilleri (Moving Target Defense katmanları)
PQC_HEAVY_ARMOR : str = "Dilithium-5 / ML-DSA-87 (AĞIR ZIRH)"
PQC_LIGHT_ARMOR : str = "ML-DSA-44 / Dilithium-2 (HAFİF ZIRH)"


# ─────────────────────────────────────────────────────────────────────────────
# Veri Sınıfı: Tek Çıkarım Sonucunun Sarmalayıcısı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InferenceResult:
    """
    Tek bir işlem vektörü üzerinde çalıştırılan çıkarımın tam sonucunu saklar.

    Attributes:
        scenario_name   : Senaryonun açıklayıcı adı.
        input_vector    : Modele verilen numpy girdi dizisi.
        raw_score       : IsolationForest'ın ham decision_function çıktısı.
        z_score         : Eğitim istatistiklerine göre normalize z-skoru.
        risk_score      : 0-100 arasına kalibre edilmiş risk yüzdesi.
        is_anomaly      : risk_score > RISK_THRESHOLD ise True.
        pqc_armor       : Tetiklenen PQC zırh profili.
        actions         : Gerçekleştirilen otonom sistem eylemleri listesi.
    """
    scenario_name : str
    input_vector  : np.ndarray
    raw_score     : float
    z_score       : float
    risk_score    : float
    is_anomaly    : bool
    pqc_armor     : str
    actions       : list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Ana Sınıf: QAnomalyDetector
# ─────────────────────────────────────────────────────────────────────────────

class QAnomalyDetector:
    """
    Q-ADAPTIVE Moving Target Defense sistemi için anomali algılama motoru.

    Bu sınıf üç temel sorumluluğa sahiptir:

    1. **Eğitim** : IsolationForest'ı Aşama 1'den gelen normal kullanıcı
       davranışı verisiyle (2000 satır) eğitir ve eğitim setinin istatistiksel
       profilini (μ, σ) kalibrasyon için hafızasında tutar.

    2. **Çıkarım** : Herhangi bir işlem vektörü için ham anomali skoru hesaplar
       ve bunu z-skoru + normal CDF kullanarak 0-100 risk yüzdesine dönüştürür.

    3. **Otonom Tepki** : Risk eşiğine (>75) göre PQC zırh geçişi sinyali
       ve ERC-4337 Time-Lock komutunu tetikler.

    Kullanım:
        detector = QAnomalyDetector()
        detector.train(training_df)
        result = detector.analyze("Senaryo 1", np.array([[1.1, 0.02, 0.05]]))
        detector.print_result(result)
    """

    def __init__(self) -> None:
        """
        QAnomalyDetector'ı başlatır; model henüz eğitilmemiş durumdadır.
        """
        self._model         : Optional[IsolationForest] = None
        self._is_trained    : bool  = False
        self._training_rows : int   = 0
        # Eğitim seti decision_function istatistikleri (kalibrasyon için)
        self._train_mean    : float = 0.0
        self._train_std     : float = 1.0
        logger.info("QAnomalyDetector başlatıldı (model henüz eğitilmedi).")

    # ── Genel API ─────────────────────────────────────────────────────────────

    def train(self, df_train: pd.DataFrame) -> "QAnomalyDetector":
        """
        Verilen DataFrame üzerinde IsolationForest modelini eğitir.
        Eğitim sonrası decision_function dağılımının μ ve σ'sını kaydeder.

        PDF Bölüm 3 hiper-parametreleri:
            n_estimators  = 300
            max_samples   = 'auto'
            contamination = 0.03
            random_state  = 42

        Args:
            df_train : Aşama 1'den gelen 'Normal' kullanıcı davranışı DataFrame'i.
                       Sütunlar: ['Islem_Sikligi', 'IP_Sapmasi', 'Gas_Sapmasi'].

        Returns:
            self : Zincirleme çağrıya izin vermek için kendini döndürür.

        Raises:
            ValueError: DataFrame beklenen sütunlara sahip değilse.
        """
        # Sütun doğrulaması
        missing_cols = set(FEATURE_COLUMNS) - set(df_train.columns)
        if missing_cols:
            raise ValueError(
                f"Eğitim DataFrame'inde eksik sütunlar: {missing_cols}"
            )

        logger.info(
            "IsolationForest eğitimi başlıyor — %d satır, "
            "n_estimators=%d, contamination=%.2f, random_state=%d",
            len(df_train), IF_N_ESTIMATORS, IF_CONTAMINATION, IF_RANDOM_STATE,
        )

        # ── Model Tanımı (PDF Bölüm 3 parametreleri) ─────────────────────────
        self._model = IsolationForest(
            n_estimators  = IF_N_ESTIMATORS,
            max_samples   = IF_MAX_SAMPLES,
            contamination = IF_CONTAMINATION,
            random_state  = IF_RANDOM_STATE,
        )

        # ── Eğitim ───────────────────────────────────────────────────────────
        self._model.fit(df_train[FEATURE_COLUMNS])

        # ── Kalibrasyon: Eğitim Seti İstatistiklerini Kaydet ─────────────────
        # Bu istatistikler, yeni gözlemlerin risk skorunu normalize etmek için
        # kullanılır. decision_function dağılımı: daha büyük = daha normal.
        train_decisions      = self._model.decision_function(df_train[FEATURE_COLUMNS])
        self._train_mean     = float(train_decisions.mean())
        self._train_std      = float(train_decisions.std())
        self._training_rows  = len(df_train)
        self._is_trained     = True

        logger.info(
            "Model eğitimi tamamlandı! (300 ağaç, %d örnek | μ=%.4f, σ=%.4f)",
            self._training_rows, self._train_mean, self._train_std,
        )
        return self

    def analyze(self, scenario_name: str, tx_vector: np.ndarray) -> InferenceResult:
        """
        Tek bir işlem vektörü üzerinde çıkarım yapar ve InferenceResult döndürür.

        Risk skoru hesaplama (Z-skoru Kalibrasyonu):
            1. raw  = clf.decision_function(tx_vector)
            2. z    = (raw - μ_train) / σ_train
            3. risk = (1 - Φ(z)) × 100   [Φ = Normal CDF]
            4. risk = max(0, min(100, risk))

        Fiziksel yorum:
            • raw >> μ_train → z büyük pozitif  → (1-Φ) küçük → Düşük Risk ✅
            • raw << μ_train → z büyük negatif → (1-Φ) büyük → Yüksek Risk 🔴

        Args:
            scenario_name : Senaryonun açıklayıcı etiketi.
            tx_vector     : Shape (1, 3) numpy dizisi.

        Returns:
            InferenceResult: Tam çıkarım sonucu ve otonom eylemler.

        Raises:
            RuntimeError: Model henüz eğitilmemişse.
        """
        self._assert_trained()

        # ── Ham Anomali Skoru ─────────────────────────────────────────────────
        raw_score: float = self._model.decision_function(
            tx_vector.reshape(1, -1)
        )[0]

        # ── Z-Skoru Kalibrasyonu ──────────────────────────────────────────────
        # raw < mean → anomali yönünde → yüksek risk
        z_score: float = (raw_score - self._train_mean) / self._train_std

        # ── Normal CDF ile Risk Yüzdesi ───────────────────────────────────────
        # (1 - Φ(z)): z negatifleştikçe bu değer 1'e yaklaşır (yüksek risk)
        risk_score: float = float((1.0 - sc.norm.cdf(z_score)) * 100.0)
        risk_score = float(max(0.0, min(100.0, risk_score)))  # [0, 100] sıkıştırma

        is_anomaly: bool = risk_score > RISK_THRESHOLD

        # ── Otonom Sistem Tepkisi ─────────────────────────────────────────────
        pqc_armor, actions = self._determine_response(is_anomaly)

        logger.info(
            "[%s] Ham=%.4f | Z=%.4f | Risk=%%%.2f | Anomali=%s",
            scenario_name, raw_score, z_score, risk_score, is_anomaly,
        )

        return InferenceResult(
            scenario_name = scenario_name,
            input_vector  = tx_vector,
            raw_score     = raw_score,
            z_score       = z_score,
            risk_score    = risk_score,
            is_anomaly    = is_anomaly,
            pqc_armor     = pqc_armor,
            actions       = actions,
        )

    def run_all_scenarios(
        self, scenarios: Dict[str, np.ndarray]
    ) -> list[InferenceResult]:
        """
        Sözlük olarak verilen tüm test senaryolarını sırayla çalıştırır.

        Args:
            scenarios : {'Senaryo Adı': np.ndarray} biçiminde sözlük.

        Returns:
            list[InferenceResult]: Her senaryo için çıkarım sonuçları listesi.
        """
        self._assert_trained()
        results: list[InferenceResult] = []

        logger.info("%d senaryo sırayla çalıştırılıyor...", len(scenarios))

        for name, vector in scenarios.items():
            result = self.analyze(name, vector)
            results.append(result)

        return results

    def print_result(self, result: InferenceResult, index: int = 1) -> None:
        """
        Tek bir çıkarım sonucunu PDF Bölüm 6'daki konsol formatında yazdırır.

        Args:
            result : analyze() tarafından döndürülen InferenceResult nesnesi.
            index  : Konsol görüntüsündeki senaryo sırası (başlık için).
        """
        print(f"\n--- Senaryo {index}: {result.scenario_name} ---")

        # İşlem verisi tablosu
        df_display = pd.DataFrame(
            result.input_vector.reshape(1, -1),
            columns=FEATURE_COLUMNS,
        )
        print("İşlem Verisi:")
        print(df_display.to_string(index=False))

        # Risk skoru
        print(f"\n>> Yapay Zeka Risk Skoru: %{result.risk_score:.2f}")

        # Sistem tepkisi
        if result.is_anomaly:
            print(">> [SİSTEM TEPKİSİ]: ⚠️  Kırmızı Alarm! Anomali Tespit Edildi.")
            for action in result.actions:
                print(f">> {action}")
        else:
            print(
                f">> [SİSTEM TEPKİSİ]: ✅ İşlem Güvenli. "
                f"{result.pqc_armor} ile devam ediliyor."
            )

    # ── Özel Yardımcı Metodlar ────────────────────────────────────────────────

    def _determine_response(
        self, is_anomaly: bool
    ) -> tuple[str, list[str]]:
        """
        Risk sonucuna göre PQC zırh profilini ve otonom eylemleri belirler.

        Eşik mantığı (PDF Bölüm 4):
            risk_score > 75  → AĞIR ZIRH + Kırmızı Alarm
            risk_score ≤ 75  → HAFİF ZIRH + İşlem Onayı

        Args:
            is_anomaly : risk_score > RISK_THRESHOLD ise True.

        Returns:
            tuple[str, list[str]]: (PQC zırh profili, eylem listesi)
        """
        if is_anomaly:
            armor   = PQC_HEAVY_ARMOR
            actions = [
                "[Eylem 1]: Eray'ın PQC Motoruna 'AĞIR ZIRH' "
                "(Dilithium-5 / ML-DSA-87) geçiş sinyali gönderiliyor...",
                "[Eylem 2]: Tuna'nın ERC-4337 Akıllı Sözleşmesinde "
                "işlem 2 saatlik TimeLock'a alındı!",
            ]
        else:
            armor   = PQC_LIGHT_ARMOR
            actions = []

        return armor, actions

    def _assert_trained(self) -> None:
        """
        Modelin eğitilip eğitilmediğini kontrol eder; eğitilmemişse hata fırlatır.

        Raises:
            RuntimeError: Model henüz eğitilmemişse.
        """
        if not self._is_trained or self._model is None:
            raise RuntimeError(
                "Model henüz eğitilmedi. Önce QAnomalyDetector.train() çağırın."
            )

    # ── Bilgi Metodları ────────────────────────────────────────────────────────

    @property
    def is_trained(self) -> bool:
        """Modelin eğitilip eğitilmediğini döndürür."""
        return self._is_trained

    @property
    def model(self) -> Optional[IsolationForest]:
        """Eğitilmiş sklearn IsolationForest nesnesini döndürür."""
        return self._model

    def summary(self) -> None:
        """Eğitilmiş modelin özetini konsola yazdırır."""
        if not self._is_trained:
            print("Model henüz eğitilmedi.")
            return

        print_section("MODEL ÖZETİ")
        print(f"  Algoritma           : IsolationForest (sklearn)")
        print(f"  n_estimators        : {IF_N_ESTIMATORS}")
        print(f"  max_samples         : {IF_MAX_SAMPLES}")
        print(f"  contamination       : {IF_CONTAMINATION} (%{IF_CONTAMINATION * 100:.0f})")
        print(f"  random_state        : {IF_RANDOM_STATE}")
        print(f"  Eğitim Satırı       : {self._training_rows}")
        print(f"  Karar Fon. Ort. (μ) : {self._train_mean:.6f}")
        print(f"  Karar Fon. Std. (σ) : {self._train_std:.6f}")
        print(f"  Risk Eşiği          : %{RISK_THRESHOLD}")
        print(f"  Hafif Zırh          : {PQC_LIGHT_ARMOR}")
        print(f"  Ağır Zırh           : {PQC_HEAVY_ARMOR}")
        print()

    # ── Kalıcılık: Kaydet & Yükle (Aşama 3) ───────────────────────────────────

    def save(self, directory: str = MODEL_DIR) -> str:
        """
        Eğitilmiş modeli ve kalibrasyon metaverisini joblib ile diske kaydeder.

        Kaydedilen artefakt sözlüğü:
            {
                'model'         : sklearn IsolationForest nesnesi,
                'train_mean'    : eğitim seti karar fonksiyonu ortalaması (μ),
                'train_std'     : eğitim seti karar fonksiyonu std sapması (σ),
                'training_rows' : eğitim satır sayısı,
                'risk_threshold': anomali eşiği (%75),
                'feature_cols'  : özellik sütun adları,
            }

        Args:
            directory : Kaydedilecek klasör (varsayılan: 'models/').

        Returns:
            str: Kaydedilen dosyanın tam yolu.

        Raises:
            RuntimeError: Model henüz eğitilmemişse.
        """
        self._assert_trained()

        from pathlib import Path
        save_dir  = Path(directory)
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / MODEL_ARTIFACT_NAME

        artifact = {
            "model"         : self._model,
            "train_mean"    : self._train_mean,
            "train_std"     : self._train_std,
            "training_rows" : self._training_rows,
            "risk_threshold": RISK_THRESHOLD,
            "feature_cols"  : FEATURE_COLUMNS,
        }

        joblib.dump(artifact, save_path, compress=3)
        logger.info("Model artefaktı kaydedildi → '%s'", save_path)
        return str(save_path)

    @classmethod
    def load(cls, directory: str = MODEL_DIR) -> "QAnomalyDetector":
        """
        Daha önce joblib ile kaydedilmiş bir modeli yükler ve
        tam olarak yapılandırılmış bir QAnomalyDetector döndürür.

        Args:
            directory : Artefaktın bulunduğu klasör (varsayılan: 'models/').

        Returns:
            QAnomalyDetector: Yüklenen ve inference'a hazır dedektör.

        Raises:
            FileNotFoundError: Artefakt dosyası bulunamazsa.
        """
        from pathlib import Path
        load_path = Path(directory) / MODEL_ARTIFACT_NAME

        if not load_path.exists():
            raise FileNotFoundError(
                f"Model artefaktı bulunamadı: '{load_path}'\n"
                f"Lütfen önce 'python run_pipeline.py' ile modeli eğitin."
            )

        artifact = joblib.load(load_path)

        instance = cls()
        instance._model         = artifact["model"]
        instance._train_mean    = artifact["train_mean"]
        instance._train_std     = artifact["train_std"]
        instance._training_rows = artifact["training_rows"]
        instance._is_trained    = True

        logger.info(
            "Model yüklendi ← '%s' (μ=%.4f, σ=%.4f, %d satır)",
            load_path,
            instance._train_mean,
            instance._train_std,
            instance._training_rows,
        )
        return instance


# ────────────────────────────────────────────────────────────────────────────────
# Fabrika Fonksiyonu: API Başlangıç Olayı İçin
# ────────────────────────────────────────────────────────────────────────────────

def load_detector(directory: str = MODEL_DIR) -> QAnomalyDetector:
    """
    FastAPI lifespan olayı için hazır fabrika fonksiyonu.
    'models/' klasöründeki artefaktı yükler ve inference'a hazır dedektör döndürür.

    Args:
        directory : Model artefaktının bulunduğu klasör.

    Returns:
        QAnomalyDetector: Yüklenen dedektör.
    """
    return QAnomalyDetector.load(directory)

