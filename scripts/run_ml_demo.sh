#!/usr/bin/env bash
# Generate deterministic demo data, train the detector, evaluate it, and run tests.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  rm -rf .venv
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --requirement requirements.txt
.venv/bin/python -m ml.simulator --output data/flows.csv --seed 7
.venv/bin/python -m ml.train --input data/flows.csv --model artifacts/detector.joblib
.venv/bin/python -m ml.evaluate --input data/flows.csv --model artifacts/detector.joblib
.venv/bin/python -m pytest -q
printf '
Created: data/flows.csv and artifacts/detector.joblib
'
