#!/bin/bash
# Wrapper script to run mypy on operators with hyphenated directory names

set -e

echo "Running mypy type checking on operators..."

# Create temporary directory with valid Python package names
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy files to temp directory with valid names
cp operators/ai-engine/main.py "$TEMP_DIR/ai_engine.py"
cp operators/infrastructure-healer/main.py "$TEMP_DIR/infrastructure_healer.py"
cp operators/code-autofix/main.py "$TEMP_DIR/code_autofix.py"

# Run mypy on the copied files
cd "$TEMP_DIR"
mypy *.py --ignore-missing-imports

echo "mypy type checking completed successfully"