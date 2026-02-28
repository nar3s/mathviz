#!/bin/sh
set -e

echo "=== MathViz startup ==="
echo "Python:  $(/opt/venv/bin/python --version 2>&1)"
echo "Uvicorn: $(/opt/venv/bin/uvicorn --version 2>&1)"
echo "Port:    ${PORT:-8000}"
echo "Output:  ${OUTPUT_DIR:-/data}"
echo "======================="

exec /opt/venv/bin/uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1
