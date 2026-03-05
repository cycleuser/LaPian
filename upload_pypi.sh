#!/usr/bin/env bash
set -e

echo "=== LaPian PyPI Upload Script ==="

# Clean previous build artifacts
echo "[1/4] Cleaning old build artifacts..."
rm -rf dist/ build/ *.egg-info

# Install/upgrade build tools
echo "[2/4] Installing/upgrading build tools..."
pip install --upgrade build twine

# Build the package
echo "[3/4] Building package..."
python -m build

# Upload to PyPI
echo "[4/4] Uploading to PyPI..."
python -m twine upload dist/*

echo "=== Done! ==="
