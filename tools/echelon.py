#!/usr/bin/env python3
"""echelon — le seul outil à connaître pour paramétrer le hub.

Tout ce qui apparaît dans le hub (projets, serveurs, nouveautés, mise en une…)
vient de `catalog.json`, lu par les clients à chaque démarrage. Éditer ce
fichier met donc à jour TOUS les joueurs, sans jamais recompiler d'exe.

    ./echelon list                          état de tous les projets
    ./echelon check                         valide le catalogue (à faire avant de publier)
    ./echelon add                           assistant : ajoute un projet
    ./echelon set <id> <champ> <valeur>     modifie un champ
    ./echelon news <id> add "…"             ajoute une nouveauté
    ./echelon news <id> clear               vide les nouveautés
    ./echelon preview                       lance le hub sur le catalogue LOCAL
    ./echelon publish                       check + publie (les joueurs suivent)

Exemples réels :
    ./echelon set harbor server 142.4.219.127:25600
    ./echelon set harbor featured true
    ./echelon set donshot tagline.fr "Hero shooter — 35 héros, duels, ligues."
    ./echelon set nouveaujeu hidden true      # préparé mais pas encore visible
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "catalog.json")
RELEASES = "https://github.com/StudioEchelon/echelon-launchers/releases/download"
LANGS = ("fr", "en", "es", "de", "pt", "it", "ru")

# champs que le hub sait lire ; tout le reste est ignoré (et signalé par check)
KNOWN = {
    "id", "name", "tagline", "accent", "accent_dim", "dir_name", "channel",
    "mod_file", "deps", "purge", "server", "news", "discord", "extra",
    "featured", "hidden", "logo_url", "bg_url", "card_url", "logo", "bg", "card",
    "rpc_asset",
}
REQUIRED = ("id", "name", "accent", "channel")

OK, WARN, BAD = "  ok  ", " att. ", " ERR  "


def load():
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)


def save(cat):
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
        f.write("\n")


def find(cat, gid):
    for g in cat["games"]:
        if g["id"] == gid:
            return g
    die("projet inconnu : %s (connus : %s)"
        % (gid, ", ".join(x["id"] for x in cat["games"])))


def die(msg):
    print("✗ " + msg)
    sys.exit(1)


# ── check ────────────────────────────────────────────────────────────────
def cmd_check(args):
    """Valide le catalogue. Sortie non nulle = ne publie pas."""
    cat = load()
    games = cat.get("games")
    if not isinstance(games, list) or not games:
        die("catalog.json : la clé \"games\" doit être une liste non vide")

    errors, warns = [], []
    seen = set()
    featured = []

    for n, g in enumerate(games):
        tag = g.get("id") or "#%d" % n
        for k in REQUIRED:
            if not g.get(k):
                errors.append("%s : champ requis manquant → %s" % (tag, k))
        gid = g.get("id", "")
        if gid and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", gid):
            errors.append("%s : id invalide (minuscules, chiffres, tirets)" % tag)
        if gid in seen:
            errors.append("%s : id en double" % tag)
        seen.add(gid)

        acc = g.get("accent", "")
        if acc and not re.fullmatch(r"#[0-9A-Fa-f]{6}", acc):
            errors.append("%s : accent doit être #RRGGBB (reçu %r)" % (tag, acc))
        if g.get("accent_dim") and not re.fullmatch(r"#[0-9A-Fa-f]{6}", g["accent_dim"]):
            errors.append("%s : accent_dim doit être #RRGGBB" % tag)

        tl = g.get("tagline")
        if isinstance(tl, dict):
            for need in ("fr", "en"):
                if not tl.get(need):
                    warns.append("%s : tagline.%s absente" % (tag, need))
            for lang in tl:
                if lang not in LANGS:
                    warns.append("%s : tagline.%s — langue non gérée" % (tag, lang))
        elif tl is None:
            warns.append("%s : pas de tagline" % tag)

        srv = g.get("server")
        if srv:
            m = re.fullmatch(r"([^\s:]+):(\d+)", str(srv))
            if not m:
                errors.append("%s : server doit être hote:port (reçu %r)" % (tag, srv))
            elif not (0 < int(m.group(2)) < 65536):
                errors.append("%s : port de server hors bornes" % tag)

        deps = g.get("deps", {})
        if not isinstance(deps, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in deps.items()):
            errors.append("%s : deps doit être un objet {prefixe: projet-modrinth}" % tag)

        if not isinstance(g.get("purge", []), list):
            errors.append("%s : purge doit être une liste" % tag)

        news = g.get("news", {})
        if news and not isinstance(news, dict):
            errors.append("%s : news doit être un objet {langue: [lignes]}" % tag)
        elif isinstance(news, dict):
            for lang, lines in news.items():
                if lang not in LANGS:
                    warns.append("%s : news.%s — langue non gérée" % (tag, lang))
                if not isinstance(lines, list):
                    errors.append("%s : news.%s doit être une liste" % (tag, lang))
                elif len(lines) > 4:
                    warns.append("%s : news.%s a %d lignes, le hub n'en affiche que 4"
                                 % (tag, lang, len(lines)))

        for ex in g.get("extra", []):
            if not isinstance(ex, dict) or not ex.get("channel") or not ex.get("file"):
                errors.append("%s : extra exige {channel, file}" % tag)

        for k in ("logo_url", "bg_url", "card_url"):
            u = g.get(k)
            if u and not str(u).startswith(("http://", "https://")):
                errors.append("%s : %s doit être une URL http(s)" % (tag, k))

        if g.get("featured") and not g.get("hidden"):
            featured.append(gid)

        for k in g:
            if k not in KNOWN:
                warns.append("%s : champ inconnu %r (le hub l'ignorera)" % (tag, k))

    if len(featured) > 3:
        warns.append("%d projets en une, le hub n'en montre que 3 (%s)"
                     % (len(featured), ", ".join(featured)))
    if not featured:
        warns.append("aucun projet `featured` : le hub prendra les 3 premiers")

    visible = [g for g in games if not g.get("hidden")]
    if not visible:
        errors.append("tous les projets sont `hidden` : le hub n'afficherait rien")

    # Rich Presence : UNE app pour tous les projets, une clé d'asset par projet
    rpc = cat.get("rpc")
    if not isinstance(rpc, dict) or not rpc.get("app_id"):
        warns.append("rpc.app_id absent : pas de Rich Presence (voir catalog/README)")
    else:
        if not re.fullmatch(r"\d{17,20}", str(rpc["app_id"])):
            errors.append("rpc.app_id doit être l'identifiant numérique de l'application Discord")
        keys = [(g.get("id"), g.get("rpc_asset") or g.get("id")) for g in visible]
        for gid, key in keys:
            if not re.fullmatch(r"[a-z0-9_-]+", str(key)):
                errors.append("%s : rpc_asset invalide (%r) — minuscules, chiffres, - et _"
                              % (gid, key))
        dbl = [k for k in set(x[1] for x in keys)
               if [x[1] for x in keys].count(k) > 1]
        if dbl:
            warns.append("clés rpc_asset partagées par plusieurs projets : %s"
                         % ", ".join(dbl))

    for w in warns:
        print(WARN + w)
    for e in errors:
        print(BAD + e)
    if not errors:
        print(OK + "%d projets, %d visibles — catalogue valide"
              % (len(games), len(visible)))
    return 1 if errors else 0


# ── list ─────────────────────────────────────────────────────────────────
def cmd_list(args):
    cat = load()
    print("%-12s %-11s %-4s %-4s %-22s %s"
          % ("id", "canal", "une", "vis", "serveur", "nouveautés"))
    print("-" * 78)
    for g in cat["games"]:
        news = g.get("news", {})
        cnt = "/".join("%s:%d" % (l, len(v)) for l, v in news.items()) or "—"
        print("%-12s %-11s %-4s %-4s %-22s %s"
              % (g["id"], g.get("channel", "—"),
                 "★" if g.get("featured") else "",
                 "" if g.get("hidden") else "✓",
                 g.get("server", "—"), cnt))
    return 0


# ── set ──────────────────────────────────────────────────────────────────
def coerce(v):
    if v.lower() in ("true", "oui", "yes"):
        return True
    if v.lower() in ("false", "non", "no"):
        return False
    if v.lower() in ("null", "none", ""):
        return None
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def cmd_set(args):
    if len(args) < 3:
        die("usage: ./echelon set <id> <champ> <valeur>\n"
            "       champ pointé accepté : tagline.fr, deps.sodium")
    gid, path, raw = args[0], args[1], " ".join(args[2:])
    cat = load()
    g = find(cat, gid)
    val = coerce(raw)
    parts = path.split(".")
    node = g
    for p in parts[:-1]:
        node = node.setdefault(p, {})
        if not isinstance(node, dict):
            die("%s n'est pas un objet, impossible d'y écrire %s" % (p, path))
    if val is None:
        node.pop(parts[-1], None)
        print(OK + "%s : %s supprimé" % (gid, path))
    else:
        node[parts[-1]] = val
        print(OK + "%s : %s = %r" % (gid, path, val))
    save(cat)
    if path not in KNOWN and parts[0] not in KNOWN:
        print(WARN + "champ %r inconnu du hub — il l'ignorera" % path)
    print("      → ./echelon publish  pour l'envoyer aux joueurs")
    return 0


# ── news ─────────────────────────────────────────────────────────────────
def cmd_news(args):
    if len(args) < 2:
        die('usage: ./echelon news <id> add "texte" [langue]\n'
            "       ./echelon news <id> clear [langue]")
    gid, action = args[0], args[1]
    cat = load()
    g = find(cat, gid)
    news = g.setdefault("news", {})
    if action == "clear":
        lang = args[2] if len(args) > 2 else None
        if lang:
            news.pop(lang, None)
            print(OK + "%s : nouveautés %s vidées" % (gid, lang))
        else:
            g["news"] = {}
            print(OK + "%s : toutes les nouveautés vidées" % gid)
    elif action == "add":
        if len(args) < 3:
            die('usage: ./echelon news <id> add "texte" [langue=fr]')
        text = args[2]
        lang = args[3] if len(args) > 3 else "fr"
        lines = news.setdefault(lang, [])
        lines.append(text)
        print(OK + "%s : news.%s → %d lignes" % (gid, lang, len(lines)))
        if len(lines) > 4:
            print(WARN + "le hub n'affiche que les 4 premières")
    else:
        die("action inconnue : %s (add | clear)" % action)
    save(cat)
    print("      → ./echelon publish  pour l'envoyer aux joueurs")
    return 0


# ── add ──────────────────────────────────────────────────────────────────
def ask(label, default=""):
    suffix = " [%s]" % default if default else ""
    try:
        v = input("  %s%s : " % (label, suffix)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    return v or default


def cmd_add(args):
    cat = load()
    print("Nouveau projet — Entrée accepte la valeur entre crochets.\n")
    gid = ask("id (minuscules, ex. glaivolver)")
    if not gid:
        die("id obligatoire")
    if any(g["id"] == gid for g in cat["games"]):
        die("ce projet existe déjà : %s" % gid)
    name = ask("nom affiché", gid.upper())
    accent = ask("couleur accent #RRGGBB", "#5AE68C")
    channel = ask("canal de release du mod", gid)
    tag_fr = ask("tagline FR")
    tag_en = ask("tagline EN", tag_fr)
    server = ask("serveur hote:port (vide si aucun)")
    discord = ask("lien Discord", "https://playechelon.net")
    feat = ask("mettre en une ? (oui/non)", "non").lower() in ("oui", "yes", "true")

    g = {
        "id": gid,
        "name": name,
        "tagline": {"fr": tag_fr, "en": tag_en},
        "accent": accent,
        "dir_name": name.replace(" ", ""),
        "channel": channel,
        "mod_file": gid + ".jar",
        "deps": {"fabric-api": "fabric-api", "sodium": "sodium", "lithium": "lithium"},
        "purge": [],
        "news": {"fr": [], "en": []},
        "discord": discord,
        # visible seulement quand tu le décides : les images et le canal
        # doivent exister avant, sinon les joueurs voient un projet cassé.
        "hidden": True,
    }
    if server:
        g["server"] = server
    if feat:
        g["featured"] = True
    cat["games"].append(g)
    save(cat)

    print("\n" + OK + "%s ajouté à catalog.json, en `hidden` pour l'instant.\n" % gid)
    print("Il reste 3 choses à faire avant de le rendre visible :")
    print("  1. les visuels — logo, fond, et carte portrait 3:4 (optionnelle) :")
    print("       gh release upload client %s_logo.png %s_bg.png --clobber" % (gid, gid))
    print("       ./echelon set %s logo_url %s/client/%s_logo.png" % (gid, RELEASES, gid))
    print("       ./echelon set %s bg_url   %s/client/%s_bg.png" % (gid, RELEASES, gid))
    print("  2. le mod sur son canal :")
    print("       ./publish.sh %s <chemin/vers/%s.jar> 1.0.0" % (channel, gid))
    print("  3. aperçu, puis ouverture aux joueurs :")
    print("       ./echelon preview")
    print("       ./echelon set %s hidden false" % gid)
    print("       ./echelon publish")
    return 0


# ── preview ──────────────────────────────────────────────────────────────
def cmd_preview(args):
    """Lance le hub sur le catalogue LOCAL — rien n'est publié."""
    if cmd_check([]) != 0:
        die("catalogue invalide : aperçu annulé")
    entry = os.path.join(ROOT, "client", "launcher.py")
    venv = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
    if not os.path.exists(venv):
        venv = os.path.join(ROOT, ".venv", "bin", "python")
    exe = venv if os.path.exists(venv) else sys.executable
    env = dict(os.environ, ECHELON_CATALOG=CATALOG)
    print(OK + "aperçu sur %s (aucune publication)" % CATALOG)
    subprocess.Popen([exe, entry], cwd=os.path.dirname(entry), env=env)
    return 0


# ── publish ──────────────────────────────────────────────────────────────
def cmd_publish(args):
    if cmd_check([]) != 0:
        die("catalogue invalide : publication annulée")
    script = os.path.join(ROOT, "publish-catalog.sh")
    print("→ %s" % script)
    return subprocess.call(["sh", script])


def cmd_release(args):
    """Prépare la publication d'un jar de mod sur son canal.

        ./echelon release harbor ../harbor-mod/build/libs/harbor-1.0.0.jar 1.1.64
        ./echelon release riposte ../riposte/build/libs/riposte-1.0.0.jar 1.0.0

    Le jar part directement en asset de release via `gh` — il n'entre JAMAIS
    dans git (un binaire de 30 Mo par version gonflerait l'historique pour
    toujours). Sans `--yes`, on s'arrête après les vérifications sans rien
    envoyer : c'est un mode blanc.
    """
    import hashlib
    import json as _json
    import tempfile
    import urllib.request
    import zipfile
    if len(args) < 3:
        die("usage: ./echelon release <canal> <jar> <version> [--yes]")
    channel, jar, ver = args[0], args[1], args[2]
    go = "--yes" in args

    if not os.path.isfile(jar):
        die("jar introuvable : %s" % jar)
    if not zipfile.is_zipfile(jar):
        die("ce n'est pas un jar : %s" % jar)
    with zipfile.ZipFile(jar) as z:
        names = z.namelist()
    if "fabric.mod.json" not in names:
        die("pas de fabric.mod.json dans le jar — ce n'est pas un mod Fabric")
    if not re.fullmatch(r"[\w.+-]+", ver):
        die("version invalide : %r" % ver)

    sha = hashlib.sha256(open(jar, "rb").read()).hexdigest()
    mo = os.path.getsize(jar) / (1024.0 * 1024.0)

    # manifest en place : on préserve les infos du launcher et on compare
    man = {}
    try:
        req = urllib.request.Request(RELEASES + "/" + channel + "/manifest.json",
                                     headers={"User-Agent": "echelon-cli"})
        man = _json.load(urllib.request.urlopen(req, timeout=10))
    except Exception:
        print(WARN + "pas de manifest publié pour %s (premier envoi ?)" % channel)
    if man.get("mod_sha256") == sha:
        print(WARN + "ce jar est DÉJÀ publié (sha identique) — rien à faire")
        return 0
    if man.get("mod_version") == ver:
        die("le jar diffère mais la version reste %s : les launchers comparent\n"
            "       mod_version, les joueurs ne verraient PAS la mise à jour." % ver)

    print("  canal      %s" % channel)
    print("  version    %s%s" % (ver, ("  (avant : %s)" % man["mod_version"])
                                 if man.get("mod_version") else ""))
    print("  jar        %.1f Mo%s" % (mo, ("  (publié : %.1f Mo)"
                                           % (man.get("mod_size", 0) / 1048576.0))
                                      if man.get("mod_size") else ""))
    print("  sha256     %s…" % sha[:16])

    if not go:
        print("\n" + WARN + "MODE BLANC — rien n'a été envoyé.")
        print("      Publier = tous les joueurs reçoivent ce jar au prochain lancement,")
        print("      et le serveur doit tourner le MÊME jar (redémarrage = joueurs coupés).")
        print("      Quand tu es sûr :  ./echelon release %s %s %s --yes"
              % (channel, jar, ver))
        return 0

    man.update({"mod_version": ver, "mod_file": channel + ".jar",
                "mod_sha256": sha, "mod_size": os.path.getsize(jar)})
    man.setdefault("launcher_version", "1.1")
    tmp = tempfile.mkdtemp()
    shutil.copyfile(jar, os.path.join(tmp, channel + ".jar"))
    with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
        _json.dump(man, f, indent=2)

    if subprocess.call(["gh", "release", "view", channel],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE) != 0:
        subprocess.check_call(["gh", "release", "create", channel,
                               "--title", "%s — canal live" % channel,
                               "--notes", "Canal de mise à jour automatique du mod %s."
                               % channel])
    rc = subprocess.call(["gh", "release", "upload", channel,
                          os.path.join(tmp, channel + ".jar"),
                          os.path.join(tmp, "manifest.json"), "--clobber"])
    if rc == 0:
        print(OK + "%s %s publié — les joueurs l'auront au prochain lancement" % (channel, ver))
    return rc


def cmd_set_rpc(args):
    """champs du bloc `rpc` (l'unique application Discord, partagée)."""
    if len(args) < 2:
        die("usage: ./echelon set-rpc <champ> <valeur>   (app_id, small_asset,\n"
            "       button_label, button_url)")
    cat = load()
    rpc = cat.setdefault("rpc", {})
    key, val = args[0], " ".join(args[1:])
    rpc[key] = coerce(val)
    save(cat)
    print(OK + "rpc.%s = %r" % (key, rpc[key]))
    print("      → ./echelon check puis publish")
    return 0


COMMANDS = {
    "list": cmd_list, "check": cmd_check, "set": cmd_set, "news": cmd_news,
    "add": cmd_add, "preview": cmd_preview, "publish": cmd_publish,
    "set-rpc": cmd_set_rpc, "release": cmd_release,
}


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = COMMANDS.get(argv[1])
    if not cmd:
        die("commande inconnue : %s (%s)" % (argv[1], " | ".join(COMMANDS)))
    return cmd(argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
