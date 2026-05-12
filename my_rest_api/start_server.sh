#!/bin/bash

set -euo pipefail

# Start script for the OpenAI Codex Task Execution API.

# Change to the directory where this script is located.
cd "$(dirname "$0")"

# Check if virtual environment exists and activate it.
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
# Path to the codex binary. Defaults to 'codex' if not set.
# You can override this via the CODEX_BIN environment variable.
CODEX_BIN="${CODEX_BIN:-codex}"
CODEX_MODEL="${CODEX_MODEL:-}"
APP_CONFIG_FILE="${APP_CONFIG_FILE:-config/app.toml}"
APP_ACTIVE_PROFILE="${APP_ACTIVE_PROFILE:-}"
CODEX_PROJECT_SOURCE="${CODEX_PROJECT_SOURCE:-}"
CODEX_SESSIONS_BASE_PATH="${CODEX_SESSIONS_BASE_PATH:-}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"
UVICORN_RELOAD="${UVICORN_RELOAD:-0}"

export CODEX_BIN
export APP_CONFIG_FILE
if [ -n "$CODEX_MODEL" ]; then
    export CODEX_MODEL
fi
if [ -n "$APP_ACTIVE_PROFILE" ]; then
    export APP_ACTIVE_PROFILE
fi
if [ -n "$CODEX_PROJECT_SOURCE" ]; then
    export CODEX_PROJECT_SOURCE
fi
if [ -n "$CODEX_SESSIONS_BASE_PATH" ]; then
    export CODEX_SESSIONS_BASE_PATH
fi

if ! command -v uvicorn >/dev/null 2>&1; then
    echo "Error: uvicorn is not installed or not on PATH." >&2
    exit 1
fi

if [ ! -x "$(command -v "$CODEX_BIN")" ] && [ ! -x "$CODEX_BIN" ]; then
    echo "Error: CODEX_BIN is not executable: $CODEX_BIN" >&2
    exit 1
fi

echo "Starting the API server..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Config file: $APP_CONFIG_FILE"
if [ -n "$APP_ACTIVE_PROFILE" ]; then
    echo "Active profile override: $APP_ACTIVE_PROFILE"
else
    echo "Active profile override: <none> (using config file default)"
fi
echo "Codex binary: $CODEX_BIN"
if [ -n "$CODEX_MODEL" ]; then
    echo "Codex model override: $CODEX_MODEL"
else
    echo "Codex model override: <none> (using local Codex default)"
fi
if [ -n "$CODEX_PROJECT_SOURCE" ]; then
    echo "Codex project source: $CODEX_PROJECT_SOURCE"
fi
if [ -n "$CODEX_SESSIONS_BASE_PATH" ]; then
    echo "Codex sessions base path: $CODEX_SESSIONS_BASE_PATH"
fi
echo "Reload mode: $UVICORN_RELOAD"

UVICORN_ARGS=(
    app.main:app
    --host "$HOST"
    --port "$PORT"
    --log-level "$UVICORN_LOG_LEVEL"
)

if [ "$UVICORN_RELOAD" = "1" ]; then
    UVICORN_ARGS+=(--reload)
fi

exec uvicorn "${UVICORN_ARGS[@]}"
