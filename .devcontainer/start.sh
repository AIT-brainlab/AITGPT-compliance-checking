#!/bin/bash
# start.sh — auto-detect GPU, start containers, and set up dev environment
# Usage: bash .devcontainer/start.sh

cd "$(dirname "$0")"

# ── Step 1: Auto-detect GPU ───────────────────────────────────────────────

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
        echo "-- NVIDIA GPU detected — writing nvidia override"
        cp docker-compose.nvidia.yml .docker-compose.override.yml
        ;;
    amd)
        echo "-- AMD GPU detected — writing AMD override"
        cp docker-compose.amd.yml .docker-compose.override.yml
        ;;
    cpu)
        echo "-- No GPU detected — writing empty override (CPU only)"
        echo "name: policychecker" > .docker-compose.override.yml
        ;;
esac

# ── Step 2: Start containers ──────────────────────────────────────────────
echo ""
echo "-- Starting containers..."
echo "-- Starting containers..."
docker compose -f docker-compose.yml -f .docker-compose.override.yml down --remove-orphans 2>/dev/null
docker compose -f docker-compose.yml -f .docker-compose.override.yml up -d
 
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to start containers. Check docker compose logs."
    exit 1
fi
 
DEV_CONTAINER=$(docker compose $COMPOSE_FILES ps -q dev 2>/dev/null | head -1)

echo ""
echo "============================================================"
echo " Done! To enter the dev container:"
echo "   Open VS Code → Reopen in Container"
echo " Or attach directly:"
echo "   docker exec -it $(docker compose $COMPOSE_FILES ps -q dev 2>/dev/null | head -1) bash"
echo "============================================================"
echo ""