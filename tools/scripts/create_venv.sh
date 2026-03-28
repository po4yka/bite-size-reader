#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "Creating virtual environment at ${VENV_DIR} using ${PYTHON_BIN}..."
${PYTHON_BIN} -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

echo "Upgrading pip and installing requirements..."
pip install --upgrade pip wheel setuptools

if command -v uv >/dev/null 2>&1; then
  echo "uv detected; compiling locks from pyproject.toml..."
  uv export --no-dev --no-hashes --format requirements-txt -o requirements.txt
  uv export --only-group dev --no-hashes --format requirements-txt -o requirements-dev.txt
fi

pip install -r requirements.txt -r requirements-dev.txt

echo "Installing pre-commit hooks..."
pre-commit install || true

echo "Done. Activate with: source ${VENV_DIR}/bin/activate"
