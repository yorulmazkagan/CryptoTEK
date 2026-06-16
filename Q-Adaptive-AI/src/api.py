# =============================================================================
# Q-ADAPTIVE AI Guardian — FastAPI REST Servisi (src/api.py)
# =============================================================================
# Bu modül, Aşama 3'ün çekirdeğini oluşturur: kalibre edilmiş IsolationForest
# modelini HTTP üzerinden erişilebilir kılan asenkron REST API.
#
# Özellikler:
#   • Lifespan protokolü ile sıfır-gecikme model yükleme (startup)
#   • Pydantic v2 ile tip güvenli istek doğrulama (TransactionPayload)
#   • POST /predict → anında risk skoru + otonom PQC tepkisi
#   • GET  /health  → sunucu + model sağlık kontrolü
#   • GET  /        → API meta bilgisi
#
# Eray'ın PQC Rust motoru veya herhangi bir Web3 istemcisi bu endpoint'i
# çağırarak gerçek zamanlı risk skoru ve PQC zırh kararı alabilir.
#
# Kullanım:
#   python run_server.py              # Uvicorn ile başlat
#   POST http://127.0.0.1:8000/predict
#   Content-Type: application/json
#   {"Islem_Sikligi": 50.0, "IP_Sapmasi": 0.05, "Gas_Sapmasi": 0.1}
# =============================================================================

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Proje içi modüller
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.model import QAnomalyDetector, load_detector
from src.utils import setup_logger
from config import FEATURE_COLUMNS

logger = setup_logger("Q-ADAPTIVE.API")


# ─────────────────────────────────────────────────────────────────────────────
# Global Model Durumu (Lifespan ile Yönetilir)
# ─────────────────────────────────────────────────────────────────────────────

# API boyunca paylaşılan model örneği — thread-safe salt-okunur kullanım
_detector: Optional[QAnomalyDetector] = None
_startup_time: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan: Uygulama Başlangıç & Bitiş Olayları
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Startup: Kalibre edilmiş IsolationForest modelini models/ klasöründen
             yükler. Model bulunamazsa kritik hata fırlatır ve server başlamaz.

    Shutdown: Temizlik işlemleri gerçekleştirilir (ileride DB bağlantısı vb.)
    """
    global _detector, _startup_time

    # ── STARTUP ───────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Q-ADAPTIVE FastAPI sunucusu başlatılıyor...")
    logger.info("Model artefaktı 'models/' klasöründen yükleniyor...")

    try:
        _detector    = load_detector()
        _startup_time = time.time()
        logger.info("✅ Model başarıyla yüklendi — API isteklere hazır.")
        logger.info("=" * 60)
    except FileNotFoundError as exc:
        logger.critical("❌ Model yüklenemedi: %s", exc)
        logger.critical(
            "Çözüm: Önce 'python run_pipeline.py' çalıştırın."
        )
        raise RuntimeError(str(exc)) from exc

    yield  # <── Uygulama burada çalışır

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    logger.info("Q-ADAPTIVE API sunucusu kapatılıyor...")
    _detector = None


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI Uygulama Örneği
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title        = "Q-ADAPTIVE AI Guardian API",
    description  = (
        "Post-kuantum akıllı güvenlik katmanı için gerçek zamanlı anomali "
        "tespit ve Moving Target Defense (MTD) REST servisi.\n\n"
        "**Eray'ın PQC Rust motoru** veya herhangi bir Web3 istemcisi bu "
        "endpoint'i çağırarak anında risk skoru ve PQC zırh kararı alabilir."
    ),
    version      = "1.0.0",
    lifespan     = lifespan,
    docs_url     = "/docs",
    redoc_url    = "/redoc",
    openapi_url  = "/openapi.json",
)

# CORS: Rust/Web3 istemcilerinden gelen cross-origin isteklere izin ver
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # Production'da kısıtlanmalı
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Şemaları: İstek & Yanıt Modelleri
# ─────────────────────────────────────────────────────────────────────────────

class TransactionPayload(BaseModel):
    """
    POST /predict endpoint'i için Pydantic istek doğrulama şeması.

    Özellikler (PDF Bölüm 2 tanımına uygun):
        Islem_Sikligi : Saniyedeki işlem sayısı     (Normal: 1-2, Anomali: 50+)
        IP_Sapmasi    : Coğrafi IP sapması [0, 1]   (1.0 → imkânsız seyahat)
        Gas_Sapmasi   : Ağ ortalamasından Gas farkı (10-20x → saldırı)
    """
    Islem_Sikligi : float = Field(
        ...,
        ge          = 0.0,
        description = "Saniyedeki işlem sayısı. Normal: 1-2, Bot saldırısı: 50+",
        examples    = [1.5],
    )
    IP_Sapmasi    : float = Field(
        ...,
        ge          = 0.0,
        le          = 100.0,         # 1.0 üstü zaten aşırı anomali
        description = "Coğrafi IP sapması (0=sabit, 1=imkânsız seyahat)",
        examples    = [0.05],
    )
    Gas_Sapmasi   : float = Field(
        ...,
        ge          = 0.0,
        description = "Ağ ortalamasından Gas ücreti sapması. Hackerlar 10-20x öder.",
        examples    = [0.1],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary"        : "Standart Kullanıcı (DeFi Swap)",
                    "Islem_Sikligi"  : 1.1,
                    "IP_Sapmasi"     : 0.02,
                    "Gas_Sapmasi"    : 0.05,
                },
                {
                    "summary"        : "Bot Saldırısı (Spam)",
                    "Islem_Sikligi"  : 50.0,
                    "IP_Sapmasi"     : 0.05,
                    "Gas_Sapmasi"    : 0.1,
                },
                {
                    "summary"        : "Private Key Çalınması",
                    "Islem_Sikligi"  : 2.0,
                    "IP_Sapmasi"     : 0.95,
                    "Gas_Sapmasi"    : 15.5,
                },
            ]
        }
    }


class PredictResponse(BaseModel):
    """
    POST /predict yanıt şeması (PDF Bölüm tarafından belirlenen format).

    Fields:
        status     : "success" veya "error"
        risk_score : 0.0–100.0 arasında risk yüzdesi
        action     : "SAFE" | "TRIGGER_PANIC_MODE"
        pqc_tier   : Aktif PQC zırh profili
    """
    status     : str
    risk_score : float
    action     : str
    pqc_tier   : str


class HealthResponse(BaseModel):
    """GET /health yanıt şeması."""
    status       : str
    model_loaded : bool
    uptime_sec   : float
    version      : str


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı: Dedektöre Güvenli Erişim
# ─────────────────────────────────────────────────────────────────────────────

def _get_detector() -> QAnomalyDetector:
    """
    Global dedektörü döndürür; model yüklenmediyse 503 hatası fırlatır.

    Returns:
        QAnomalyDetector: Yüklü ve inference'a hazır dedektör.

    Raises:
        HTTPException 503: Model henüz yüklü değilse.
    """
    if _detector is None or not _detector.is_trained:
        raise HTTPException(
            status_code = 503,
            detail      = (
                "Model henüz yüklenmedi. "
                "Lütfen önce 'python run_pipeline.py' çalıştırın."
            ),
        )
    return _detector


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: GET / — API Meta Bilgisi
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Meta"], summary="API Kök Bilgisi")
async def root() -> Dict[str, Any]:
    """
    API kök endpoint'i — temel meta bilgisini döndürür.
    Eray'ın Rust motoru bu endpoint ile API'nin canlı olduğunu doğrulayabilir.
    """
    return {
        "project"    : "Q-ADAPTIVE AI Guardian",
        "version"    : "1.0.0",
        "description": "Post-Kuantum Akıllı Güvenlik Katmanı — MTD REST API",
        "endpoints"  : {
            "predict" : "POST /predict",
            "health"  : "GET  /health",
            "docs"    : "GET  /docs",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: GET /health — Sağlık Kontrolü
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model = HealthResponse,
    tags           = ["Meta"],
    summary        = "Sunucu & Model Sağlık Kontrolü",
)
async def health_check() -> HealthResponse:
    """
    Sunucu ve model sağlık durumunu döndürür.
    Load balancer veya Kubernetes probe'ları bu endpoint'i kullanabilir.
    """
    model_ok = _detector is not None and _detector.is_trained
    uptime   = round(time.time() - _startup_time, 2) if _startup_time else 0.0

    return HealthResponse(
        status       = "healthy" if model_ok else "degraded",
        model_loaded = model_ok,
        uptime_sec   = uptime,
        version      = "1.0.0",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: POST /predict — Gerçek Zamanlı Risk Tahmini
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/predict",
    response_model = PredictResponse,
    tags           = ["Inference"],
    summary        = "İşlem Risk Skoru Tahmini",
    response_description = (
        "Risk skoru (0-100), tetiklenen otonom eylem ve aktif PQC zırh profili."
    ),
)
async def predict(payload: TransactionPayload) -> PredictResponse:
    """
    Tek bir blockchain işlem vektörü için gerçek zamanlı risk skoru hesaplar
    ve otonom Moving Target Defense kararını döndürür.

    **Düşük Risk (≤ %75):**
    - `action`   → `"SAFE"`
    - `pqc_tier` → `"ML-DSA-44 (Light Armor)"`

    **Yüksek Risk (> %75):**
    - `action`   → `"TRIGGER_PANIC_MODE"`
    - `pqc_tier` → `"ML-DSA-87 (Heavy Armor)"`

    Bu yanıt Eray'ın PQC motoruna, motorun hangi zırh seviyesine geçeceğini
    ve Tuna'nın ERC-4337 Time-Lock kontratının aktive edilip edilmeyeceğini
    bildirir.
    """
    detector = _get_detector()

    # ── Girdi Vektörünü Numpy Dizisine Dönüştür ───────────────────────────────
    tx_vector = np.array(
        [[payload.Islem_Sikligi, payload.IP_Sapmasi, payload.Gas_Sapmasi]],
        dtype = np.float64,
    )

    logger.info(
        "Tahmin isteği alındı — [Islem=%.3f, IP=%.3f, Gas=%.3f]",
        payload.Islem_Sikligi, payload.IP_Sapmasi, payload.Gas_Sapmasi,
    )

    # ── Model Çıkarımı ────────────────────────────────────────────────────────
    result = detector.analyze(
        scenario_name = "API_REQUEST",
        tx_vector     = tx_vector,
    )

    # ── Yanıt Formatı Belirleme (PDF Bölüm tanımına uygun) ───────────────────
    if result.is_anomaly:
        action   = "TRIGGER_PANIC_MODE"
        pqc_tier = "ML-DSA-87 (Heavy Armor)"
    else:
        action   = "SAFE"
        pqc_tier = "ML-DSA-44 (Light Armor)"

    logger.info(
        "Tahmin tamamlandı — Risk: %%%.2f | Eylem: %s | PQC: %s",
        result.risk_score, action, pqc_tier,
    )

    return PredictResponse(
        status     = "success",
        risk_score = round(result.risk_score, 4),
        action     = action,
        pqc_tier   = pqc_tier,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Global Hata Yakalayıcı
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Beklenmedik sunucu hatalarını yakalayarak yapılandırılmış JSON hata
    yanıtı döndürür. Stack trace'i gizleyerek güvenli hata mesajı üretir.
    """
    logger.exception("Beklenmedik sunucu hatası: %s", exc)
    return JSONResponse(
        status_code = 500,
        content     = {
            "status" : "error",
            "detail" : "Sunucu tarafında beklenmedik bir hata oluştu.",
            "type"   : type(exc).__name__,
        },
    )
