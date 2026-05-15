#!/bin/bash

# Fix permissions if inside Dev Container
if [ "$IS_DEVCONTAINER" = "True" ]; then
    echo "-- Correcting permissions..."
    sudo chown 1000:1000 .venv
    sudo chown 1000:1000 .python
    sudo chown 1000:1000 .uv_cache
fi

# Install Python
echo "-- Installing Python"
uv python install

# Install dependencies
echo "-- Installing dependencies"
uv sync

# Install CLI completion
echo "-- Installing CLI"
uv run policy-checker --install-completion
