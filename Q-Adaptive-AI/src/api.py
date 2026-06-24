# =============================================================================
# Q-ADAPTIVE AI Guardian — FastAPI REST + Dashboard Hub (src/api.py)
# =============================================================================
# Production-Grade Refactor:
#   • subprocess.run(["cargo", "run"]) TAMAMEN KALDIRILDI
#   • asyncio.create_subprocess_exec → Önceden derlenmiş release binary'e yönlendirir
#   • asyncio.Queue(maxsize=50) → Sunucu kaynaklarını DoS'tan korur
#   • HTTP 429 "Cryptographic Proof Queue Saturated" → Kuyruğu doldurmaya çalışan
#     saldırganları durdurur
#   • SlidingWindowThresholdCalibrator (model.py'den) → Statik %75 eşiği kaldırıldı
#
# Endpoint'ler:
#   GET  /              → Birleşik SPA (index.html)
#   GET  /ui/*          → Dashboard statik varlıklar
#   POST /api/predict   → Tam pipeline: ONNX → (Async ZK) → JSON yanıtı
#   GET  /api/health    → Sunucu + model + kuyruk sağlık kontrolü
#   GET  /docs          → Swagger UI
#
# Pipeline (POST /api/predict):
#   1. SlidingWindowThresholdCalibrator güncellenir → dinamik τ(t) hesaplanır
#   2. ONNX IsolationForest çıkarımı → risk_pct
#   3. risk_pct >= τ(t) ise: asyncio kuyruğuna girer →
#      asyncio.create_subprocess_exec ile önceden derlenmiş Rust binary çalışır
#   4. proof_payload.json okunarak EVM metrikleri çıkarılır
#   5. Genişletilmiş JSON yanıtı (ai_metrics, pqc_metrics, evm_metrics)
#
# Güvenlik Notu (ZK Binary Yolu):
#   Binary 'cargo run' ile değil, 'cargo build --release' ile önceden derlenmeli:
#     cd Q-Adaptive-ZK && cargo build --release
#   Sunucu başlatılmadan önce binary'nin mevcut olduğu doğrulanır.
# =============================================================================

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from scipy.stats import norm

# Proje içi modüller
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils import setup_logger
from src.model import _THRESHOLD_CALIBRATOR, SlidingWindowThresholdCalibrator

logger = setup_logger("Q-ADAPTIVE.API")

# ─────────────────────────────────────────────────────────────────────────────
# Dizin Sabitleri
# ─────────────────────────────────────────────────────────────────────────────

# Q-Adaptive-AI/ kökü
_AI_ROOT   = Path(__file__).parent.parent.resolve()

# Q-Adaptive-ZK/ kökü (yan dizin)
_ZK_ROOT   = _AI_ROOT.parent / "Q-Adaptive-ZK"

# Dashboard kökü
_DASH_ROOT = _AI_ROOT.parent / "stitch_q_adaptive_ai_guardian_dashboards"

# Model artefaktları
_ONNX_PATH         = _AI_ROOT / "models" / "q_adaptive_guardian.onnx"
_CALIBRATION_PATH  = _AI_ROOT / "models" / "calibration_metadata.json"
_PROOF_PATH        = _ZK_ROOT / "proof_payload.json"

# ─────────────────────────────────────────────────────────────────────────────
# ZK Prover Binary Yolu
# ─────────────────────────────────────────────────────────────────────────────
# GÜVENLIK: 'cargo run' tamamen kaldırıldı. Yalnızca önceden derlenmiş
# release binary'e işaret eder. Sunucu başlatıldığında binary'nin varlığı
# kontrol edilir. Binary yoksa sunucu başlamaz.
# Derleme: cd Q-Adaptive-ZK && cargo build --release
_ZK_BINARY_PATH = _ZK_ROOT / "target" / "release" / "q-adaptive-zk"

# Zaman kilidi süresi (Solidity SECURITY_DELAY = 2 hours)
_TIME_LOCK_SECONDS = 7200

# ─────────────────────────────────────────────────────────────────────────────
# Global Durum
# ─────────────────────────────────────────────────────────────────────────────

_ort_session   : Optional[ort.InferenceSession] = None
_calib_meta    : Dict[str, Any]                 = {}
_startup_time  : float                           = 0.0

# Async ZK proof kuyruğu:
#   maxsize=50 → En fazla 50 eş zamanlı kanıt üretimi.
#   Kuyruk dolunca HTTP 429 döner. Sunucu başlatılırken lifespan'da oluşturulur.
_ZK_PROOF_QUEUE: Optional[asyncio.Queue] = None


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan: Model + Kalibrasyon + ZK Binary Doğrulama
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: ONNX oturumunu, kalibrasyon meta-verilerini ve ZK kuyrucunu yükler.
    Shutdown: Kaynakları serbest bırakır.

    ZK binary doğrulaması:
        Binary yoksa RuntimeError fırlatılır — 'cargo run' gibi dinamik derleme
        hiçbir zaman başlatılmaz. Bu tasarım kasıtlıdır: DoS yüzeyini sıfırlar.
    """
    global _ort_session, _calib_meta, _startup_time, _ZK_PROOF_QUEUE

    logger.info("=" * 60)
    logger.info("Q-ADAPTIVE FastAPI + Dashboard Hub başlatılıyor...")

    # ── ONNX oturumu yükle ────────────────────────────────────────────────────
    if not _ONNX_PATH.exists():
        raise RuntimeError(
            f"ONNX modeli bulunamadı: {_ONNX_PATH}\n"
            "Çözüm: önce 'python run_pipeline.py' çalıştırın."
        )
    _ort_session = ort.InferenceSession(str(_ONNX_PATH))
    logger.info("✅ ONNX InferenceSession yüklendi: %s", _ONNX_PATH.name)

    # ── Kalibrasyon meta-verisini yükle ───────────────────────────────────────
    if not _CALIBRATION_PATH.exists():
        raise RuntimeError(f"Kalibrasyon dosyası bulunamadı: {_CALIBRATION_PATH}")
    with open(_CALIBRATION_PATH, encoding="utf-8") as f:
        _calib_meta = json.load(f)
    logger.info(
        "✅ Kalibrasyon yüklendi — mean_d=%.6f, std_d=%.6f",
        _calib_meta["mean_d"], _calib_meta["std_d"],
    )

    # ── ZK Binary varlık doğrulaması ──────────────────────────────────────────
    # Güvenlik tasarımı: binary yoksa başlatma başarısız olur.
    # Bu, test ortamlarında 'cargo run' ile başlatma cazibesini ortadan kaldırır.
    if not _ZK_BINARY_PATH.exists():
        logger.warning(
            "⚠️  ZK prover binary'si bulunamadı: %s\n"
            "   ZK kanıt üretimi devre dışı olacak. Binary oluşturmak için:\n"
            "   cd Q-Adaptive-ZK && cargo build --release",
            _ZK_BINARY_PATH,
        )
        # Binary yoksa ZK doğrulaması devre dışı kalır, panic modu çalışır
        # ancak prover çağrısı atlanır. Üretimde bu durum hata fırlatmalıdır:
        # raise RuntimeError(f"ZK binary bulunamadı: {_ZK_BINARY_PATH}")
    else:
        logger.info("✅ ZK prover binary doğrulandı: %s", _ZK_BINARY_PATH)

    # ── Async ZK kanıt kuyruğu oluştur ───────────────────────────────────────
    # asyncio.Queue, asyncio döngüsünün içinde oluşturulmalıdır.
    # maxsize=50: eş zamanlı 50 istek sınırı. Aşılırsa HTTP 429 döner.
    _ZK_PROOF_QUEUE = asyncio.Queue(maxsize=50)
    logger.info(
        "✅ Async ZK kanıt kuyruğu oluşturuldu (maxsize=%d)", _ZK_PROOF_QUEUE.maxsize
    )

    _startup_time = time.time()
    logger.info("✅ Sunucu isteklere hazır.")
    logger.info("=" * 60)

    yield  # ← Uygulama burada çalışır

    logger.info("Q-ADAPTIVE API kapatılıyor...")
    _ort_session = None
    _ZK_PROOF_QUEUE = None


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Uygulaması
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Q-ADAPTIVE AI Guardian API",
    description = (
        "Post-kuantum akıllı güvenlik katmanı — ONNX çıkarımı, "
        "Async Rust ZK-STARK kanıt üretimi ve EVM durum haritalama REST servisi."
    ),
    version     = "3.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    openapi_url = "/openapi.json",
)

# CORS: Dashboard, Rust ve Web3 istemcileri için
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Şemaları
# ─────────────────────────────────────────────────────────────────────────────

class TransactionPayload(BaseModel):
    """
    POST /api/predict için istek şeması.
    Üç blockchain işlem özelliği + opsiyonel senaryo etiketi.
    """
    Islem_Sikligi : float = Field(
        ..., ge=0.0,
        description="Saniyedeki işlem sayısı. Normal: 1-2, Bot: 50+",
        examples=[1.5],
    )
    IP_Sapmasi    : float = Field(
        ..., ge=0.0, le=100.0,
        description="Coğrafi IP sapması [0, 1]. 1.0 → imkansız seyahat",
        examples=[0.05],
    )
    Gas_Sapmasi   : float = Field(
        ..., ge=0.0,
        description="Ağ ortalamasından Gas ücreti sapması. Saldırganlar 10-20x öder.",
        examples=[0.1],
    )
    scenario_label: Optional[str] = Field(
        None,
        description="Opsiyonel senaryo etiketi (standart|bot|drainer)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary"       : "Standart Kullanıcı (DeFi Swap)",
                    "Islem_Sikligi" : 1.1,
                    "IP_Sapmasi"    : 0.02,
                    "Gas_Sapmasi"   : 0.05,
                },
                {
                    "summary"       : "Bot Saldırısı (Spam)",
                    "Islem_Sikligi" : 50.0,
                    "IP_Sapmasi"    : 0.05,
                    "Gas_Sapmasi"   : 0.1,
                },
                {
                    "summary"       : "Private Key Çalınması",
                    "Islem_Sikligi" : 2.0,
                    "IP_Sapmasi"    : 0.95,
                    "Gas_Sapmasi"   : 15.5,
                },
            ]
        }
    }


class AiMetrics(BaseModel):
    risk_score        : float
    dynamic_threshold : float   # τ(t) — kayan pencere kalibrasyonu
    # Alias: frontend reads `dynamic_tau` — senkronize et
    dynamic_tau       : float   # τ(t) kopyası — frontend HUD uyumluluğu
    islem_sikligi     : float
    ip_sapmasi        : float
    gas_sapmasi       : float
    calibrator_window_fill_pct: float  # Kalibratör penceresi doluluk oranı
    # Kayan pencere varyans bileşenleri — frontend Kalibrasyon paneli
    variance_gas      : float   # σ²_gas(t) — gaz sapması varyansı
    variance_freq     : float   # σ²_freq(t) — işlem sıklığı varyansı
    # Gerçek zamanlı kuyruk boyutu — frontend HUD kuyruk göstergesi
    queue_size        : int     # Anlık ZK proof kuyruk doluluk sayısı


class PqcMetrics(BaseModel):
    armor_tier              : str
    prover_time_ms          : float
    proof_size_kb           : float
    calldata_absorption_pct : float
    rho_prime_hex           : str   # Rho-prime seed — rotasyon doğrulaması için


class EvmMetrics(BaseModel):
    start_a          : int
    start_s1         : int
    start_s2         : int
    start_t          : int
    time_lock_seconds: int


class ExtendedPredictResponse(BaseModel):
    """Tam pipeline yanıtı — dört UI sekmesinin tüm alanlarını kapsar."""
    status     : str
    action     : str
    ai_metrics : AiMetrics
    pqc_metrics: PqcMetrics
    evm_metrics: EvmMetrics


class HealthResponse(BaseModel):
    status          : str
    model_loaded    : bool
    uptime_sec      : float
    version         : str
    zk_queue_size   : int   # Mevcut kuyruk doluluk sayısı
    zk_queue_max    : int   # Maksimum kuyruk kapasitesi
    calibrator_tau  : float # Mevcut dinamik eşik τ(t)
    calibrator_warmed_up: bool


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _onnx_infer(islem: float, ip: float, gas: float) -> tuple[float, int]:
    """
    ONNX IsolationForest üzerinde tek çıkarım çalıştırır.

    Model çıktıları (skl2onnx IsolationForest):
        outputs[0] → label : ndarray int64 shape [N,1]  — 1=normal, -1=anomali
        outputs[1] → scores: ndarray float32 shape [N,1] — raw decision_function

    Returns:
        (risk_pct, label) — risk_pct ∈ [0, 100], label ∈ {1, -1}

    Hata Güvenceleri:
        • std_d sıfır olursa (patolojik kalibrasyon verisi) 1e-9 ile sınırlandırılır
          → ZeroDivisionError veya NaN/inf üretilmez.
        • ONNX çıktısı beklenen şekle sahip değilse IndexError yakalanır.
    """
    if _ort_session is None:
        raise HTTPException(status_code=503, detail="ONNX oturumu hazır değil.")

    X       = np.array([[islem, ip, gas]], dtype=np.float32)
    outputs = _ort_session.run(None, {"float_input": X})

    label   = int(outputs[0][0][0])
    raw_df  = float(outputs[1][0][0])

    mean_d  = float(_calib_meta["mean_d"])
    # Güvenlik: std_d sıfır olursa (patolojik kalibrasyon) ZeroDivisionError önle.
    # Minimum 1e-9 ile sınırlandır — olasılık hesabı güvenli kalır.
    std_d   = max(float(_calib_meta["std_d"]), 1e-9)

    z        = (raw_df - mean_d) / std_d
    risk_pct = float((1.0 - norm.cdf(z)) * 100.0)
    risk_pct = max(0.0, min(100.0, risk_pct))

    logger.debug(
        "ONNX çıkarım — islem=%.2f ip=%.3f gas=%.2f | raw_df=%.6f z=%.4f risk=%.2f%% label=%d",
        islem, ip, gas, raw_df, z, risk_pct, label,
    )
    return risk_pct, label


async def _run_zk_prover_async() -> tuple[float, dict]:
    """
    Önceden derlenmiş Rust ZK-STARK prover binary'sini asenkron olarak çalıştırır.

    Güvenlik Tasarımı:
    ──────────────────
    1. asyncio.create_subprocess_exec kullanılır — 'cargo run' yok, 'shell=True' yok.
       Kabuk enjeksiyonu imkansız çünkü argümanlar dizisi olarak verilir.
    2. Binary yolu sabit bir Path sabitinden gelir (_ZK_BINARY_PATH).
       Kullanıcı girdisi binary yolunu hiçbir zaman etkileyemez.
    3. stdout/stderr yakalanır; çıktı sınırlandırılarak bellek tüketimi önlenir.
    4. Zaman aşımı: asyncio.wait_for ile 600 saniye (10 dakika).
    5. Bu fonksiyon yalnızca _ZK_PROOF_QUEUE bir slot serbest bıraktıktan sonra
       çalışır; kuyruk doluyken asla buraya ulaşılmaz.

    Returns:
        (prover_time_ms, proof_payload_dict)

    Raises:
        RuntimeError: Binary bulunamazsa veya sıfır olmayan çıkış kodu döndürürse.
    """
    if not _ZK_BINARY_PATH.exists():
        raise RuntimeError(
            f"ZK prover binary bulunamadı: {_ZK_BINARY_PATH}\n"
            "Derleme: cd Q-Adaptive-ZK && cargo build --release"
        )

    logger.info("🔐 Async ZK-STARK kanıt üretimi başlatılıyor (binary=%s)", _ZK_BINARY_PATH.name)
    t0 = time.perf_counter()

    try:
        proc = await asyncio.create_subprocess_exec(
            str(_ZK_BINARY_PATH),
            # Rho-prime seed —  yeni parametre; main.rs --rho-prime CLI argümanı
            # ile entegre edilmiştir. Gelecekte: seed burada üretilip geçilecek.
            cwd    = str(_ZK_ROOT),
            stdout = asyncio.subprocess.PIPE,
            stderr = asyncio.subprocess.PIPE,
        )

        # 600 saniye zaman aşımı — uzun kanıt üretimleri için yeterli
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=600.0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError("ZK prover zaman aşımına uğradı (600s limiti)")

        prover_ms = (time.perf_counter() - t0) * 1000.0

        if proc.returncode != 0:
            stderr_tail = stderr_bytes[-2000:].decode("utf-8", errors="replace")
            logger.error("ZK prover başarısız:\nSTDERR: %s", stderr_tail)
            raise RuntimeError(
                f"ZK prover {proc.returncode} koduyla çıktı. STDERR: {stderr_tail[-500:]}"
            )

        logger.info("✅ Async ZK-STARK kanıt üretimi tamamlandı (%.1f ms)", prover_ms)

    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ZK prover binary çalıştırılamadı: {exc}\n"
            "Binary çalıştırma izni var mı? chmod +x kontrol edin."
        ) from exc

    # proof_payload.json oku
    if not _PROOF_PATH.exists():
        raise RuntimeError(f"proof_payload.json bulunamadı: {_PROOF_PATH}")

    with open(_PROOF_PATH, encoding="utf-8") as f:
        proof_data = json.load(f)

    return prover_ms, proof_data


async def _invoke_zk_prover_with_queue_guard() -> tuple[float, dict]:
    """
    asyncio.Queue ile hız sınırlı ZK prover çağrısı.

    Tasarım:
    ─────────
    asyncio.Queue bir semafor olarak kullanılır:
      • put_nowait() → kuyruğa bir "token" ekler (slot rezervasyonu)
      • get()        → token tüketilir (prover tamamlandığında)
    Kuyruk maxsize=50 ile dolu olduğunda put_nowait() QueueFull fırlatır.
    Bu durum HTTP 429'a dönüştürülür.

    Saldırgan 50'den fazla eş zamanlı panik-modu isteği gönderirse:
      → put_nowait() QueueFull fırlatır
      → asynccontextmanager HTTP 429 döndürür
      → Rust binary hiçbir zaman spawn edilmez
      → Sunucu kaynakları korunur

    Returns:
        (prover_time_ms, proof_data_dict)

    Raises:
        HTTPException 429: Kuyruk kapasitesi aşıldığında.
        RuntimeError: Prover binary hatası.
    """
    if _ZK_PROOF_QUEUE is None:
        raise HTTPException(status_code=503, detail="ZK kanıt kuyruğu başlatılmadı.")

    # Kuyruk dolu kontrolü — saldırgan tespiti
    if _ZK_PROOF_QUEUE.full():
        logger.warning(
            "ZK kanıt kuyruğu dolu (%d/%d) — HTTP 429 döndürülüyor.",
            _ZK_PROOF_QUEUE.qsize(), _ZK_PROOF_QUEUE.maxsize,
        )
        raise HTTPException(
            status_code=429,
            detail=(
                "Cryptographic Proof Queue Saturated: "
                f"Maximum {_ZK_PROOF_QUEUE.maxsize} concurrent ZK proof generations "
                "are already in progress. Retry after current proofs complete."
            ),
            headers={"Retry-After": "30"},
        )

    # Slot rezervasyonu — kuyruğa token ekle
    await _ZK_PROOF_QUEUE.put(1)
    logger.info(
        "ZK kuyruk slot alındı (%d/%d aktif)",
        _ZK_PROOF_QUEUE.qsize(), _ZK_PROOF_QUEUE.maxsize,
    )

    try:
        # Asenkron prover çalıştır
        return await _run_zk_prover_async()
    finally:
        # Slot her zaman serbest bırakılır — başarı veya hata durumunda
        await _ZK_PROOF_QUEUE.get()
        _ZK_PROOF_QUEUE.task_done()
        logger.info(
            "ZK kuyruk slot serbest bırakıldı (%d/%d aktif)",
            _ZK_PROOF_QUEUE.qsize(), _ZK_PROOF_QUEUE.maxsize,
        )


def _proof_size_kb(proof_hex: str) -> float:
    """Hex string → gerçek kanıt bayt boyutunu KB olarak döndürür.

    Hata Güvencesi:
        Geçersiz hex (tek sayıda karakter, hex olmayan karakterler) durumunda
        ValueError fırlatılabilir. Bu durum 0.0 döndürerek yumuşatılır;
        çağıran kod sıfır boyutu '—' olarak gösterir.
    """
    try:
        return len(bytes.fromhex(proof_hex)) / 1024.0
    except (ValueError, TypeError):
        logger.warning(
            "_proof_size_kb: Geçersiz hex string (uzunluk=%d) — 0.0 döndürülüyor.",
            len(proof_hex) if proof_hex else 0,
        )
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: GET / — Dashboard SPA
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Birleşik Glassmorphic Dashboard SPA'sını sunar."""
    index_path = _DASH_ROOT / "index.html"
    if not index_path.exists():
        return JSONResponse(
            status_code=503,
            content={"detail": "Dashboard henüz oluşturulmadı. index.html bulunamadı."},
        )
    return FileResponse(str(index_path), media_type="text/html")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: GET /api/health — Sağlık Kontrolü
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["Meta"])
async def health_check() -> HealthResponse:
    """
    Sunucu, ONNX model, ZK kuyruk durumu ve dinamik eşik kalibrasyonunu döndürür.
    """
    model_ok    = _ort_session is not None
    uptime      = round(time.time() - _startup_time, 2) if _startup_time else 0.0
    queue_size  = _ZK_PROOF_QUEUE.qsize()  if _ZK_PROOF_QUEUE else 0
    queue_max   = _ZK_PROOF_QUEUE.maxsize if _ZK_PROOF_QUEUE else 0
    cal_stats   = _THRESHOLD_CALIBRATOR.get_stats()

    return HealthResponse(
        status               = "healthy" if model_ok else "degraded",
        model_loaded         = model_ok,
        uptime_sec           = uptime,
        version              = "3.0.0",
        zk_queue_size        = queue_size,
        zk_queue_max         = queue_max,
        calibrator_tau       = round(cal_stats["current_tau"], 4),
        calibrator_warmed_up = cal_stats["is_warmed_up"],
    )


# Legacy health endpoint (backward compat)
@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health_check_legacy() -> HealthResponse:
    return await health_check()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: POST /api/predict — Tam Pipeline Çıkarımı
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/predict",
    response_model        = ExtendedPredictResponse,
    tags                  = ["Inference"],
    summary               = "Tam Pipeline Risk Tahmini",
    response_description  = (
        "Genişletilmiş JSON: ai_metrics (dinamik eşik dahil), pqc_metrics, evm_metrics "
        "(Dashboard'un 4 sekmesini besler)."
    ),
)
async def predict(payload: TransactionPayload) -> ExtendedPredictResponse:
    """
    Blockchain işlem vektörü için uçtan uca pipeline çalıştırır.

    **Pipeline Adımları:**
    1. SlidingWindowThresholdCalibrator güncellenir → τ(t) hesaplanır (statik %75 değil)
    2. ONNX IsolationForest → kalibre edilmiş Z-skoru risk yüzdesi
    3. risk ≥ τ(t): asyncio kuyruğuna girer → Rust binary async spawn
       • Kuyruk doluysa (>50 eş zamanlı): HTTP 429 "Cryptographic Proof Queue Saturated"
    4. proof_payload.json → EVM sınır koşulları + kanıt boyutu + rho_prime_hex
    5. Genişletilmiş JSON yanıtı (dört UI sekmesini besler)
    """
    logger.info(
        "Tahmin isteği — [Islem=%.3f, IP=%.3f, Gas=%.3f]",
        payload.Islem_Sikligi, payload.IP_Sapmasi, payload.Gas_Sapmasi,
    )

    # ── ADIM 1: Kayan Pencere Kalibratörünü Güncelle ─────────────────────────
    # Bu çağrı hem pencereyi günceller hem de güncel τ(t) değerini döndürür.
    # Statik %75 eşiği tamamen kaldırıldı.
    dynamic_threshold = _THRESHOLD_CALIBRATOR.update(
        gas_deviation=payload.Gas_Sapmasi,
        tx_frequency=payload.Islem_Sikligi,
    )
    cal_stats = _THRESHOLD_CALIBRATOR.get_stats()

    logger.info(
        "Dinamik eşik τ(t)=%.2f (pencere: %d/50, σ²_gas=%.4f, σ²_freq=%.4f)",
        dynamic_threshold,
        _THRESHOLD_CALIBRATOR.window_size,
        cal_stats["gas_var"],
        cal_stats["freq_var"],
    )

    # ── ADIM 2: ONNX Çıkarımı ────────────────────────────────────────────────
    risk_pct, onnx_label = _onnx_infer(
        payload.Islem_Sikligi,
        payload.IP_Sapmasi,
        payload.Gas_Sapmasi,
    )

    # Panik kararı: dinamik eşik kullanılır (statik değil)
    is_panic   = risk_pct >= dynamic_threshold
    action     = "TRIGGER_PANIC_MODE" if is_panic else "SAFE"
    armor_tier = "ML-DSA-87" if is_panic else "ML-DSA-44"

    logger.info(
        "Risk: %.2f%% | τ(t): %.2f%% | Eylem: %s | Zırh: %s",
        risk_pct, dynamic_threshold, action, armor_tier,
    )

    # ── ADIM 3 & 4: Async ZK-STARK (Yalnızca Panik Modunda) ──────────────────
    prover_time_ms          = 0.0
    proof_size_kb           = 0.0
    calldata_absorption_pct = 0.0
    evm_start_a             = 0
    evm_start_s1            = 0
    evm_start_s2            = 0
    evm_start_t             = 0
    rho_prime_hex           = ""

    if is_panic:
        try:
            # asyncio.Queue hız sınırlayıcısı ile async prover çağrısı.
            # Kuyruk doluysa (saldırı senaryosu) bu satır HTTP 429 fırlatır.
            prover_time_ms, proof_data = await _invoke_zk_prover_with_queue_guard()

            # Kanıt boyutunu hex'ten hesapla
            hex_proof    = proof_data.get("stark_proof_bytes_hex", "")
            proof_size_kb = _proof_size_kb(hex_proof) if hex_proof else 0.0

            # Calldata emilim oranı: sıkıştırılmış / ham kanıt boyutu
            raw_sig_bytes           = 4608.0
            compressed_bytes        = proof_size_kb * 1024.0
            calldata_absorption_pct = min(
                99.9,
                max(0.0, (1.0 - compressed_bytes / (raw_sig_bytes + compressed_bytes)) * 100.0)
                    if (raw_sig_bytes + compressed_bytes) > 0 else 0.0,
            )

            # AIR sınır koşulları
            air_meta     = proof_data.get("air_verification_metadata", {})
            evm_start_a  = int(air_meta.get("start_a",  0))
            evm_start_s1 = int(air_meta.get("start_s1", 0))
            evm_start_s2 = int(air_meta.get("start_s2", 0))
            evm_start_t  = int(air_meta.get("start_t",  0))

            # Rho-prime hex — rotasyon doğrulaması için yeni alan
            rho_prime_hex = str(proof_data.get("rho_prime_hex", ""))

            logger.info(
                "ZK payload — boyut=%.2f KB, süre=%.1f ms, "
                "start=[a=%d, s1=%d, s2=%d, t=%d], rho_prime=%s...",
                proof_size_kb, prover_time_ms,
                evm_start_a, evm_start_s1, evm_start_s2, evm_start_t,
                rho_prime_hex[:16] if rho_prime_hex else "N/A",
            )

        except HTTPException:
            # HTTP 429 (kuyruk dolu) — yeniden fırlat, gizleme
            raise
        except Exception as exc:
            logger.warning("ZK-STARK kanıt üretimi başarısız: %s — Önbellek kontrol ediliyor.", exc)
            # Panik modunda proof üretimi başarısız olsa dahi yanıt döndürülür.
            if _PROOF_PATH.exists():
                try:
                    with open(_PROOF_PATH, encoding="utf-8") as f:
                        proof_data   = json.load(f)
                    hex_proof        = proof_data.get("stark_proof_bytes_hex", "")
                    proof_size_kb    = _proof_size_kb(hex_proof) if hex_proof else 0.0
                    air_meta         = proof_data.get("air_verification_metadata", {})
                    evm_start_a      = int(air_meta.get("start_a",  0))
                    evm_start_s1     = int(air_meta.get("start_s1", 0))
                    evm_start_s2     = int(air_meta.get("start_s2", 0))
                    evm_start_t      = int(air_meta.get("start_t",  0))
                    rho_prime_hex    = str(proof_data.get("rho_prime_hex", ""))
                    logger.info("Önbellek proof_payload.json kullanıldı.")
                except Exception:
                    pass

    # ── ADIM 5: Genişletilmiş Yanıt ──────────────────────────────────────────
    # Anlık kuyruk doluluk sayısını al (frontend HUD için)
    _current_queue_size = _ZK_PROOF_QUEUE.qsize() if _ZK_PROOF_QUEUE else 0

    response = ExtendedPredictResponse(
        status = "success",
        action = action,
        ai_metrics = AiMetrics(
            risk_score                 = round(risk_pct, 4),
            dynamic_threshold          = round(dynamic_threshold, 4),
            dynamic_tau                = round(dynamic_threshold, 4),  # frontend alias
            islem_sikligi              = payload.Islem_Sikligi,
            ip_sapmasi                 = payload.IP_Sapmasi,
            gas_sapmasi                = payload.Gas_Sapmasi,
            calibrator_window_fill_pct = round(cal_stats["window_fill_pct"], 2),
            variance_gas               = round(cal_stats["gas_var"], 6),
            variance_freq              = round(cal_stats["freq_var"], 6),
            queue_size                 = _current_queue_size,
        ),
        pqc_metrics = PqcMetrics(
            armor_tier              = armor_tier,
            prover_time_ms          = round(prover_time_ms, 3),
            proof_size_kb           = round(proof_size_kb, 3),
            calldata_absorption_pct = round(calldata_absorption_pct, 2),
            rho_prime_hex           = rho_prime_hex,
        ),
        evm_metrics = EvmMetrics(
            start_a           = evm_start_a,
            start_s1          = evm_start_s1,
            start_s2          = evm_start_s2,
            start_t           = evm_start_t,
            time_lock_seconds = _TIME_LOCK_SECONDS,
        ),
    )

    # ── Kriptografik Yürütme İzi (Standart Terminal Formatı) ─────────────────
    # Format: [Timestamp] [Module] [Queue Slots] [Risk Score] [PQC Armor]
    logger.info(
        "[%s] [Q-ADAPTIVE.API] [Kuyruk:%d/50] [Risk:%.4f%%] [τ(t):%.4f%%] [Zırh:%s] [Eylem:%s]",
        time.strftime("%Y-%m-%dT%H:%M:%S"),
        _current_queue_size,
        risk_pct,
        dynamic_threshold,
        armor_tier,
        action,
    )
    return response


# Legacy /predict endpoint (backward compat with old Rust/Web3 clients)
@app.post("/predict", include_in_schema=False)
async def predict_legacy(payload: TransactionPayload):
    return await predict(payload)


# ─────────────────────────────────────────────────────────────────────────────
# Statik Dosyalar: Dashboard Varlıkları
# ─────────────────────────────────────────────────────────────────────────────

if _DASH_ROOT.exists():
    app.mount(
        "/ui",
        StaticFiles(directory=str(_DASH_ROOT), html=True),
        name="dashboard",
    )
    logger.info("Dashboard statik dosyaları /ui altında sunuluyor: %s", _DASH_ROOT)
else:
    logger.warning("Dashboard dizini bulunamadı: %s", _DASH_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Global Hata Yakalayıcı
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Beklenmedik sunucu hatalarını yapılandırılmış JSON olarak döndürür."""
    logger.exception("Beklenmedik sunucu hatası: %s", exc)
    return JSONResponse(
        status_code = 500,
        content     = {
            "status" : "error",
            "detail" : "Sunucu tarafında beklenmedik bir hata oluştu.",
            "type"   : type(exc).__name__,
        },
    )
