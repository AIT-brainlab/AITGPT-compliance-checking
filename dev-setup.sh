#!/bin/bash

# Fix permissions if inside Dev Container
if [ "$IS_DEVCONTAINER" = "True" ]; then
    echo "-- Correcting permissions..."
    sudo chown 1000:1000 .venv 2>/dev/null || true
    sudo chown 1000:1000 .python 2>/dev/null || true
    sudo chown 1000:1000 .uv_cache 2>/dev/null || true
fi

# Fix line endings in .env if needed
sed -i 's/\r//' .env 2>/dev/null || true

# Load environment variables
echo "-- Loading .env"
source .env

# Install uv if not found
echo "-- Checking uv..."
if ! command -v uv &> /dev/null; then
    echo "-- Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "✓ uv installed"
else
    echo "✓ uv already installed"
fi

# Install Python
echo "-- Installing Python"
uv python install

# Install dependencies
echo "-- Installing dependencies"
uv sync

# Install CLI completion
echo "-- Installing CLI"
uv run policy-checker --install-completion 2>/dev/null || true

echo ""
echo "================================================"
echo "Setup complete!"
echo "Run: uv run policy-checker --source ait --verbose"
echo "================================================"
