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

# Check Ollama model
OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-mistral}"
 
echo ""
echo "-- Checking Ollama at $OLLAMA_HOST..."
 
# Wait for Ollama to be ready (up to 30 seconds)
for i in $(seq 1 30); do
    if curl -sf "$OLLAMA_HOST/api/tags" > /dev/null 2>&1; then
        break
    fi
    echo "   Waiting for Ollama... ($i/30)"
    sleep 1
done
 
# Check if model is already pulled
MODELS=$(curl -sf "$OLLAMA_HOST/api/tags" 2>/dev/null)
if echo "$MODELS" | grep -q "\"$OLLAMA_MODEL\""; then
    echo "-- Model $OLLAMA_MODEL already available."
else
    echo "-- Pulling $OLLAMA_MODEL (~4GB, this may take a while)..."
    curl -X POST "$OLLAMA_HOST/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$OLLAMA_MODEL\"}" \
        --no-buffer 2>/dev/null | while IFS= read -r line; do
            STATUS=$(echo "$line" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
            [ -n "$STATUS" ] && echo "   $STATUS"
        done
    echo "-- Model $OLLAMA_MODEL is ready."
fi
 
echo ""
echo "-- Setup complete. Run: uv run policy-checker --source ait --verbose"