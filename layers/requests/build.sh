#!/bin/bash
set -e

echo "Building requests Lambda Layer..."

# Clean previous build artifacts
rm -rf python/ layer.zip

# Install requests with platform-specific wheels for Lambda (Python 3.12, x86_64)
pip install requests \
  -t python/ \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  --python-version 3.12

# Create layer zip
zip -r layer.zip python/

# Print layer size for validation (must be < 50MB)
LAYER_SIZE=$(du -sh layer.zip | cut -f1)
echo "Layer size: ${LAYER_SIZE}"

LAYER_BYTES=$(stat --format=%s layer.zip 2>/dev/null || stat -f%z layer.zip 2>/dev/null)
MAX_BYTES=$((50 * 1024 * 1024))

if [ "$LAYER_BYTES" -gt "$MAX_BYTES" ]; then
  echo "ERROR: Layer exceeds 50MB limit!"
  exit 1
fi

echo "Build complete: layer.zip (${LAYER_SIZE})"
