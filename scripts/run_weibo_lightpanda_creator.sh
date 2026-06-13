#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIGHTPANDA_BIN="${LIGHTPANDA_BIN:-$HOME/.cache/lightpanda-node/lightpanda}"
LIGHTPANDA_HOST="${LIGHTPANDA_HOST:-127.0.0.1}"
LIGHTPANDA_PORT="${LIGHTPANDA_PORT:-9222}"
LIGHTPANDA_WS_URL="${LIGHTPANDA_WS_URL:-ws://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}/}"
SAVE_DATA_OPTION="${SAVE_DATA_OPTION:-json}"
RUN_ARGS=("$@")

cleanup() {
  if [[ -n "${LIGHTPANDA_PID:-}" ]] && kill -0 "${LIGHTPANDA_PID}" >/dev/null 2>&1; then
    kill "${LIGHTPANDA_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

echo "[weibo-lightpanda] root: ${ROOT_DIR}"
echo "[weibo-lightpanda] save_data_option: ${SAVE_DATA_OPTION}"
echo "[weibo-lightpanda] cdp_url: ${LIGHTPANDA_WS_URL}"

if ! curl -fsS "http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}/json/version" >/dev/null 2>&1; then
  if [[ ! -x "${LIGHTPANDA_BIN}" ]]; then
    echo "Lightpanda binary not found: ${LIGHTPANDA_BIN}" >&2
    exit 1
  fi
  echo "[weibo-lightpanda] starting lightpanda on ${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}"
  nohup "${LIGHTPANDA_BIN}" serve --host "${LIGHTPANDA_HOST}" --port "${LIGHTPANDA_PORT}" >/tmp/lightpanda_weibo_creator.log 2>&1 &
  LIGHTPANDA_PID=$!
  for _ in {1..30}; do
    if curl -fsS "http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}/json/version" >/dev/null 2>&1; then
      echo "[weibo-lightpanda] lightpanda is ready"
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS "http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}/json/version" >/dev/null 2>&1; then
  echo "Lightpanda did not become ready on ${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}" >&2
  exit 1
fi
echo "[weibo-lightpanda] confirmed lightpanda endpoint is reachable"

cd "${ROOT_DIR}"
export CDP_REMOTE_WS_URL="${LIGHTPANDA_WS_URL}"
if [[ ${#RUN_ARGS[@]} -eq 0 ]]; then
  echo "[weibo-lightpanda] running crawler: uv run main.py --platform wb --lt cookie --type creator --save_data_option ${SAVE_DATA_OPTION}"
  uv run main.py --platform wb --lt cookie --type creator --save_data_option "${SAVE_DATA_OPTION}"
else
  echo "[weibo-lightpanda] running crawler with extra args: ${RUN_ARGS[*]}"
  uv run main.py --platform wb --lt cookie --type creator --save_data_option "${SAVE_DATA_OPTION}" "${RUN_ARGS[@]}"
fi

echo "[weibo-lightpanda] crawl finished"
