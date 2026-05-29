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


# Set up Node.js via nodeenv (pinned to LTS 20 — Node 26 requires libatomic which is absent in the container)
echo "-- Setting up Node.js (LTS 20)"
uv run python -m nodeenv --node=20.19.2 .venv/node_env
export PATH="$PWD/.venv/node_env/bin:$PATH"

# Install frontend dependencies
echo "-- Installing frontend dependencies"
npm install --prefix src/policy_checker/web/frontend

# Install OLLAMA model
uv run --env-file=.env policy-ollama load

