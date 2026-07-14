#!/usr/bin/env bash
# bootstrap.sh - One-command setup for Linux, macOS, and WSL2.
# Usage: bash bootstrap.sh
# Windows-native users: use bootstrap.ps1 instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# -- Terminal colours ----------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}▸${NC} $*"; }
success() { echo -e "${GREEN}OK${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠? ${NC} $*"; }
die()     { echo -e "${RED}NO${NC} $*" >&2; exit 1; }

echo ""
echo "------------------------------------------------------------"
echo " Keyhole Developer Kit - bootstrap"
echo "------------------------------------------------------------"

# -- Python version check ------------------------------------------------------
PYTHON=""
for cmd in python3.11 python3.12 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done
[ -n "$PYTHON" ] || die "Python 3.9+ not found. Install Python 3.11 and retry."
info "Using Python: $($PYTHON --version)"

# -- Virtual environment -------------------------------------------------------
if [ ! -d ".venv" ]; then
    info "Creating virtual environment (.venv)..."
    "$PYTHON" -m venv .venv
else
    info "Virtual environment already exists (.venv)"
fi

# Activate for the remainder of the script
# shellcheck disable=SC1091
source .venv/bin/activate

# -- Install packages ----------------------------------------------------------
info "Upgrading pip..."
pip install --quiet --upgrade pip

info "Installing keyhole-sdk (editable)..."
pip install --quiet -e packages/python/keyhole-sdk

info "Installing keyhole-cli (editable)..."
pip install --quiet -e packages/python/keyhole-cli

info "Installing dev/test tools (pytest, ruff)..."
pip install --quiet pytest pytest-cov ruff

# -- Environment file ----------------------------------------------------------
if [ ! -f .env ]; then
    cp .env.example .env
    info "Copied .env.example -> .env"
else
    info ".env already exists - skipping copy"
fi

# -- Docker check --------------------------------------------------------------
if command -v docker &>/dev/null; then
    info "Docker found: $(docker --version | head -1)"
    info "To start the local test runtime, run:  docker compose up -d"
else
    warn "Docker not found - install Docker Desktop to run the test runtime."
fi

echo ""
success "Bootstrap complete."
echo ""
echo "  Next steps:"
echo "    source .venv/bin/activate   # activate the virtual environment"
echo "    docker compose up -d        # start the local test runtime"
echo "    keyhole doctor              # verify your environment"
echo "    keyhole --help              # explore CLI commands"
echo "------------------------------------------------------------"
