# Instructions

## ⚠️ Il y a de vrais joueurs en prod
Le catalogue et les canaux de release alimentent des joueurs réels, en direct.
- **Contenu** (catalog.json) : publiable sur simple demande — réversible, personne n'est déconnecté.
- **Code** (jars de mod, exe du hub/launchers) et **redémarrages Pterodactyl** : **jamais** sans accord explicite de Thomas, ça coupe des sessions en cours.

## Paramétrer le hub : toujours par `./echelon`
`catalog.json` est la source unique de ce que le hub affiche. **Ne l'édite pas à la main.**
```sh
./echelon list | check | add | set <id> <champ> <valeur> | news <id> add "…" | preview | publish
```
- `./echelon check` avant toute publication (il est aussi rejoué en CI).
- `./echelon preview` lance le hub sur le catalogue **local** via `ECHELON_CATALOG`, sans rien publier ni polluer le cache d'un joueur. **Toujours passer par là avant `publish`.**
- Référence complète des champs → `catalog/README.md`.

## Publication
| Quoi | Comment | Garde-fou |
| --- | --- | --- |
| Catalogue (contenu) | commit + push de `catalog.json` sur `master` | workflow `publish-catalog.yml` : `echelon check` puis upload. Auto. |
| Mod d'un jeu | `./publish.sh <canal> <jar> <version>` | demander d'abord |
| Hub | `./publish-client.sh <version>` | demander d'abord |
| Launcher mono-jeu | `./publish-launcher.sh <jeu> <version>` | demander d'abord |

## Dev local
- Venv : `.venv` (Python 3.12, `pillow`, `minecraft-launcher-lib`).
- Lancer : **`pythonw.exe`**, jamais `python.exe` — celui-ci ouvre une console noire par-dessus.
- Compiler pour vérifier : `python -m py_compile client/launcher.py`.

## UI — conventions de `client/launcher.py`
- **Un seul canvas Tk**, tout est dessiné à la main en **coordonnées absolues**. Fenêtre **1280×760 figée**.
- `_draw()` est un **routeur de pages** (`home` / `library` / `news` / `downloads`) : contenu de page, puis rail, puis barre haute, puis modales, puis l'UI de chargement. L'ordre compte — le rail et le bandeau d'en-tête **masquent volontairement** le débord des grilles qui défilent, ce qui évite de clipper le canvas.
- Toute nouvelle zone cliquable doit être ajoutée à **`_ZONE_ATTRS`**, tout nouvel item animé à **`_ITEM_ATTRS`** : ils sont remis à zéro à chaque redraw, sinon une zone d'une autre page continue de répondre.
- Le rail porte des **sections**, jamais la liste des jeux — c'est ce qui permet d'aligner 20 projets.
- **DA à ne pas dériver** : fond `#0A0C0E`, accent **par jeu** tiré du catalogue, police Zalando Expanded, panneaux verre via `_flat()`, cartes via `_cover()`. Les animations restent amorties et discrètes (`NAV_EASE`, `LIFT_EASE`, `PAGE_FADE_STEPS`).
- `subprocess.Popen` est patché globalement avec `CREATE_NO_WINDOW` (en tête de fichier) : c'est ce qui empêche l'installeur Fabric d'ouvrir une console. **Ne pas le contourner.**

## Ne jamais annoncer un rendu comme validé sans l'avoir vu
Le client est graphique : un process vivant et un log ne prouvent rien. Pour vérifier,
capturer la fenêtre (EnumWindows + `PIL.ImageGrab`, échelle physique 2× sur cet écran 4K)
et la regarder. Sinon, le dire explicitement.
