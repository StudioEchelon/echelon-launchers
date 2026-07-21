#!/bin/sh
# Publie une MISE À JOUR DU HUB (StudioEchelonClient). Les hubs des joueurs se
# remplacent tout seuls au prochain démarrage.
#   1. modifie client/launcher.py
#   2. ./publish-client.sh 1.1
set -e
VER=$1
[ -z "$VER" ] && { echo "usage: ./publish-client.sh <version>"; exit 1; }

cd "$(dirname "$0")"

# 1) bump CLIENT_VERSION
sed -i '' "s/^CLIENT_VERSION = \".*\"/CLIENT_VERSION = \"$VER\"/" client/launcher.py
python3 -m py_compile client/launcher.py

# 2) push → build Windows (Actions)
git add client/launcher.py
git commit -m "hub client v$VER"
git push
echo "⏳ Build Windows en cours…"
sleep 10
RUN_ID=$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status

# 3) récupère l'exe, calcule le sha, publie sur le canal client
TMP=$(mktemp -d)
gh run download "$RUN_ID" --name StudioEchelonClient --dir "$TMP"
SHA=$(shasum -a 256 "$TMP/StudioEchelonClient.exe" | cut -d' ' -f1)
cat > "$TMP/manifest.json" <<EOF
{
  "client_version": "$VER",
  "client_url": "https://github.com/StudioEchelon/echelon-launchers/releases/download/client/StudioEchelonClient.exe",
  "client_sha256": "$SHA"
}
EOF

gh release view client >/dev/null 2>&1 || gh release create client \
    --title "Studio Echelon Client" --notes "Hub des jeux Echelon."
gh release upload client "$TMP/StudioEchelonClient.exe" "$TMP/manifest.json" --clobber
rm -rf "$TMP"

echo "✅ Hub v$VER en ligne — les joueurs se mettront à jour au prochain démarrage."
