#!/usr/bin/env bash
# =============================================================================
# Q-ADAPTIVE — Hugging Face Space klasörü oluşturucu
# =============================================================================
# Neden gerekli?
#   Bu reponun git geçmişinde 25 MB'lık .pptx dosyaları var. Hugging Face,
#   Git LFS dışında 10 MB üstü dosya kabul etmediği için `git push` reddedilir.
#   Bu betik, yalnızca konteynerin ihtiyaç duyduğu dosyalardan oluşan temiz
#   bir klasör üretir; oraya sıfırdan git geçmişi kurulur.
#
# Kullanım:
#   bash make-space.sh              → ../q-adaptive-space klasörünü oluşturur
#   bash make-space.sh /baska/yol   → belirtilen yola oluşturur
#
# Kod değiştiğinde bu betiği tekrar çalıştırıp klasörü yenileyebilirsiniz;
# .git klasörü korunur, dolayısıyla push geçmişi kaybolmaz.
# =============================================================================

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$(dirname "$SRC")/q-adaptive-space}"

echo "═══════════════════════════════════════════════════════════"
echo "  Kaynak : $SRC"
echo "  Hedef  : $DEST"
echo "═══════════════════════════════════════════════════════════"
echo

# Mevcut git geçmişini koru (yeniden çalıştırmalarda push geçmişi kaybolmasın)
if [ -d "$DEST/.git" ]; then
    echo "→ Mevcut .git geçmişi korunuyor..."
    TMP_GIT="$(mktemp -d)"
    mv "$DEST/.git" "$TMP_GIT/.git"
    KEEP_GIT=1
else
    KEEP_GIT=0
fi

rm -rf "$DEST"
mkdir -p "$DEST"

if [ "$KEEP_GIT" = "1" ]; then
    mv "$TMP_GIT/.git" "$DEST/.git"
    rmdir "$TMP_GIT"
fi

# ── Kök dosyalar ─────────────────────────────────────────────────────────────
echo "→ Kök dosyalar kopyalanıyor (Dockerfile, README, LICENSE)..."
cp "$SRC/Dockerfile"    "$DEST/"
cp "$SRC/.dockerignore" "$DEST/"
cp "$SRC/README.md"     "$DEST/"
[ -f "$SRC/LICENSE" ] && cp "$SRC/LICENSE" "$DEST/"

# ── Uygulama katmanları ──────────────────────────────────────────────────────
echo "→ Q-Adaptive-AI (FastAPI + ONNX + model artefaktları)..."
cp -r "$SRC/Q-Adaptive-AI" "$DEST/"

echo "→ Q-Adaptive-Contracts (Solidity kaynakları)..."
cp -r "$SRC/Q-Adaptive-Contracts" "$DEST/"

echo "→ Dashboard SPA..."
cp -r "$SRC/stitch_q_adaptive_ai_guardian_dashboards" "$DEST/"

echo "→ README görselleri..."
[ -d "$SRC/images" ] && cp -r "$SRC/images" "$DEST/"

# ── ZK katmanı: target/ HARİÇ (derleme konteyner içinde yapılır) ─────────────
echo "→ Q-Adaptive-ZK (kaynak + manifest + yedek payload; target/ hariç)..."
mkdir -p "$DEST/Q-Adaptive-ZK"
cp -r "$SRC/Q-Adaptive-ZK/src" "$DEST/Q-Adaptive-ZK/"
cp "$SRC/Q-Adaptive-ZK/Cargo.toml"        "$DEST/Q-Adaptive-ZK/"
cp "$SRC/Q-Adaptive-ZK/Cargo.lock"        "$DEST/Q-Adaptive-ZK/"
cp "$SRC/Q-Adaptive-ZK/proof_payload.json" "$DEST/Q-Adaptive-ZK/"

# ── Temizlik ─────────────────────────────────────────────────────────────────
echo "→ Önbellek ve log artıkları temizleniyor..."
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name '*.py[co]'    -type f -delete 2>/dev/null || true
find "$DEST" -name '*.log'       -type f -delete 2>/dev/null || true
find "$DEST" -name '.DS_Store'   -type f -delete 2>/dev/null || true

# ── .gitignore ───────────────────────────────────────────────────────────────
cat > "$DEST/.gitignore" <<'EOF'
Q-Adaptive-ZK/target/
**/__pycache__/
**/*.py[cod]
*.log
.venv/
venv/
.DS_Store
EOF

# ── Doğrulama ────────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════════"
echo "  DOĞRULAMA"
echo "═══════════════════════════════════════════════════════════"

MISSING=0
for f in \
    "Dockerfile" \
    "README.md" \
    "Q-Adaptive-AI/run_server.py" \
    "Q-Adaptive-AI/src/api.py" \
    "Q-Adaptive-AI/models/q_adaptive_guardian.onnx" \
    "Q-Adaptive-AI/models/calibration_metadata.json" \
    "Q-Adaptive-AI/models/q_adaptive_isolation_forest.joblib" \
    "Q-Adaptive-ZK/Cargo.toml" \
    "Q-Adaptive-ZK/src/main.rs" \
    "Q-Adaptive-ZK/proof_payload.json" \
    "stitch_q_adaptive_ai_guardian_dashboards/index.html"
do
    if [ -e "$DEST/$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ EKSİK: $f"
        MISSING=1
    fi
done

echo
echo "10 MB üstü dosya kontrolü (HF push engeli):"
BIG="$(find "$DEST" -type f -size +10M 2>/dev/null || true)"
if [ -n "$BIG" ]; then
    echo "$BIG" | while read -r b; do echo "  ✗ $(du -h "$b" | cut -f1)  $b"; done
    echo "  UYARI: Bu dosyalar push'u engeller. Silin veya Git LFS kullanın."
    MISSING=1
else
    echo "  ✓ temiz — 10 MB üstü dosya yok"
fi

echo
echo "  Toplam boyut : $(du -sh "$DEST" | cut -f1)"
echo "  Konum        : $DEST"
echo

if [ "$MISSING" = "1" ]; then
    echo "  ⚠️  Yukarıdaki uyarıları giderin."
    exit 1
fi

echo "  ✅ Space klasörü hazır."
echo "═══════════════════════════════════════════════════════════"
