#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Trend Scraper – one-command installer (no Docker required)
#
#  What this script does:
#    1. Checks that Python 3.11+ is installed
#    2. Creates a virtual environment (.venv)
#    3. Installs all Python dependencies
#    4. Copies .env.example → .env if no .env exists yet
#    5. Prints next steps
#
#  Usage:
#    chmod +x install.sh   (only needed once)
#    ./install.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[✔]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
error()   { echo -e "${RED}[✘]${RESET} $*"; exit 1; }
section() { echo -e "\n${YELLOW}──── $* ────${RESET}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "  ████████╗██████╗ ███████╗███╗   ██╗██████╗ "
echo "  ╚══██╔══╝██╔══██╗██╔════╝████╗  ██║██╔══██╗"
echo "     ██║   ██████╔╝█████╗  ██╔██╗ ██║██║  ██║"
echo "     ██║   ██╔══██╗██╔══╝  ██║╚██╗██║██║  ██║"
echo "     ██║   ██║  ██║███████╗██║ ╚████║██████╔╝"
echo "     ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ "
echo "           SCRAPER  –  installer"
echo ""

# ── 1. Check Python ───────────────────────────────────────────────────────────
section "Checking Python"

if ! command -v python3 &>/dev/null; then
    error "Python 3 is not installed. Download it from https://python.org"
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED_MAJOR=3
REQUIRED_MINOR=11

MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$MAJOR" -lt "$REQUIRED_MAJOR" ] || { [ "$MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$MINOR" -lt "$REQUIRED_MINOR" ]; }; then
    error "Python $PYTHON_VERSION found, but 3.11 or newer is required. Download from https://python.org"
fi

info "Python $PYTHON_VERSION found"

# ── 2. Create virtual environment ─────────────────────────────────────────────
section "Setting up virtual environment"

if [ -d ".venv" ]; then
    warn ".venv already exists – skipping creation"
else
    python3 -m venv .venv
    info "Created .venv"
fi

# Activate
# shellcheck disable=SC1091
source .venv/bin/activate
info "Virtual environment activated"

# ── 3. Install dependencies ───────────────────────────────────────────────────
section "Installing dependencies"

pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
info "All dependencies installed"

# ── 4. Environment file ───────────────────────────────────────────────────────
section "Environment configuration"

if [ -f ".env" ]; then
    warn ".env already exists – leaving it unchanged"
else
    cp .env.example .env
    info "Created .env from .env.example"
    warn "Open .env and set your DATABASE_URL before starting the app"
fi

# ── 5. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Installation complete!${RESET}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit your settings (only needed once):"
echo "       open .env"
echo ""
echo "  2. Start the API  (Terminal window 1):"
echo "       source .venv/bin/activate"
echo "       uvicorn api.main:app --reload --port 8000"
echo ""
echo "  3. Start the data collector  (Terminal window 2):"
echo "       source .venv/bin/activate"
echo "       python -m workers.scheduler"
echo ""
echo "  4. Open in your browser:"
echo "       http://localhost:8000/docs"
echo ""
echo "  ── OR, if you have Docker installed, just run: ──"
echo ""
echo "       docker compose up"
echo ""
