# Paramétrer le hub — un seul fichier, un seul outil

Tout ce que le hub affiche vient de **`catalog.json`**, publié sur le canal `client`.
Les clients le relisent **à chaque démarrage** : modifier ce fichier met à jour
**tous les joueurs**, sans jamais recompiler ni redistribuer d'exe.

Tu n'as pas à éditer le JSON à la main — `./echelon` fait tout :

```sh
./echelon list                          # état de tous les projets
./echelon check                         # valide (publish refuse si ça échoue)
./echelon add                           # assistant : nouveau projet
./echelon set <id> <champ> <valeur>     # modifie un champ
./echelon news <id> add "…"             # ajoute une nouveauté
./echelon preview                       # ouvre le hub sur le catalogue LOCAL
./echelon publish                       # check + envoi aux joueurs
```

> ⚠️ **Il y a de vrais joueurs en prod.** `./echelon preview` lit le catalogue local
> sans rien publier et sans toucher au cache d'un joueur — passe toujours par là
> avant `publish`.

## Les gestes du quotidien

| Ce que tu veux faire | La commande |
| --- | --- |
| Changer l'IP d'un serveur | `./echelon set harbor server 1.2.3.4:25600` |
| Mettre un projet en une | `./echelon set harbor featured true` |
| Retirer un projet de la une | `./echelon set harbor featured false` |
| Cacher un projet (préparation) | `./echelon set nouveau hidden true` |
| Ouvrir un projet aux joueurs | `./echelon set nouveau hidden false` |
| Corriger une accroche | `./echelon set donshot tagline.fr "…"` |
| Changer la couleur d'un jeu | `./echelon set harbor accent #5AE68C` |
| Annoncer une nouveauté | `./echelon news harbor add "10 nouveaux donjons"` |
| Repartir de zéro sur les news | `./echelon news harbor clear` |
| Ajouter une dépendance Modrinth | `./echelon set harbor deps.geckolib geckolib` |

Rien de tout ça ne demande de rebuild : `./echelon publish` suffit.

## Ajouter un projet

```sh
./echelon add
```

L'assistant crée l'entrée **en `hidden`** — un projet n'apparaît jamais aux joueurs
avant que ses visuels et son canal de mod existent. Il t'affiche ensuite les 3 étapes
restantes : héberger les images, publier le mod, puis passer `hidden` à `false`.

Héberger les visuels d'un projet (ils vivent sur le canal `client`) :

```sh
gh release upload client monjeu_logo.png monjeu_bg.png monjeu_card.png --clobber
```

Puis pointe-les — le hub télécharge et cache (re-télécharge si l'URL change) :

```sh
./echelon set monjeu logo_url https://github.com/StudioEchelon/echelon-launchers/releases/download/client/monjeu_logo.png
./echelon set monjeu bg_url   .../monjeu_bg.png
./echelon set monjeu card_url .../monjeu_card.png     # optionnel
```

## Les champs

| Champ | Rôle |
| --- | --- |
| `id` | identifiant technique, minuscules/chiffres/tirets. **Ne le change plus** après publication : il sert de clé au dossier de jeu et aux versions installées. |
| `name` | nom affiché (`HARBOR`) |
| `accent` | `#RRGGBB` — pilote le liseré du rail, JOUER, les badges, les points de chargement |
| `accent_dim` | variante sombre, optionnelle |
| `channel` | canal de release GitHub du mod (`./publish.sh <channel> …`) |
| `tagline` | `{fr, en, …}` — 7 langues gérées, `fr` et `en` attendues |
| `server` | `hote:port` — sert le compteur « N en ligne ». Absent = pas de ping. |
| `news` | `{langue: [4 lignes max]}` — panneau Accueil + page Nouveautés |
| `featured` | ★ rangée « EN UNE » de l'Accueil. **3 maximum** ; au-delà le hub ignore le reste. Aucun `featured` = les 3 premiers. |
| `hidden` | `true` = invisible partout (projet en préparation) |
| `deps` | `{prefixe-de-fichier: projet-modrinth}` installées automatiquement |
| `purge` | préfixes de mods à supprimer du dossier (incompatibilités) |
| `extra` | `[{channel, file}]` — mods communs, ex. `echelonskin` |
| `logo_url` / `bg_url` | visuels distants (wordmark + key-art plein écran) |
| `card_url` | carte portrait 3:4 de la Bibliothèque. Absent = le key-art est recadré. |
| `dir_name` | nom du dossier dans `%APPDATA%`. Défaut : `name` sans espaces. |
| `mod_file` | nom du jar. Défaut : `<id>.jar`. |

Champs déduits automatiquement, à ne pas mettre : `dir`, `base`, `seed`, `card`, `logo`, `bg`.

## Discord Rich Presence — UNE application, pas une par projet

Le piège classique est de créer une application Discord par jeu : un
`application_id` par projet, des assets à uploader partout, et N apps à
maintenir. Ici il y a **une seule application** pour tout Studio Echelon, et
**une clé d'asset par projet**.

Le catalogue porte le bloc :

```json
"rpc": {
  "app_id": "",
  "small_asset": "echelon",
  "button_label": "Studio Echelon",
  "button_url": "https://playechelon.net"
}
```

Mise en place, une seule fois :

1. Crée **une** application sur `discord.com/developers/applications`, nom `Studio Echelon`.
2. Dans *Rich Presence → Art Assets*, uploade une image par projet, nommée exactement
   comme son `rpc_asset` (par défaut l'id du jeu : `harbor`, `donshot`, …), plus une
   image `echelon` pour la petite icône du studio.
3. `./echelon set-rpc app_id <l'identifiant numérique>` — ou colle-le dans `catalog.json`.
4. `./echelon publish`.

Ensuite, **ajouter un projet ne demande plus rien côté Discord** à part uploader
son image dans l'app existante : la clé `rpc_asset` est déduite de l'id, et
`echelon check` refuse une clé mal formée ou partagée par deux projets.

Le hub affiche le projet sélectionné (nom, accroche, nombre de joueurs en ligne,
logo du projet en grande image, icône studio en petite). L'option *Discord Rich
Presence* des réglages par jeu coupe la présence pour ce projet.

## Les autres canaux de publication

`catalog.json` couvre le **contenu**. Pour le **code**, les scripts existants restent :

| Quoi | Commande |
| --- | --- |
| Nouvelle version d'un mod | `./publish.sh harbor <jar> 1.2.0` |
| Nouvelle version du hub | `./publish-client.sh 1.6` |
| Nouvelle version d'un launcher mono-jeu | `./publish-launcher.sh harbor 1.2` |

Les trois se répandent tout seuls : le hub compare `client_version` au démarrage et se
remplace, et chaque jeu compare `mod_version` avant de lancer.

## Aperçu sans publier

```sh
./echelon preview
```

Lance le hub depuis les sources sur `catalog.json` local via la variable
`ECHELON_CATALOG`. Dans ce mode le hub **n'écrit pas** dans le cache de catalogue,
donc ton install de test ne se retrouve pas avec un catalogue non publié.
