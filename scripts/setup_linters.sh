#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/setup_linters.sh
# Optional env:
#   PYTHON_BIN=python3.11 NPM_BIN=npm GITLEAKS_VERSION=8.24.2

PYTHON_BIN="${PYTHON_BIN:-python3}"
NPM_BIN="${NPM_BIN:-npm}"
GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.24.2}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

install_gitleaks() {
  if command -v gitleaks >/dev/null 2>&1; then
    return 0
  fi

  echo "gitleaks not found. Installing local binary..."
  local os arch archive url
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"

  case "$arch" in
    x86_64) arch="x64" ;;
    aarch64|arm64) arch="arm64" ;;
    *)
      echo "Unsupported architecture for automatic gitleaks install: $arch"
      return 1
      ;;
  esac

  archive="gitleaks_${GITLEAKS_VERSION}_${os}_${arch}.tar.gz"
  url="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${archive}"

  mkdir -p "$ROOT_DIR/.local/bin"
  curl -fsSL "$url" -o /tmp/gitleaks.tar.gz
  tar -xzf /tmp/gitleaks.tar.gz -C /tmp
  mv /tmp/gitleaks "$ROOT_DIR/.local/bin/gitleaks"
  chmod +x "$ROOT_DIR/.local/bin/gitleaks"
  export PATH="$ROOT_DIR/.local/bin:$PATH"
}

echo "[1/5] Installing Python tools (ruff, pip-audit)..."
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install ruff pip-audit

echo "[2/5] Verifying Python tools..."
ruff --version
pip-audit --version

echo "[3/5] Installing Node lint tools (eslint + plugins for JS/Vue)..."
if [ ! -f package.json ]; then
  cat > package.json <<'JSON'
{
  "name": "code-review-agent-linters",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "devDependencies": {}
}
JSON
fi
"$NPM_BIN" install --save-dev eslint @eslint/js vue-eslint-parser eslint-plugin-vue @typescript-eslint/parser @typescript-eslint/eslint-plugin

echo "[4/5] Installing gitleaks..."
install_gitleaks || echo "Skipped auto-install. Please install gitleaks manually."

echo "[5/5] Verifying Node/Security tools..."
./node_modules/.bin/eslint --version
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks version
else
  echo "gitleaks is not available in PATH"
fi

echo "Done. Lint/security tools are installed."
