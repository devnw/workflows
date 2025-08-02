#!/usr/bin/env bash

set -euo pipefail

# Check if the `.pre-commit-config.yaml` file exists and run `pre-commit autoupdate`.
if [ -x "$(command -v pre-commit)" ]; then
    if [ -f ".pre-commit-config.yaml" ]; then
        echo "Updating pre-commit hooks..."
        pre-commit autoupdate
    else
        echo ".pre-commit-config.yaml not found, skipping pre-commit autoupdate"
    fi 
else
  echo "pre-commit is not installed, skipping pre-commit autoupdate"
fi

if [ -x "$(command -v nix)" ]; then
    # Check if there is a flake.nix file
    if [ -f "flake.nix" ]; then
        echo "Found flake.nix, running nix flake update..."
        NIX_CONFIG="experimental-features = nix-command flakes;access-tokens = github.com=$(gh auth token)" nix flake update
    else
        echo "flake.nix not found, skipping nix flake update"
    fi
else
  echo "Nix is not installed, skipping flake update"
fi

if [ -x "$(command -v go)" ]; then
    # Check for a `go.mod` file and run `go mod tidy`.
    if [ -f "go.mod" ]; then
        echo "Found go.mod, running go mod tidy..."
        go mod tidy

        # Update the Go dependencies.
        echo "Updating Go dependencies..."
        go get -u ./...
    else
        echo "go.mod not found, skipping go mod tidy"
    fi
else
    echo "Go is not installed, skipping Go dependency update"
fi

if [ -x "$(command -v npm)" ]; then
    # Do a recursive check for `package.json` files for each directory execute a set of commands.
    find . -name "package.json" -execdir sh -c '
        echo "Found package.json in $(pwd), running npm install..."
        npm install npm-check-updates && ncu -u || echo "npm-check-updates is not installed, skipping"
	    npm update && npm install
        echo "Installing npm-check-updates..."
        echo "Running npm audit fix..."
        npm audit fix
        echo "Running npm run build..."
        npm run build || echo "npm run build failed, skipping"
    ' \;
    echo "All npm packages installed and built."
else
    echo "npm is not installed, skipping npm install"
fi
