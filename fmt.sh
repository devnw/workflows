#!/usr/bin/env bash

set -euo pipefail

# Check to see if `nixfmt` is available and format `flake.nix` if it is.
if [ -x "$(command -v nixfmt)" ]; then
  nixfmt flake.nix
else
  echo "nixfmt is not installed, skipping formatting of flake.nix"
fi

# Format Go, JavaScript, and TypeScript files.

if [ -x "$(command -v goimports)" ]; then
  echo "Formatting Go files..."
else
  echo "goimports is not installed, skipping Go formatting"
fi

if [ -x "$(command -v gofmt)" ]; then
  gofmt -s -w .
else
  echo "gofmt is not installed, skipping Go formatting"
fi

if [ -x "$(command -v prettier)" ]; then
  prettier --write .
else
  echo "prettier is not installed, skipping formatting"
fi

# Format shell scripts
if [ -x "$(command -v shfmt)" ]; then
  echo "Formatting shell scripts..."
  find . -type f -name "*.sh" -exec shfmt -w {} +
else
  echo "shfmt is not installed, skipping shell script formatting"
fi

# Format Python files
if [ -x "$(command -v black)" ]; then
  echo "Formatting Python files..."
  black .
else
  echo "black is not installed, skipping Python formatting"
fi