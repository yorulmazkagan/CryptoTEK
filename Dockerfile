# =============================================================================
# Q-ADAPTIVE (AI Guardian) — Üretim Konteyneri
# =============================================================================
# Çok aşamalı (multi-stage) yapı:
#   Aşama 1 (zk-builder) : Rust + Winterfell ZK-STARK prover'ı release modda derler
#   Aşama 2 (runtime)    : Python 3.11 + ONNX Runtime + FastAPI; derlenmiş binary'yi devralır
#
# Sonuç: Tek konteyner, tek origin.
#   GET  /              → Glassmorphic Dashboard SPA
#   POST /api/predict   → ONNX çıkarımı → (panik modunda) Rust STARK prover
#   GET  /api/health    → Sağlık kontrolü
#   GET  /docs          → Swagger UI
#
# Dizin düzeni korunmalıdır: api.py, ZK ve dashboard köklerini kendi konumuna
# göre (parent.parent) çözer. Bu nedenle /app altında repo yapısı birebir kurulur.
#
# Yerel test:
#   docker build -t q-adaptive .
#   docker run --rm -p 7860:7860 q-adaptive
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# AŞAMA 1 — Rust Winterfell ZK-STARK Prover Derlemesi
# ─────────────────────────────────────────────────────────────────────────────
# Not: Winterfell 0.13.1 ve `jiff` bağımlılıkları güncel bir toolchain bekler;
# bu yüzden sürüm sabitlemek yerine güncel stable kullanılır. Yeniden
# üretilebilirlik gerekirse buradaki etiketi (ör. rust:1.86-slim-bookworm)
# sabitleyin.
FROM rust:slim-bookworm AS zk-builder

# blake3 ve keccak crate'leri assembly/C derlemesi için gcc gerektirir
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# ── Bağımlılık katmanı önbelleği ─────────────────────────────────────────────
# Önce yalnızca manifest dosyaları kopyalanır ve sahte bir main.rs ile
# bağımlılıklar derlenir. Böylece kaynak kodu değiştiğinde Winterfell
# bağımlılık ağacı yeniden derlenmez (build süresi ~8dk → ~2dk).
COPY Q-Adaptive-ZK/Cargo.toml Q-Adaptive-ZK/Cargo.lock ./
RUN mkdir -p src \
    && echo "fn main() {}" > src/main.rs \
    && cargo build --release \
    && rm -rf src

# ── Gerçek kaynak kodu ───────────────────────────────────────────────────────
COPY Q-Adaptive-ZK/src ./src
RUN touch src/main.rs \
    && cargo build --release \
    && ls -lh target/release/q-adaptive-zk


# ─────────────────────────────────────────────────────────────────────────────
# AŞAMA 2 — Python Çalışma Zamanı (FastAPI + ONNX Runtime)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# libgomp1 : ONNX Runtime'ın OpenMP bağımlılığı
# curl     : HEALTHCHECK için
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces konteynerleri UID 1000 ile çalışır.
# Root olmayan kullanıcı hem güvenlik hem de platform uyumluluğu için zorunludur.
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QA_HOST=0.0.0.0 \
    PORT=7860

WORKDIR /app

# ── Python bağımlılıkları (ayrı katman → kod değişiminde yeniden kurulmaz) ────
# requirements-runtime.txt kullanılır: skl2onnx (yalnızca eğitim/dönüşüm için
# gereken paket) hariç tutulmuştur. Konteyner önceden eğitilmiş .onnx
# artefaktını kullandığından çalışma zamanında ihtiyaç duyulmaz.
COPY Q-Adaptive-AI/requirements-runtime.txt ./Q-Adaptive-AI/requirements-runtime.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r ./Q-Adaptive-AI/requirements-runtime.txt

# ── Uygulama kaynakları ──────────────────────────────────────────────────────
# Model artefaktları (q_adaptive_guardian.onnx, calibration_metadata.json,
# q_adaptive_isolation_forest.joblib) repoda mevcuttur; çalışma zamanında
# eğitim YAPILMAZ. Konteyner saniyeler içinde ayağa kalkar.
COPY Q-Adaptive-AI/ ./Q-Adaptive-AI/
COPY stitch_q_adaptive_ai_guardian_dashboards/ ./stitch_q_adaptive_ai_guardian_dashboards/

# ── ZK katmanı: önbellek payload'ı + derlenmiş prover binary'si ──────────────
# proof_payload.json, prover çalışmadan önceki ilk istekler için yedek kaynaktır.
COPY Q-Adaptive-ZK/proof_payload.json ./Q-Adaptive-ZK/proof_payload.json
COPY --from=zk-builder /build/target/release/q-adaptive-zk \
     ./Q-Adaptive-ZK/target/release/q-adaptive-zk

# Prover, çalışma dizinine (Q-Adaptive-ZK/) proof_payload.json yazar.
# Bu nedenle dizin, uygulamayı çalıştıran kullanıcıya ait olmalıdır.
RUN chmod +x ./Q-Adaptive-ZK/target/release/q-adaptive-zk \
    && chown -R user:user /app

USER user

# run_server.py, model artefaktını göreli yoldan (models/) doğrular:
# çalışma dizini Q-Adaptive-AI olmalıdır.
WORKDIR /app/Q-Adaptive-AI

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["python", "run_server.py"]
