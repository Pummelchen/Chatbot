#!/usr/bin/env bash
# Lantern House core instruction: stay fail-safe, never leak debug or error
# text into the live chat, log recovered failures to logs/error.txt with
# context, and preserve hot-patch compatibility for uninterrupted long-running
# operation.
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

VENV_DIR="${PROJECT_ROOT}/.venv"
INSTALL_STAMP="${VENV_DIR}/.lantern-house-installed"
STARTUP_LOG="${PROJECT_ROOT}/logs/startup.log"
OLLAMA_LOG="${PROJECT_ROOT}/logs/ollama-serve.log"
ERROR_LOG="${PROJECT_ROOT}/logs/error.txt"

CONFIG_PATH="${LANTERN_HOUSE_CONFIG_PATH:-${PROJECT_ROOT}/config.example.toml}"
AUTO_RESTART=1
RUN_ARGS=()
HOST_PYTHON=""
APP_PYTHON=""
CHILD_PID=""
STOP_REQUESTED=0

mkdir -p "${PROJECT_ROOT}/logs"

log() {
  printf '[start.sh] %s\n' "$*" | tee -a "${STARTUP_LOG}" >&2
}

escape_json() {
  local value="${1//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  printf '%s' "${value}"
}

log_error_context() {
  local operation="$1"
  local reason="$2"
  local expectation="${3:-}"
  local retry_advice="${4:-}"

  {
    printf '{"source":"start.sh","operation":"%s","reason":"%s"' \
      "$(escape_json "${operation}")" "$(escape_json "${reason}")"
    if [[ -n "${expectation}" ]]; then
      printf ',"expected":"%s"' "$(escape_json "${expectation}")"
    fi
    if [[ -n "${retry_advice}" ]]; then
      printf ',"retry_advice":"%s"' "$(escape_json "${retry_advice}")"
    fi
    printf ',"config_path":"%s","timestamp":"%s"}\n' \
      "$(escape_json "${CONFIG_PATH}")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >>"${ERROR_LOG}"
}

die() {
  log_error_context \
    "startup" \
    "$*" \
    "A valid Python 3.12+ environment, reachable MySQL database, reachable Ollama server, and readable config." \
    "Repair the reported dependency or configuration and rerun ./start.sh."
  log "ERROR: $*"
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./start.sh [--config PATH] [--once] [--no-restart] [--help] [-- RUN_ARGS...]

Bootstraps Lantern House, initializes local dependencies, runs migrations,
seeds only when needed, and starts the resumable live runtime.

Options:
  --config PATH   Use a specific runtime config TOML file.
  --once          Run a single turn and exit.
  --no-restart    Disable auto-restart if the runtime exits unexpectedly.
  --help          Show this help.

Any extra arguments after -- are passed directly to:
  python -m lantern_house run
EOF
}

on_signal() {
  STOP_REQUESTED=1
  if [[ -n "${CHILD_PID}" ]]; then
    kill -TERM "${CHILD_PID}" 2>/dev/null || true
  fi
}

trap on_signal INT TERM

parse_args() {
  while (($#)); do
    case "$1" in
      --config)
        shift
        (($#)) || die "--config requires a path."
        CONFIG_PATH="$1"
        ;;
      --once)
        AUTO_RESTART=0
        RUN_ARGS+=("--once")
        ;;
      --no-restart)
        AUTO_RESTART=0
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      --)
        shift
        RUN_ARGS+=("$@")
        break
        ;;
      *)
        RUN_ARGS+=("$1")
        ;;
    esac
    shift
  done
}

python_is_compatible() {
  local candidate="$1"
  "${candidate}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
}

resolve_host_python() {
  local candidate
  for candidate in python3.12 python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1 && python_is_compatible "${candidate}"; then
      HOST_PYTHON="$(command -v "${candidate}")"
      return
    fi
  done
  die "Python 3.12+ is required."
}

resolve_config_path() {
  CONFIG_PATH="$("${HOST_PYTHON}" -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())' "${CONFIG_PATH}")"
  export LANTERN_HOUSE_CONFIG_PATH="${CONFIG_PATH}"
}

ensure_virtualenv() {
  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    if python_is_compatible "${VENV_DIR}/bin/python"; then
      APP_PYTHON="${VENV_DIR}/bin/python"
      return
    fi
    log "Existing virtual environment is not using Python 3.12+. Rebuilding ${VENV_DIR}."
    rm -rf "${VENV_DIR}"
  fi
  log "Creating virtual environment in ${VENV_DIR}."
  "${HOST_PYTHON}" -m venv "${VENV_DIR}"
  APP_PYTHON="${VENV_DIR}/bin/python"
}

runtime_dependencies_ready() {
  "${APP_PYTHON}" - <<'PY' >/dev/null 2>&1
import importlib

modules = [
    "alembic",
    "cryptography",
    "dotenv",
    "lantern_house",
    "pydantic",
    "pymysql",
    "rich",
    "sqlalchemy",
    "typer",
    "yaml",
]
for name in modules:
    importlib.import_module(name)
PY
}

ensure_dependencies() {
  if runtime_dependencies_ready; then
    if [[ ! -f "${INSTALL_STAMP}" || "${PROJECT_ROOT}/pyproject.toml" -nt "${INSTALL_STAMP}" ]]; then
      log "Existing virtual environment is already runtime-ready. Refreshing install stamp."
      touch "${INSTALL_STAMP}"
    fi
    return
  fi

  log "Installing Python dependencies."
  if ! "${APP_PYTHON}" -m pip install --disable-pip-version-check -e ".[dev]" >/dev/null; then
    die "Dependency installation failed. Ensure network access or preinstall the project dependencies in ${VENV_DIR}."
  fi
  touch "${INSTALL_STAMP}"
}

config_value() {
  local expression="$1"
  "${APP_PYTHON}" - "${CONFIG_PATH}" "${expression}" <<'PY'
import sys
from lantern_house.config import load_config

cfg = load_config(sys.argv[1])
expr = sys.argv[2]
if expr == "ollama_base_url":
    print(cfg.ollama.base_url)
elif expr == "enabled_models":
    models = [cfg.models.character, cfg.models.repair, cfg.models.manager, cfg.models.announcer]
    if cfg.god_ai.enabled:
        models.append(cfg.models.god_ai)
    seen = []
    for item in models:
        if item and item not in seen:
            seen.append(item)
    print("\n".join(seen))
else:
    raise SystemExit(f"Unknown config expression: {expr}")
PY
}

ensure_ollama_running() {
  local base_url
  base_url="$(config_value ollama_base_url)"
  command -v curl >/dev/null 2>&1 || die "curl is required to healthcheck and start Ollama."
  if curl -fsS "${base_url}/api/tags" >/dev/null 2>&1; then
    return
  fi

  if [[ "${base_url}" != http://127.0.0.1:* && "${base_url}" != http://localhost:* ]]; then
    die "Ollama is unreachable at ${base_url}. Auto-start only supports localhost."
  fi
  command -v ollama >/dev/null 2>&1 || die "The ollama CLI is required to auto-start the model server."

  log "Starting local Ollama server."
  nohup ollama serve >>"${OLLAMA_LOG}" 2>&1 &

  local waited=0
  until curl -fsS "${base_url}/api/tags" >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if (( waited >= 30 )); then
      die "Ollama did not become ready at ${base_url} within 30 seconds."
    fi
  done
}

ensure_ollama_models() {
  local base_url
  base_url="$(config_value ollama_base_url)"
  local model
  while IFS= read -r model; do
    [[ -n "${model}" ]] || continue
    if ollama_has_model "${base_url}" "${model}"; then
      continue
    fi
    log "Pulling missing Ollama model: ${model}"
    ollama pull "${model}"
  done < <(config_value enabled_models)
}

ollama_has_model() {
  local base_url="$1"
  local model="$2"
  local payload=""
  local attempt=0

  while (( attempt < 5 )); do
    payload="$(curl -fsS "${base_url}/api/tags" 2>/dev/null || true)"
    if [[ -n "${payload}" ]] && "${APP_PYTHON}" -c '
import json
import sys

needle = sys.argv[1]
payload = json.loads(sys.argv[2])
models = {item.get("name") for item in payload.get("models", [])}
raise SystemExit(0 if needle in models else 1)
' "${model}" "${payload}" >/dev/null 2>&1
    then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  if [[ -n "${payload}" ]]; then
    log_error_context \
      "ensure_ollama_models" \
      "Unable to parse Ollama model inventory while checking ${model}." \
      "A JSON response from Ollama /api/tags listing installed models." \
      "Wait for the local Ollama server to stabilize and rerun ./start.sh if model detection stays noisy."
  fi
  return 1
}

ensure_database_exists() {
  local output=""
  if ! output="$("${APP_PYTHON}" - "${CONFIG_PATH}" 2>&1 <<'PY'
import sys

import pymysql
from sqlalchemy.engine import make_url

from lantern_house.config import load_config

try:
    cfg = load_config(sys.argv[1])
    url = make_url(cfg.database.url)
    db_name = url.database
    if not db_name:
        raise RuntimeError("Database URL must include a database name.")
    if not url.drivername.startswith("mysql"):
        raise RuntimeError("start.sh currently supports MySQL database URLs only.")

    connection = pymysql.connect(
        host=url.host or "127.0.0.1",
        user=url.username or "",
        password=url.password or "",
        port=int(url.port or 3306),
        charset="utf8mb4",
        autocommit=True,
    )
    escaped = db_name.replace("`", "``")
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{escaped}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    connection.close()
except Exception as exc:
    raise SystemExit(str(exc))
PY
  )"; then
    if [[ -n "${output}" ]]; then
      log_error_context \
        "ensure_database_exists" \
        "${output}" \
        "A reachable MySQL server and valid credentials in the configured database URL." \
        "Repair MySQL connectivity or credentials and rerun ./start.sh."
    fi
    die "Unable to ensure the configured MySQL database exists. Check the database URL, credentials, and local MySQL availability."
  fi
}

run_cli() {
  "${APP_PYTHON}" -m lantern_house "$@" --config "${CONFIG_PATH}"
}

initialize_project() {
  log "Ensuring database exists."
  ensure_database_exists

  log "Ensuring Ollama is reachable."
  ensure_ollama_running
  ensure_ollama_models

  log "Applying migrations."
  run_cli migrate

  log "Validating or seeding story state."
  run_cli seed

  log "Running healthcheck."
  run_cli healthcheck
}

run_runtime_supervisor() {
  local delay=5
  local exit_code=0

  while (( STOP_REQUESTED == 0 )); do
    log "Starting Lantern House runtime."
    set +e
    "${APP_PYTHON}" -m lantern_house run --config "${CONFIG_PATH}" "${RUN_ARGS[@]}" &
    CHILD_PID=$!
    wait "${CHILD_PID}"
    exit_code=$?
    set -e
    CHILD_PID=""

    if (( STOP_REQUESTED != 0 )); then
      return 130
    fi
    if (( exit_code == 0 )); then
      return 0
    fi
    if (( AUTO_RESTART == 0 )); then
      return "${exit_code}"
    fi
    log "Runtime exited with code ${exit_code}. Restarting in ${delay}s."
    sleep "${delay}"
    if (( delay < 60 )); then
      delay=$((delay * 2))
      if (( delay > 60 )); then
        delay=60
      fi
    fi
  done

  return 130
}

main() {
  parse_args "$@"
  resolve_host_python
  resolve_config_path
  ensure_virtualenv
  ensure_dependencies

  log "Using config: ${CONFIG_PATH}"
  initialize_project
  run_runtime_supervisor
}

main "$@"
