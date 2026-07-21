#!/bin/sh
# Publie une MISE À JOUR DU LAUNCHER lui-même (l'exe se remplace chez les joueurs).
#   1. modifie harbor/launcher.py (ou donshot/launcher.py)
#   2. ./publish-launcher.sh harbor 1.2
# Fait tout : bump version, push, build Windows (Actions), upload exe, manifest.
set -e

GAME=$1
VER=$2
[ -z "$GAME" ] || [ -z "$VER" ] && { echo "usage: ./publish-launcher.sh <harbor|donshot> <version>"; exit 1; }

case $GAME in
  harbor)  EXE=HarborLauncher.exe ;;
  donshot) EXE=DonShotLauncher.exe ;;
  *) echo "jeu inconnu: $GAME"; exit 1 ;;
esac

cd "$(dirname "$0")"

# 1) bump de LAUNCHER_VERSION dans le code
sed -i '' "s/^LAUNCHER_VERSION = \".*\"/LAUNCHER_VERSION = \"$VER\"/" "$GAME/launcher.py"
python3 -m py_compile "$GAME/launcher.py"

# 2) push → GitHub Actions build l'exe sur Windows
git add "$GAME/launcher.py"
git commit -m "$GAME launcher v$VER"
git push
echo "⏳ Build Windows en cours…"
sleep 10
RUN_ID=$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status

# 3) récupère l'exe et le pousse sur le canal live
TMP=$(mktemp -d)
gh run download "$RUN_ID" --name "${EXE%.exe}" --dir "$TMP"
gh release upload "$GAME" "$TMP/$EXE" --clobber

# 4) manifest : monte launcher_version SANS toucher aux infos du mod
curl -sL "https://github.com/StudioEchelon/echelon-launchers/releases/download/$GAME/manifest.json" \
    > "$TMP/manifest.json"
python3 - "$TMP/manifest.json" "$VER" <<'EOF'
import json, sys
p, ver = sys.argv[1], sys.argv[2]
m = json.load(open(p))
m["launcher_version"] = ver
json.dump(m, open(p, "w"), indent=2)
EOF
gh release upload "$GAME" "$TMP/manifest.json" --clobber
rm -rf "$TMP"

echo "✅ Launcher $GAME v$VER en ligne — les exe des joueurs se remplaceront au prochain lancement."
