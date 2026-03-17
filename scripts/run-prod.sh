#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_PATH="${VENV_PATH:-${REPO_ROOT}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FORCE_REFRESH=0

if [[ "${1:-}" == "--refresh" ]]; then
	FORCE_REFRESH=1
	shift
fi

needs_install=0

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
	"${PYTHON_BIN}" -m venv "${VENV_PATH}"
	needs_install=1
fi

if [[ ! -x "${VENV_PATH}/bin/gentooinstall" ]]; then
	needs_install=1
fi

if (( FORCE_REFRESH == 1 || needs_install == 1 )); then
	"${VENV_PATH}/bin/python" -m pip install -e "${REPO_ROOT}"
fi

if (( EUID == 0 )); then
	exec "${VENV_PATH}/bin/gentooinstall" "$@"
fi

exec sudo "${VENV_PATH}/bin/gentooinstall" "$@"
