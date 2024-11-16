# Environment Variables
OP_CMD = op run --env-file="./.env"

# Targets
.PHONY: init fix-path fmt add channels clean switch all test deps

deps: detect-secrets

pre-commit: fmt

detect-secrets:
	detect-secrets scan > .secrets.baseline

dependabot:
	$(OP_CMD) -- python3 ./scripts/dependabot.py

fmt:
	nixfmt flake.nix

clean:
