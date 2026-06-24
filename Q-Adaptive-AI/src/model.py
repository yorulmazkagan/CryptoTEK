# =============================================================================
# Q-ADAPTIVE AI Guardian — ML Motoru (src/model.py)
# =============================================================================
# Production-Grade Refactor — Sliding Window Dynamic Threshold
#
# Sorumluluklar:
#   1. QAnomalyDetector     : IsolationForest modelini eğitir.
#   2. Risk Skoru           : Ham anomali skoru → %0-100 risk puanına dönüşüm.
#   3. SlidingWindowThresholdCalibrator:
#      - Son 50 işlemin ağ metriklerinin (Gas sapması + işlem sıklığı)
#        kayan varyansını izler.
#      - Eşiği otomatik olarak kalibre eder — donmuş matris yok.
#      - Formül:
#          τ(t) = τ_base + α·σ²_gas(t) + β·σ²_freq(t)
#          τ(t) ∈ [TAU_MIN=55.0, TAU_MAX=90.0]
#      - Soğuk başlangıç (< MIN_WINDOW_SIZE gözlem): sabit τ = COLD_START_THRESHOLD
#   4. Otonom Tepkiler: PQC zırh geçişi + ERC-4337 Time-Lock.
#
# PDF Referansı: Q_ADAPTIVE_AI_Simulasyon_Rehberi.pdf — Bölüm 3 & 4
# =============================================================================

from __future__ import annotations

import warnings
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, NamedTuple, Optional, Tuple

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

# PQC Zırh profilleri (Moving Target Defense katmanları)
PQC_HEAVY_ARMOR : str = "Dilithium-5 / ML-DSA-87 (AĞIR ZIRH)"
PQC_LIGHT_ARMOR : str = "ML-DSA-44 / Dilithium-2 (HAFİF ZIRH)"


# ─────────────────────────────────────────────────────────────────────────────
# Sliding Window Dynamic Threshold Calibrator
# ─────────────────────────────────────────────────────────────────────────────

# Kayan pencere boyutu — son N işlemin metrikleri izlenir
CALIBRATOR_WINDOW_SIZE    : int   = 50

# Soğuk başlangıç eşiği — pencere dolmadan önce kullanılır
COLD_START_THRESHOLD      : float = 75.0

# Temel eşik — pencere dolduğunda varyans bileşenleri buna eklenir
CALIBRATOR_BASE_THRESHOLD : float = 60.0

# Varyans hassasiyet katsayıları
CALIBRATOR_ALPHA          : float = 0.15  # Gas sapması varyans ağırlığı
CALIBRATOR_BETA           : float = 0.08  # İşlem sıklığı varyans ağırlığı

# Minimum gözlem sayısı — soğuk başlangıç/dinamik geçiş sınırı
CALIBRATOR_MIN_WINDOW_SIZE: int   = 5

# Dinamik eşiğin izin verilen aralığı — patolojik sürüklenmeyi önler
CALIBRATOR_TAU_MIN        : float = 55.0
CALIBRATOR_TAU_MAX        : float = 90.0


class _MetricSample(NamedTuple):
    """Kayan pencereye eklenen tek bir işlem ağ metriği gözlemi."""
    gas_deviation    : float  # Ağ ortalamasından Gas ücreti sapması
    tx_frequency     : float  # Saniyedeki işlem sayısı


class SlidingWindowThresholdCalibrator:
    """
    Son N işlemin ağ metriklerinin kayan varyansını izleyerek
    anomali eşiğini otomatik olarak kalibre eden üretim sınıfı.

    Algoritma (Kayan Pencere Dinamik Eşik):
    ─────────────────────────────────────
    Her yeni işlem gözlemi geldiğinde:
      1. (gas_deviation, tx_frequency) deque'ya eklenir (maxlen=50, eski düşer).
      2. Pencerede >= MIN_WINDOW_SIZE gözlem varsa:
           σ²_gas  = Var[gas_deviation_window]
           σ²_freq = Var[tx_frequency_window]
           τ(t)    = BASE_THRESHOLD + α·σ²_gas + β·σ²_freq
           τ(t)    = clamp(τ(t), TAU_MIN, TAU_MAX)
      3. Pencere yetersizse (soğuk başlangıç):
           τ(t)    = COLD_START_THRESHOLD (= 75.0)

    Matematiksel Garantiler:
    ────────────────────────
    • Gas volatilitesi arttığında (saldırı taraması): σ²_gas ↑ → τ ↑
      → eşik daha muhafazakar hale gelir, yanlış negatif riski düşer.
    • Saldırı geçtikten sonra ağ sakinleşince: σ² ↓ → τ ↓
      → meşru kullanıcılar için gereksiz panik modu azalır.
    • [55.0, 90.0] sıkıştırması: eşik hiçbir zaman tespit edilemez
      veya her şeyi anomali sayan bir değere saplanmaz.

    Örnek Kullanım:
        calibrator = SlidingWindowThresholdCalibrator()
        calibrator.update(gas_deviation=0.1, tx_frequency=1.5)
        threshold  = calibrator.get_threshold()
    """

    def __init__(
        self,
        window_size    : int   = CALIBRATOR_WINDOW_SIZE,
        base_threshold : float = CALIBRATOR_BASE_THRESHOLD,
        alpha          : float = CALIBRATOR_ALPHA,
        beta           : float = CALIBRATOR_BETA,
        min_window     : int   = CALIBRATOR_MIN_WINDOW_SIZE,
        tau_min        : float = CALIBRATOR_TAU_MIN,
        tau_max        : float = CALIBRATOR_TAU_MAX,
        cold_start_val : float = COLD_START_THRESHOLD,
    ) -> None:
        self._window      : Deque[_MetricSample] = deque(maxlen=window_size)
        self._base        : float = base_threshold
        self._alpha       : float = alpha
        self._beta        : float = beta
        self._min_window  : int   = min_window
        self._tau_min     : float = tau_min
        self._tau_max     : float = tau_max
        self._cold_start  : float = cold_start_val
        self._last_tau    : float = cold_start_val

        logger.info(
            "SlidingWindowThresholdCalibrator başlatıldı — "
            "window=%d, base=%.1f, α=%.3f, β=%.3f, τ∈[%.1f,%.1f]",
            window_size, base_threshold, alpha, beta, tau_min, tau_max,
        )

    # ── Genel API ─────────────────────────────────────────────────────────────

    def update(self, gas_deviation: float, tx_frequency: float) -> float:
        """
        Yeni bir işlem gözlemi ekler ve güncel dinamik eşiği döndürür.

        Args:
            gas_deviation : Bu işlemin ağ ortalamasına göre Gas sapması.
            tx_frequency  : Bu işlemdeki anlık işlem sıklığı (tx/s).

        Returns:
            float: Güncellenmiş dinamik eşik τ(t).
        """
        self._window.append(_MetricSample(
            gas_deviation=float(gas_deviation),
            tx_frequency=float(tx_frequency),
        ))
        self._last_tau = self._compute_threshold()
        return self._last_tau

    def get_threshold(self) -> float:
        """Mevcut kalibre edilmiş dinamik eşiği döndürür (pencereyi güncellemez)."""
        return self._last_tau

    @property
    def window_size(self) -> int:
        """Penceredeki mevcut gözlem sayısını döndürür."""
        return len(self._window)

    @property
    def is_warmed_up(self) -> bool:
        """True ise pencere dinamik hesaplama için yeterli gözleme sahiptir."""
        return len(self._window) >= self._min_window

    def get_stats(self) -> Dict[str, float]:
        """
        Hata ayıklama ve loglama için mevcut pencere istatistiklerini döndürür.

        Returns:
            dict: gas_var, freq_var, current_tau, window_fill_pct içerir.
        """
        n = len(self._window)
        if n < 2:
            return {
                "gas_var"         : 0.0,
                "freq_var"        : 0.0,
                "current_tau"     : self._last_tau,
                "window_fill_pct" : n / self._window.maxlen * 100.0,
                "is_warmed_up"    : False,
            }

        gas_arr  = np.array([s.gas_deviation for s in self._window], dtype=np.float64)
        freq_arr = np.array([s.tx_frequency  for s in self._window], dtype=np.float64)

        return {
            "gas_var"         : float(np.var(gas_arr,  ddof=1)),
            "freq_var"        : float(np.var(freq_arr, ddof=1)),
            "current_tau"     : self._last_tau,
            "window_fill_pct" : n / self._window.maxlen * 100.0,
            "is_warmed_up"    : n >= self._min_window,
        }

    # ── İç Hesaplama ──────────────────────────────────────────────────────────

    def _compute_threshold(self) -> float:
        """
        Kayan pencere varyansından τ(t) hesaplar.

        Soğuk başlangıç koruması: pencerede MIN_WINDOW_SIZE'dan az gözlem
        varsa COLD_START_THRESHOLD döndürülür — ilk birkaç işlem için güvenli.

        ddof=1 (Bessel düzeltmesi) kullanılır çünkü pencere, tüm nüfusun
        değil bir örneklemin kayan özetini temsil eder.
        """
        n = len(self._window)

        # Soğuk başlangıç koruması
        if n < self._min_window:
            return self._cold_start

        gas_arr  = np.array([s.gas_deviation for s in self._window], dtype=np.float64)
        freq_arr = np.array([s.tx_frequency  for s in self._window], dtype=np.float64)

        sigma2_gas  = float(np.var(gas_arr,  ddof=1))
        sigma2_freq = float(np.var(freq_arr, ddof=1))

        # Dinamik eşik formülü
        tau = self._base + self._alpha * sigma2_gas + self._beta * sigma2_freq

        # [TAU_MIN, TAU_MAX] sıkıştırması — patolojik sürüklenmeyi önler
        tau_clamped = float(np.clip(tau, self._tau_min, self._tau_max))

        logger.debug(
            "Eşik kalibrasyonu — σ²_gas=%.4f σ²_freq=%.4f τ_raw=%.3f τ_final=%.3f (n=%d)",
            sigma2_gas, sigma2_freq, tau, tau_clamped, n,
        )
        return tau_clamped


# ─────────────────────────────────────────────────────────────────────────────
# Modül Düzeyi Singleton — api.py ve diğer modüller bu örneği paylaşır
# ─────────────────────────────────────────────────────────────────────────────

_THRESHOLD_CALIBRATOR: SlidingWindowThresholdCalibrator = SlidingWindowThresholdCalibrator()
"""
Paylaşılan global kalibratör örneği.

api.py, her POST /api/predict çağrısında bu singleton'ı besler:
    from src.model import _THRESHOLD_CALIBRATOR
    _THRESHOLD_CALIBRATOR.update(gas_deviation=payload.Gas_Sapmasi,
                                  tx_frequency=payload.Islem_Sikligi)
    threshold = _THRESHOLD_CALIBRATOR.get_threshold()

Bu tasarım sayesinde tüm API işleyicileri tek bir pencereyi paylaşır
ve eşik, sunucu genelindeki trafik gürültüsünü yansıtır.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Veri Sınıfı: Tek Çıkarım Sonucunun Sarmalayıcısı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InferenceResult:
    """
    Tek bir işlem vektörü üzerinde çalıştırılan çıkarımın tam sonucunu saklar.

    Attributes:
        scenario_name    : Senaryonun açıklayıcı adı.
        input_vector     : Modele verilen numpy girdi dizisi.
        raw_score        : IsolationForest'ın ham decision_function çıktısı.
        z_score          : Eğitim istatistiklerine göre normalize z-skoru.
        risk_score       : 0-100 arasına kalibre edilmiş risk yüzdesi.
        dynamic_threshold: Bu çıkarım anında geçerli olan dinamik eşik τ(t).
        is_anomaly       : risk_score > dynamic_threshold ise True.
        pqc_armor        : Tetiklenen PQC zırh profili.
        actions          : Gerçekleştirilen otonom sistem eylemleri listesi.
    """
    scenario_name     : str
    input_vector      : np.ndarray
    raw_score         : float
    z_score           : float
    risk_score        : float
    dynamic_threshold : float          # Artık statik değil — her çıkarımda farklı olabilir
    is_anomaly        : bool
    pqc_armor         : str
    actions           : list = field(default_factory=list)


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
       Eşik, paylaşılan SlidingWindowThresholdCalibrator'dan dinamik olarak alınır.

    3. **Otonom Tepki** : Dinamik eşiğe göre PQC zırh geçişi sinyali
       ve ERC-4337 Time-Lock komutunu tetikler.

    Kullanım:
        detector = QAnomalyDetector()
        detector.train(training_df)
        result = detector.analyze("Senaryo 1", np.array([[1.1, 0.02, 0.05]]),
                                  calibrator=_THRESHOLD_CALIBRATOR)
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

    def analyze(
        self,
        scenario_name : str,
        tx_vector     : np.ndarray,
        calibrator    : Optional[SlidingWindowThresholdCalibrator] = None,
    ) -> InferenceResult:
        """
        Tek bir işlem vektörü üzerinde çıkarım yapar ve InferenceResult döndürür.

        Risk skoru hesaplama (Z-skoru Kalibrasyonu):
            1. raw  = clf.decision_function(tx_vector)
            2. z    = (raw - μ_train) / σ_train
            3. risk = (1 - Φ(z)) × 100   [Φ = Normal CDF]
            4. risk = max(0, min(100, risk))

        Dinamik Eşik Entegrasyonu:
            Eğer calibrator verilmişse, modül-düzeyi _THRESHOLD_CALIBRATOR
            kullanılır. İşlem vektörü kalibrasyona (gas, freq) olarak beslenir.
            Eşik, bu çıkarım için dinamik olarak hesaplanır.

        Fiziksel yorum:
            • raw >> μ_train → z büyük pozitif  → (1-Φ) küçük → Düşük Risk ✅
            • raw << μ_train → z büyük negatif → (1-Φ) büyük → Yüksek Risk 🔴

        Args:
            scenario_name : Senaryonun açıklayıcı etiketi.
            tx_vector     : Shape (1, 3) numpy dizisi [Islem_Sikligi, IP_Sapmasi, Gas_Sapmasi].
            calibrator    : Opsiyonel SlidingWindowThresholdCalibrator. None ise
                            modül singleton'ı (_THRESHOLD_CALIBRATOR) kullanılır.

        Returns:
            InferenceResult: Tam çıkarım sonucu ve otonom eylemler.

        Raises:
            RuntimeError: Model henüz eğitilmemişse.
        """
        self._assert_trained()

        # Kalibratör çözümlemesi: verilmemişse modül singleton'ını kullan
        _cal = calibrator if calibrator is not None else _THRESHOLD_CALIBRATOR

        # ── Ham Anomali Skoru ─────────────────────────────────────────────────
        raw_score: float = self._model.decision_function(
            tx_vector.reshape(1, -1)
        )[0]

        # ── Z-Skoru Kalibrasyonu ──────────────────────────────────────────────
        # raw < mean → anomali yönünde → yüksek risk
        # Güvenlik: _train_std sıfır olursa (patolojik eğitim seti) ZeroDivisionError
        # veya inf/NaN üretmesini önlemek için 1e-9 minimum ile sınırlandır.
        _safe_std: float = max(self._train_std, 1e-9)
        z_score: float = (raw_score - self._train_mean) / _safe_std

        # ── Normal CDF ile Risk Yüzdesi ───────────────────────────────────────
        # (1 - Φ(z)): z negatifleştikçe bu değer 1'e yaklaşır (yüksek risk)
        risk_score: float = float((1.0 - sc.norm.cdf(z_score)) * 100.0)
        risk_score = float(max(0.0, min(100.0, risk_score)))  # [0, 100] sıkıştırma

        # ── Dinamik Eşik Güncelleme ───────────────────────────────────────────
        # İşlem vektöründen gas ve frekans metriklerini çıkar
        # tx_vector şekli: [[Islem_Sikligi, IP_Sapmasi, Gas_Sapmasi]]
        vec_flat = tx_vector.flatten()
        gas_dev  = float(vec_flat[2]) if len(vec_flat) > 2 else 0.0
        tx_freq  = float(vec_flat[0]) if len(vec_flat) > 0 else 0.0

        dynamic_threshold = _cal.update(gas_deviation=gas_dev, tx_frequency=tx_freq)

        is_anomaly: bool = risk_score > dynamic_threshold

        # ── Otonom Sistem Tepkisi ─────────────────────────────────────────────
        pqc_armor, actions = self._determine_response(is_anomaly)

        logger.info(
            "[%s] Ham=%.4f | Z=%.4f | Risk=%%%.2f | τ(t)=%.2f | Anomali=%s",
            scenario_name, raw_score, z_score, risk_score, dynamic_threshold, is_anomaly,
        )

        return InferenceResult(
            scenario_name     = scenario_name,
            input_vector      = tx_vector,
            raw_score         = raw_score,
            z_score           = z_score,
            risk_score        = risk_score,
            dynamic_threshold = dynamic_threshold,
            is_anomaly        = is_anomaly,
            pqc_armor         = pqc_armor,
            actions           = actions,
        )

    def run_all_scenarios(
        self, scenarios: Dict[str, np.ndarray],
        calibrator: Optional[SlidingWindowThresholdCalibrator] = None,
    ) -> list[InferenceResult]:
        """
        Sözlük olarak verilen tüm test senaryolarını sırayla çalıştırır.

        Args:
            scenarios  : {'Senaryo Adı': np.ndarray} biçiminde sözlük.
            calibrator : Paylaşılan kalibratör — None ise modül singleton'ı.

        Returns:
            list[InferenceResult]: Her senaryo için çıkarım sonuçları listesi.
        """
        self._assert_trained()
        results: list[InferenceResult] = []

        logger.info("%d senaryo sırayla çalıştırılıyor...", len(scenarios))

        for name, vector in scenarios.items():
            result = self.analyze(name, vector, calibrator=calibrator)
            results.append(result)

        return results

    def print_result(self, result: InferenceResult, index: int = 1) -> None:
        """
        Tek bir çıkarım sonucunu PDF Bölüm 6'daki konsol formatında yazdırır.
        Dinamik eşik artık her satırda gösterilir.

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

        # Risk skoru + dinamik eşik
        print(f"\n>> Yapay Zeka Risk Skoru : %{result.risk_score:.2f}")
        print(f">> Dinamik Eşik τ(t)     : %{result.dynamic_threshold:.2f}  "
              f"(kayan pencere kalibrasyonu)")

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
    ) -> Tuple[str, list[str]]:
        """
        Risk sonucuna göre PQC zırh profilini ve otonom eylemleri belirler.

        Eşik mantığı: risk_score > τ(t) → AĞIR ZIRH + Kırmızı Alarm
                      risk_score ≤ τ(t) → HAFİF ZIRH + İşlem Onayı

        Args:
            is_anomaly : risk_score > dynamic_threshold ise True.

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

        cal_stats = _THRESHOLD_CALIBRATOR.get_stats()

        print_section("MODEL ÖZETİ")
        print(f"  Algoritma           : IsolationForest (sklearn)")
        print(f"  n_estimators        : {IF_N_ESTIMATORS}")
        print(f"  max_samples         : {IF_MAX_SAMPLES}")
        print(f"  contamination       : {IF_CONTAMINATION} (%{IF_CONTAMINATION * 100:.0f})")
        print(f"  random_state        : {IF_RANDOM_STATE}")
        print(f"  Eğitim Satırı       : {self._training_rows}")
        print(f"  Karar Fon. Ort. (μ) : {self._train_mean:.6f}")
        print(f"  Karar Fon. Std. (σ) : {self._train_std:.6f}")
        print(f"  ── Dinamik Eşik (Kayan Pencere) ──────────────────────────")
        print(f"  Mevcut τ(t)         : %{cal_stats['current_tau']:.2f}")
        print(f"  Pencere Doluluk     : %{cal_stats['window_fill_pct']:.1f}  "
              f"({'hazır' if cal_stats['is_warmed_up'] else 'soğuk başlangıç'})")
        print(f"  σ²_gas (kayan)      : {cal_stats['gas_var']:.6f}")
        print(f"  σ²_freq (kayan)     : {cal_stats['freq_var']:.6f}")
        print(f"  τ aralığı           : [{CALIBRATOR_TAU_MIN}, {CALIBRATOR_TAU_MAX}]")
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
                'risk_threshold': 'DYNAMIC — SlidingWindowThresholdCalibrator',
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
            # Not: artık statik eşik yok; kalibratör çalışma zamanında yeniden
            # oluşturulur. Bu alan geriye uyumluluk için korunur.
            "risk_threshold": "DYNAMIC — SlidingWindowThresholdCalibrator",
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
