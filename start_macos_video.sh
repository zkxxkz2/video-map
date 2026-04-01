#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
TTS_HOST="${TTS_HOST:-127.0.0.1}"
TTS_PORT="${TTS_PORT:-9880}"

COSYVOICE_ROOT="$ROOT_DIR/storage/local_tts/CosyVoice-upstream"
MODEL_DIR="$ROOT_DIR/storage/local_tts/models/CosyVoice-300M-SFT"
MODELSCOPE_CACHE_DIR="$ROOT_DIR/storage/local_tts/modelscope_cache"
TTS_LOG="$ROOT_DIR/storage/temp/cosyvoice-server.log"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[ERROR] Python not found: $PYTHON_BIN"
  echo "Set PYTHON_BIN first, e.g. export PYTHON_BIN=$(which python)"
  exit 1
fi

if [[ ! -d "$COSYVOICE_ROOT" ]]; then
  echo "[ERROR] CosyVoice upstream not found: $COSYVOICE_ROOT"
  exit 1
fi

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "[ERROR] Local model not found: $MODEL_DIR"
  echo "Run bootstrap first or copy model files to this path."
  exit 1
fi

mkdir -p "$MODELSCOPE_CACHE_DIR" "$ROOT_DIR/storage/temp"
export MODELSCOPE_CACHE="$MODELSCOPE_CACHE_DIR"

echo "[INFO] Installing main requirements..."
"$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt"

echo "[INFO] Installing local TTS requirements for macOS..."
"$PYTHON_BIN" -m pip install -r "$ROOT_DIR/tools/local_tts/requirements.cosyvoice-runtime.macos.txt"

echo "[INFO] Starting local CosyVoice service on http://$TTS_HOST:$TTS_PORT"
"$PYTHON_BIN" "$ROOT_DIR/tools/local_tts/cosyvoice_server.py" \
  --cosyvoice-root "$COSYVOICE_ROOT" \
  --model-dir "$MODEL_DIR" \
  --host "$TTS_HOST" \
  --port "$TTS_PORT" > "$TTS_LOG" 2>&1 &

TTS_PID=$!
trap 'kill "$TTS_PID" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 45); do
  if curl -fsS "http://$TTS_HOST:$TTS_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS "http://$TTS_HOST:$TTS_PORT/health" >/dev/null 2>&1; then
  echo "[ERROR] Local CosyVoice service failed to become ready."
  echo "[INFO] Check log: $TTS_LOG"
  exit 1
fi

echo "[INFO] Local CosyVoice is ready. Launching WebUI..."
streamlit run ./webui/Main.py --browser.serverAddress="0.0.0.0" --server.enableCORS=True --browser.gatherUsageStats=False
