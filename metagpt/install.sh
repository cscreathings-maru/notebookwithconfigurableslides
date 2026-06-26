#!/usr/bin/env bash
# MetaGPT environment setup. Run on your machine (NOT inside the app sandbox).
# Requires: conda (or pyenv), and Node.js + pnpm available on PATH.
set -euo pipefail

echo "==> Checking prerequisites"
command -v node >/dev/null || { echo "Install Node.js first: https://nodejs.org"; exit 1; }
command -v pnpm >/dev/null || { echo "Install pnpm first: npm i -g pnpm"; exit 1; }

echo "==> Creating Python env (MetaGPT needs Python 3.9–3.11; using 3.11)"
if command -v conda >/dev/null; then
  conda create -y -n metagpt python=3.11
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate metagpt
else
  echo "conda not found — create a venv with Python 3.11 manually, then re-run from 'pip install'."
  python3 --version
fi

echo "==> Installing MetaGPT"
pip install --upgrade pip
pip install --upgrade metagpt

echo "==> Writing config"
mkdir -p "$HOME/.metagpt"
if [ ! -f "$HOME/.metagpt/config2.yaml" ]; then
  cp "$(dirname "$0")/config2.example.yaml" "$HOME/.metagpt/config2.yaml"
  echo "Created ~/.metagpt/config2.yaml — edit it and set your DeepSeek API key."
else
  echo "~/.metagpt/config2.yaml already exists — leaving it untouched."
fi

echo "==> Verify"
metagpt --help >/dev/null && echo "MetaGPT installed."
echo "Next: edit ~/.metagpt/config2.yaml, then see OPERATOR-GUIDE.md to run a slice."
