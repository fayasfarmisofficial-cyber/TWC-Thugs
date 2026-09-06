#!/usr/bin/env sh
# TWC Thugs · amu installer — idempotent. Entire CLI → graph plugin → amu (as `amu` and `entire amu`).
set -e
if ! command -v entire >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew tap entireio/tap && brew trust entireio/tap >/dev/null 2>&1 || true && brew install --cask entire
  else
    echo "Install the Entire CLI first: https://docs.entire.io (brew tap entireio/tap && brew install --cask entire)"; exit 3
  fi
fi
entire graph version >/dev/null 2>&1 || entire plugin install graph
if command -v pipx >/dev/null 2>&1; then
  pipx install --force "git+https://github.com/fayasfarmisofficial-cyber/TWC-Thugs" >/dev/null
else
  python3 -m pip install -q "git+https://github.com/fayasfarmisofficial-cyber/TWC-Thugs"
fi
echo "installed: amu $(amu --version 2>/dev/null | head -1)"
entire amu doctor || true
echo "next: cd <your repo> && amu init && amu map --file <file>"
