# =============================================================================
# Q-ADAPTIVE AI Guardian — API Sunucu Başlatıcı (run_server.py)
# =============================================================================
# Bu dosya, FastAPI uygulamasını üretim kalitesinde Uvicorn ASGI sunucusuyla
# programatik olarak başlatır.
#
# Kullanım:
#   python run_server.py
#
# Ön Koşul:
#   python run_pipeline.py   ← Model artefaktını (models/) oluşturur
#
# Sunucu başladıktan sonra erişilebilir adresler:
#   • REST API  : http://127.0.0.1:8000
#   • Swagger UI: http://127.0.0.1:8000/docs
#   • ReDoc     : http://127.0.0.1:8000/redoc
#   • OpenAPI   : http://127.0.0.1:8000/openapi.json
# =============================================================================

import sys
import os
from pathlib import Path

# Proje kökünü Python yoluna ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from src.utils import setup_logger, print_banner, SEPARATOR
from config import MODEL_DIR, MODEL_ARTIFACT_NAME

logger = setup_logger("Q-ADAPTIVE.Server")

# ── Sunucu Yapılandırması ─────────────────────────────────────────────────────

SERVER_HOST   : str  = "127.0.0.1"
SERVER_PORT   : int  = 8000
RELOAD_MODE   : bool = False     # Development'ta True yapılabilir
LOG_LEVEL     : str  = "info"
WORKERS       : int  = 1         # Tek worker (tek model örneği için)


def _check_model_artifact() -> None:
    """
    Sunucu başlamadan önce model artefaktının varlığını doğrular.
    Artefakt eksikse açıklayıcı hata mesajı ile çıkar.
    """
    artifact_path = Path(MODEL_DIR) / MODEL_ARTIFACT_NAME
    if not artifact_path.exists():
        print()
        print("=" * 65)
        print("  ❌ HATA: Model artefaktı bulunamadı!")
        print(f"  Beklenen konum: '{artifact_path}'")
        print()
        print("  Çözüm: Önce aşağıdaki komutu çalıştırın:")
        print("    python run_pipeline.py")
        print()
        print("  Bu komut modeli eğitir ve 'models/' klasörüne kaydeder.")
        print("=" * 65)
        print()
        sys.exit(1)


def run_server() -> None:
    """
    Q-ADAPTIVE FastAPI uygulamasını Uvicorn ASGI sunucusuyla başlatır.

    Başlatma öncesinde model artefaktının varlığını doğrular; eksikse
    kullanıcıya açıklayıcı mesaj göstererek güvenli biçimde çıkar.
    """
    # Model artefaktı ön koşul kontrolü
    _check_model_artifact()

    # Konsol başlığı
    print()
    print(SEPARATOR)
    print("  Q-ADAPTIVE AI Guardian — FastAPI REST Sunucusu Başlatılıyor")
    print(SEPARATOR)
    print(f"  Host       : {SERVER_HOST}")
    print(f"  Port       : {SERVER_PORT}")
    print(f"  Swagger UI : http://{SERVER_HOST}:{SERVER_PORT}/docs")
    print(f"  ReDoc      : http://{SERVER_HOST}:{SERVER_PORT}/redoc")
    print(f"  Predict    : POST http://{SERVER_HOST}:{SERVER_PORT}/predict")
    print(SEPARATOR)
    print()

    # Uvicorn başlat
    uvicorn.run(
        app         = "src.api:app",   # modül:obje formatı
        host        = SERVER_HOST,
        port        = SERVER_PORT,
        reload      = RELOAD_MODE,
        log_level   = LOG_LEVEL,
        workers     = WORKERS,
        # Production önerileri (ihtiyaç halinde aktif edilebilir):
        # ssl_keyfile  = "certs/key.pem",
        # ssl_certfile = "certs/cert.pem",
        # access_log   = True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Giriş Noktası
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_server()
