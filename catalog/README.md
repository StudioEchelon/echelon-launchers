# Catalogue des jeux — modifiable à distance, zéro rebuild

La liste des jeux du hub vient de **`catalog.json`** (publié sur le canal `client`).
Le hub le lit à chaque démarrage → **modifier le catalogue met à jour tous les joueurs**,
sans jamais recompiler ni redistribuer l'exe.

## Ajouter / modifier un jeu
1. Édite `catalog.json` (à la racine du repo).
2. Pour un NOUVEAU jeu, ajoute un objet avec :
   - `id`, `name`, `accent` (couleur hex), `channel` (canal de release du mod)
   - `tagline` : les 7 langues
   - `logo_url`, `bg_url` : URLs des images (voir ci-dessous pour les héberger)
   - `deps` : dépendances Modrinth, `discord` : lien
3. `./publish-catalog.sh`

## Héberger le logo + le fond d'un jeu
Upload les 2 images sur le canal `client` (elles servent le catalogue) :
```sh
gh release upload client mon_jeu_logo.png mon_jeu_bg.png --clobber
```
puis mets leurs URLs `.../download/client/mon_jeu_logo.png` dans `catalog.json`.

Le hub télécharge et cache les images (re-téléchargées si l'URL change).

## Champs auto-déduits (pas besoin de les mettre)
`dir` (dossier du jeu), `base` (canal de release), `seed` (uuid), `mod_file` (`<id>.jar`),
`play` (traduit). Optionnel : `dir_name`, `mod_file`, `accent_dim`.
