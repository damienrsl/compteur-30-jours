#!/bin/bash
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin
cd "$(dirname "$0")" || exit 1
/usr/bin/python3 compteur.py
git add -A
git diff --cached --quiet || git commit -qm "Compteur $(date +%F)" && git push -q
