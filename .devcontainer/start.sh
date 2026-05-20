#!/bin/bash
# start.sh — auto-detect GPU, start containers, and set up dev environment
# Usage: bash .devcontainer/start.sh

cd "$(dirname "$0")"

# ── Step 1: Auto-detect GPU ───────────────────────────────────────────────
COMPOSE_FILES="-f docker-compose.yml"

detect_gpu() {
    if docker run --rm --gpus all ubuntu nvidia-smi > /dev/null 2>&1; then
        echo "nvidia"
    elif [ -e /dev/kfd ] && [ -e /dev/dri ]; then
        echo "amd"
    else
        echo "cpu"
    fi
}

echo ""
echo "============================================================"
echo " PolicyChecker — Dev Environment Setup"
echo "============================================================"
echo ""
echo "-- Detecting GPU..."
GPU=$(detect_gpu)

case $GPU in
    nvidia)
        echo "-- NVIDIA GPU detected — enabling GPU acceleration"
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
        ;;
    amd)
        echo "-- AMD GPU detected — enabling ROCm acceleration"
        COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.amd.yml"
        ;;
    cpu)
        echo "-- No GPU detected — using CPU (inference will be slow)"
        ;;
esac

# ── Step 2: Start containers ──────────────────────────────────────────────
echo ""
echo "-- Starting containers..."
docker compose $COMPOSE_FILES down --remove-orphans 2>/dev/null
docker compose $COMPOSE_FILES up -d

if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to start containers. Check docker compose logs."
    exit 1
fi

# ── Step 3: Run dev-setup.sh inside the dev container ────────────────────
DEV_CONTAINER=$(docker compose $COMPOSE_FILES ps -q dev 2>/dev/null | head -1)

if [ -z "$DEV_CONTAINER" ]; then
    echo "[ERROR] Dev container not found. Check docker compose status."
    exit 1
fi

echo ""
echo "-- Running dev-setup inside container..."
docker exec -it "$DEV_CONTAINER" bash /Projects/compliance-checking/dev-setup.sh

echo ""
echo "============================================================"
echo " Done! To enter the dev container:"
echo "   Open VS Code → Reopen in Container"
echo " Or attach directly:"
echo "   docker exec -it $DEV_CONTAINER bash"
echo "============================================================"
echo ""