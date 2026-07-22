#!/bin/sh
# Publie le catalogue des jeux (catalog.json). Tous les hubs se mettent à jour
# au prochain démarrage — ajout/modif de projet SANS rebuild de l'exe.
#   ./publish-catalog.sh
set -e
cd "$(dirname "$0")"

python3 -c "import json; json.load(open('catalog.json'))" || { echo "catalog.json invalide"; exit 1; }

gh release view client >/dev/null 2>&1 || gh release create client \
    --title "Studio Echelon Client" --notes "Hub des jeux Echelon."
gh release upload client catalog.json --clobber

echo "✅ Catalogue publié — les hubs des joueurs se mettront à jour au prochain démarrage."
