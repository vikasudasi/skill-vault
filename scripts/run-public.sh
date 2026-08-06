#!/usr/bin/env bash
set -euo pipefail

# Load secrets (admin password etc.) from a gitignored .env if present.
# Keep secrets OUT of this committed script — only the untracked .env holds values.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

RUN_DIR="${RUN_DIR:-run}"
mkdir -p "${RUN_DIR}"

MCP_HOST="${SKILL_VAULT_MCP_HOST:-0.0.0.0}"
MCP_PORT="${SKILL_VAULT_MCP_PORT:-8000}"
WEB_HOST="${SKILL_VAULT_WEB_HOST:-0.0.0.0}"
WEB_PORT="${SKILL_VAULT_WEB_PORT:-8080}"

DISPLAY_MCP_HOST="${MCP_HOST}"
if [[ "${DISPLAY_MCP_HOST}" == "0.0.0.0" ]]; then
  DISPLAY_MCP_HOST="<your-host-or-ip>"
fi

DISPLAY_WEB_HOST="${WEB_HOST}"
if [[ "${DISPLAY_WEB_HOST}" == "0.0.0.0" ]]; then
  DISPLAY_WEB_HOST="<your-host-or-ip>"
fi

cleanup() {
  for pid_file in "${RUN_DIR}/skillvault-mcp.pid" "${RUN_DIR}/skillvault-web.pid"; do
    if [[ -f "${pid_file}" ]]; then
      pid="$(cat "${pid_file}")"
      if kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" || true
      fi
    fi
  done
}

trap cleanup EXIT INT TERM

echo "Running migrations..."
skill-vault migrate

echo "Starting MCP service..."
skill-vault serve --transport streamable-http >"${RUN_DIR}/mcp.log" 2>&1 &
echo "$!" > "${RUN_DIR}/skillvault-mcp.pid"

echo "Starting web service..."
skill-vault web >"${RUN_DIR}/web.log" 2>&1 &
echo "$!" > "${RUN_DIR}/skillvault-web.pid"

echo "Waiting for web health endpoint..."
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${WEB_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:${WEB_PORT}/healthz" >/dev/null 2>&1; then
  echo "Web health check failed. See ${RUN_DIR}/web.log"
  exit 1
fi

echo "Skill Vault public services are running."
echo "MCP URL: http://${DISPLAY_MCP_HOST}:${MCP_PORT}/mcp"
echo "Dashboard URL: http://${DISPLAY_WEB_HOST}:${WEB_PORT}/dashboard"
echo "Logs: ${RUN_DIR}/mcp.log and ${RUN_DIR}/web.log"
echo "Press Ctrl+C to stop."

wait
