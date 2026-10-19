#!/usr/bin/env bash
# Offline editable install with the pre-baked setuptools backend.
set -euo pipefail
cd "$(dirname "$0")"
python -m pip install --no-index --no-build-isolation -e .
