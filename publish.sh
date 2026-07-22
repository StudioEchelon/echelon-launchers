#!/bin/sh
# Publie une mise à jour de mod sur le canal live d'un jeu.
#   ./publish.sh harbor  ~/test/harbor-mod/build/libs/donshot-1.0.0.jar  1.0.1
#   ./publish.sh donshot ~/test/donshot/build/libs/donshot-1.0.0.jar    1.2.0
# Les launchers des joueurs se mettent à jour au prochain lancement.
set -e

GAME=$1
JAR=$2
VER=${3:-$(date +%Y.%m.%d.%H%M)}
[ -z "$GAME" ] || [ -z "$JAR" ] && { echo "usage: ./publish.sh <harbor|donshot> <jar> [version]"; exit 1; }
[ -f "$JAR" ] || { echo "jar introuvable: $JAR"; exit 1; }

case $GAME in
  harbor)  EXE=HarborLauncher.exe ;;
  donshot) EXE=DonShotLauncher.exe ;;
  *)       EXE="" ;;   # canal générique (echelonskin, futurs mods communs)
esac

SHA=$(shasum -a 256 "$JAR" | cut -d' ' -f1)
TMP=$(mktemp -d)
cp "$JAR" "$TMP/$GAME.jar"
# préserve launcher_version/url du manifest existant (ne JAMAIS l'écraser)
LV=$(curl -sL "https://github.com/StudioEchelon/echelon-launchers/releases/download/$GAME/manifest.json"      | python3 -c "import json,sys;print(json.load(sys.stdin).get('launcher_version','1.1'))" 2>/dev/null || echo "1.1")
cat > "$TMP/manifest.json" <<EOF
{
  "mod_version": "$VER",
  "mod_file": "$GAME.jar",
  "mod_sha256": "$SHA",
  "launcher_version": "$LV",
  "launcher_url_win": "https://github.com/StudioEchelon/echelon-launchers/releases/download/$GAME/$EXE"
}
EOF

gh release view "$GAME" >/dev/null 2>&1 || gh release create "$GAME" \
    --title "$GAME — canal live" --notes "Canal de mise à jour automatique du launcher $GAME."
gh release upload "$GAME" "$TMP/$GAME.jar" "$TMP/manifest.json" --clobber
rm -rf "$TMP"

echo "✅ $GAME $VER publié — les launchers se mettront à jour tout seuls."
