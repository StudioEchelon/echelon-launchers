#!/usr/bin/env python3
"""Panneau web LOCAL de gestion du hub Studio Echelon.

    ./echelon web          ouvre http://127.0.0.1:8770

Tout se pilote ici : projets, modpack, reglages, publication. Le panneau
n'ecrit JAMAIS catalog.json lui-meme — il appelle tools/echelon.py, qui valide.
Trois consequences voulues :
  - la meme validation protege le terminal et le navigateur ;
  - une commande a la fois (verrou), parce que save() reecrit tout le fichier
    sans temporaire : deux ecritures simultanees le tronqueraient ;
  - copie horodatee du catalogue avant chaque commande mutante.

Il n'ecoute que sur 127.0.0.1 et ne demande aucun secret.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ECHELON = os.path.join(ROOT, "tools", "echelon.py")
CATALOG = os.path.join(ROOT, "catalog.json")
BACKUPS = os.path.join(ROOT, ".panel-backups")
RELEASES = "https://github.com/StudioEchelon/echelon-launchers/releases/download"
MODRINTH = "https://api.modrinth.com/v2"
PORT = int(os.environ.get("ECHELON_PANEL_PORT", "8770"))
JARS = os.path.join(ROOT, ".panel-jars")
ARTS = os.path.join(ROOT, ".panel-art")
MAX_ART = 12 * 1024 * 1024
ROLES = ("logo", "bg", "card")
MAX_JAR = 200 * 1024 * 1024

VERROU = threading.Lock()
JOURNAL = []
_CACHE = {}

# publie : touche les joueurs, exige une confirmation explicite.
# blanc  : sans --yes la commande n'envoie rien (mode blanc) — on la laisse
#          passer sans confirmation pour que le panneau puisse l'afficher.
COMMANDES = {
    "list":    {"publie": False, "mute": False},
    "check":   {"publie": False, "mute": False},
    "config":  {"publie": False, "mute": True},
    "set":     {"publie": False, "mute": True},
    "news":    {"publie": False, "mute": True},
    "set-rpc": {"publie": False, "mute": True},
    "add":     {"publie": False, "mute": True},
    "preview": {"publie": False, "mute": False},
    "publish": {"publie": True,  "mute": False},
    "release": {"publie": True,  "mute": False, "blanc": True},
    "client":  {"publie": True,  "mute": False, "blanc": True},
    "art":     {"publie": True,  "mute": True,  "blanc": True},
}

RESERVES = re.compile(r"^(true|oui|yes|false|non|no|null|none|-?\d+)$", re.I)


def _run(args, timeout=900, cwd=ROOT):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        out = (p.stdout or b"") + (p.stderr or b"")
        return p.returncode, out.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "delai depasse (%ds)" % timeout
    except Exception as e:
        return 1, "echec: %s" % e


def _sauvegarde():
    try:
        os.makedirs(BACKUPS, exist_ok=True)
        dst = os.path.join(BACKUPS, "catalog-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
        shutil.copyfile(CATALOG, dst)
        for f in sorted(os.listdir(BACKUPS))[:-40]:
            os.remove(os.path.join(BACKUPS, f))
        return os.path.basename(dst)
    except Exception as e:
        return "sauvegarde impossible: %s" % e


def echelon(args, confirme=False):
    if not args:
        return 1, "commande vide", None
    regle = COMMANDES.get(args[0])
    if regle is None:
        return 1, "commande refusee : %s" % args[0], None
    if "--yes" in args and not confirme:
        return 1, "--yes refuse sans confirmation explicite", None
    if regle["publie"] and not confirme and not (regle.get("blanc")
                                                 and "--yes" not in args):
        return 1, "%s touche les joueurs : confirmation requise" % args[0], None
    with VERROU:
        sauve = _sauvegarde() if regle["mute"] else None
        code, out = _run([sys.executable, ECHELON] + [str(a) for a in args])
        JOURNAL.insert(0, {"t": time.strftime("%H:%M:%S"),
                           "cmd": " ".join(str(a) for a in args),
                           "code": code, "out": out.strip()[-4000:]})
        del JOURNAL[60:]
        return code, out, sauve


def _git(args):
    code, out = _run(["git", "-C", ROOT] + args, timeout=60)
    return out.strip() if code == 0 else ""


def _get(url, timeout=12, cache=0):
    """GET JSON, avec un petit cache memoire pour ne pas marteler Modrinth."""
    if cache and url in _CACHE and time.time() - _CACHE[url][0] < cache:
        return _CACHE[url][1]
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "echelon-panel/1.0 (studioechelon.fr)",
            "Cache-Control": "no-cache"})
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
        if cache:
            _CACHE[url] = (time.time(), d)
        return d
    except Exception:
        return None


def _vt(v):
    """1.21.1 -> (1, 21, 1). S'arrete au premier morceau non numerique."""
    out = []
    for m in re.split(r"[.\-+]", str(v).strip()):
        if not m.isdigit():
            break
        out.append(int(m))
    return tuple(out) or (0,)


def mc_compatible(spec, mc):
    """True / False / None (None = borne illisible, on n'invente pas).

    Les bornes de fabric.mod.json sont declaratives et souvent approximatives :
    ce verdict informe, il ne bloque jamais un ajout.
    """
    if not spec:
        return None
    cible, lisible = _vt(mc), False
    for bloc in re.split(r"\s*\|\|\s*", str(spec)):
        clauses = [c for c in re.split(r"[\s,]+", bloc.strip()) if c]
        bon = bool(clauses)
        for c in clauses:
            m = re.fullmatch(r"(>=|<=|>|<|~|\^|=)?v?([0-9]+(?:\.[0-9]+)*)"
                             r"(\.[x*])?(-[0-9A-Za-z.]*)?", c)
            if not m:
                bon = False
                break
            lisible = True
            op, base, joker = m.group(1) or "=", _vt(m.group(2)), bool(m.group(3))
            if joker or op in ("~", "^"):
                haut = ((base[0] + 1,) if op == "^"
                        else base[:-1] + (base[-1] + 1,))
                bon = bon and base <= cible < haut
            elif op == ">=":
                bon = bon and cible >= base
            elif op == ">":
                bon = bon and cible > base
            elif op == "<=":
                bon = bon and cible <= base
            elif op == "<":
                bon = bon and cible < base
            else:
                bon = bon and cible[:len(base)] == base
        if bon:
            return True
    return False if lisible else None


def jar_info(chemin, mc="1.21.1"):
    """Ce que le jar dit de lui-meme — meme lecture que le chargeur Fabric."""
    import hashlib
    import zipfile
    d = {"ok": False, "taille": os.path.getsize(chemin)}
    if not zipfile.is_zipfile(chemin):
        d["erreur"] = "archive illisible — ce n'est pas un .jar"
        return d
    try:
        with zipfile.ZipFile(chemin) as z:
            noms = set(z.namelist())
            if "fabric.mod.json" not in noms:
                autre = noms & {"META-INF/mods.toml", "META-INF/neoforge.mods.toml"}
                d["erreur"] = ("mod Forge/NeoForge : il ne tournera pas sur Fabric"
                               if autre else
                               "pas de fabric.mod.json — ce n'est pas un mod Fabric")
                return d
            if not any(n.endswith(".class") for n in noms):
                d["erreur"] = ("aucune classe compilee — c'est le jar de *sources*, "
                               "prends celui sans le suffixe -sources")
                return d
            brut = z.read("fabric.mod.json").decode("utf-8", "replace")
    except Exception as e:
        d["erreur"] = "jar illisible : %s" % e
        return d
    try:
        m = json.loads(brut)
    except Exception:
        try:  # certains jars trainent des commentaires // dans le manifeste
            m = json.loads(re.sub(r"^\s*//.*$", "", brut, flags=re.M))
        except Exception as e:
            d["erreur"] = "fabric.mod.json illisible : %s" % e
            return d
    if not isinstance(m, dict):
        d["erreur"] = "fabric.mod.json n'est pas un objet"
        return d
    dep = m.get("depends") if isinstance(m.get("depends"), dict) else {}
    spec = dep.get("minecraft")
    if isinstance(spec, list):
        spec = " || ".join(str(x) for x in spec)
    ver = str(m.get("version") or "")
    d.update({
        "ok": True,
        "mod_id": str(m.get("id") or ""),
        "nom": str(m.get("name") or m.get("id") or ""),
        "version": ver,
        "env": str(m.get("environment") or "*"),
        "mc_spec": spec,
        "mc_ok": mc_compatible(spec, mc),
        "loader": str(dep.get("fabricloader") or ""),
        "sha": hashlib.sha256(open(chemin, "rb").read()).hexdigest(),
    })
    if "$" in ver or "{" in ver:
        d["version"] = ""
        d["alerte"] = ("le jar annonce version=%r : Gradle n'a pas substitue la "
                       "variable, donne la version a la main" % ver)
    return d


def etat_canal(local, canal):
    """Le canal est-il utilisable, et qu'y a-t-il deja publie dessus ?"""
    d = {"canal": canal}
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,31}", canal or ""):
        d["erreur"] = "canal : minuscules, chiffres et tirets, 2 a 32 caracteres"
        return d
    if canal in canaux_reserves(local):
        d["erreur"] = ("canal reserve : %s porte deja le hub ou le mod principal "
                       "d'un projet — publier dessus l'ecraserait" % canal)
        return d
    m = _get(RELEASES + "/" + canal + "/manifest.json?t=%d" % time.time(), timeout=8)
    d["version"] = (m or {}).get("mod_version")
    d["sha"] = ((m or {}).get("mod_sha256") or "")[:12]
    d["utilise_par"] = sorted({g.get("id") for g in local.get("games", [])
                               for e in (g.get("extra") or [])
                               if isinstance(e, dict) and e.get("channel") == canal})
    return d


def canaux_reserves(local):
    """Canaux qu'on refuse d'ecraser : l'exe du hub, le mod principal des jeux."""
    r = {"client"}
    for g in local.get("games", []):
        if g.get("channel"):
            r.add(str(g["channel"]))
    return r


def ping(host, port, timeout=4):
    import socket
    import struct

    def varint(n):
        b = b""
        while True:
            x = n & 0x7F
            n >>= 7
            b += bytes([x | (0x80 if n else 0)])
            if not n:
                return b
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        h = (varint(0) + varint(765) + varint(len(host)) + host.encode()
             + struct.pack(">H", port) + varint(1))
        s.sendall(varint(len(h)) + h)
        s.sendall(varint(1) + varint(0))

        def rv():
            n = sh = 0
            while True:
                b = s.recv(1)
                if not b:
                    raise IOError("ferme")
                n |= (b[0] & 0x7F) << sh
                if not (b[0] & 0x80):
                    return n
                sh += 7
        rv(); rv(); ln = rv()
        data = b""
        while len(data) < ln:
            data += s.recv(ln - len(data))
        s.close()
        d = json.loads(data.decode("utf-8", "replace"))
        return {"en_ligne": d.get("players", {}).get("online"),
                "max": d.get("players", {}).get("max"),
                "version": d.get("version", {}).get("name")}
    except Exception as e:
        return {"erreur": str(e)[:70]}


# ── Modrinth ────────────────────────────────────────────────────────────────
def mr_facets(mc):
    return urllib.parse.quote(json.dumps(
        [["categories:fabric"], ["versions:%s" % mc], ["project_type:mod"]]))


def mr_search(q, mc, limit=12):
    d = _get("%s/search?query=%s&limit=%d&facets=%s"
             % (MODRINTH, urllib.parse.quote(q), limit, mr_facets(mc)), cache=120)
    if not d:
        return []
    return [{"slug": h["slug"], "titre": h.get("title"),
             "desc": (h.get("description") or "")[:110],
             "dl": h.get("downloads"), "icone": h.get("icon_url"),
             "client": h.get("client_side"), "serveur": h.get("server_side")}
            for h in d.get("hits", [])]


def mr_versions(slug, mc):
    """Les versions du mod, DANS L'ORDRE OU LE HUB LES PREND.

    Le hub prefere une version stable et ne retombe sur les betas que s'il n'y
    en a aucune : le panneau doit annoncer le meme fichier que celui qui
    arrivera chez le joueur, sinon il ment.
    """
    d = _get("%s/project/%s/version?game_versions=%s&loaders=%s"
             % (MODRINTH, urllib.parse.quote(slug),
                urllib.parse.quote(json.dumps([mc])),
                urllib.parse.quote(json.dumps(["fabric"]))), cache=120)
    if not d:
        return None
    stables = [v for v in d if v.get("version_type") == "release"]
    return stables or d


def mr_prefixe(fichier, slug):
    """Prefixe de detection : le hub teste f.startswith(prefixe) dans mods/."""
    base = os.path.basename(fichier or "")
    if base.lower().startswith(slug.lower()):
        m = re.match(r"^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z][A-Za-z0-9]*)*)", base)
        if m and len(m.group(1)) >= len(slug):
            return m.group(1)
    return slug


# jamais dans l'historique git : un binaire y reste pour toujours, meme
# supprime au commit suivant, et le depot enfle a chaque version.
BINAIRES = (".jar", ".exe", ".zip", ".7z", ".png.part", ".mp4", ".dll")
LOURD = 5 * 1024 * 1024


def git_etat():
    """Ce que git sait, sous une forme lisible par le panneau."""
    # surtout PAS _git ici : il fait un .strip() global, et la premiere ligne
    # de --porcelain commence par une espace (le statut de l'index). Elle
    # perdait donc son premier caractere : ".github/..." devenait "github/...".
    code, sale = _run(["git", "-C", ROOT, "status", "--porcelain"], timeout=60)
    sale = sale.rstrip() if code == 0 else ""
    fichiers = []
    for ligne in sale.splitlines():
        if len(ligne) < 4:
            continue
        marque, chemin = ligne[:2].strip() or "?", ligne[3:].strip().strip('"')
        entier = os.path.join(ROOT, chemin)
        taille = os.path.getsize(entier) if os.path.isfile(entier) else 0
        fichiers.append({
            "marque": marque, "chemin": chemin, "taille": taille,
            "lourd": taille > LOURD or chemin.lower().endswith(BINAIRES),
        })
    devant = derriere = 0
    amont = _git(["rev-parse", "--abbrev-ref", "@{upstream}"])
    if amont:
        cnt = _git(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"])
        try:
            devant, derriere = [int(x) for x in cnt.split()]
        except Exception:
            pass
    return {"branche": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "amont": amont, "devant": devant, "derriere": derriere,
            "fichiers": fichiers, "origine": _git(["remote", "get-url", "origin"]),
            "dernier": _git(["log", "--oneline", "-1"]),
            "sale": sale, "propre": sale.strip() == ""}


def etat():
    try:
        local = json.load(open(CATALOG, encoding="utf-8"))
    except Exception as e:
        return {"fatal": "catalog.json illisible : %s" % e}

    publie = _get(RELEASES + "/client/catalog.json?t=%d" % time.time())
    code_check, out_check = _run([sys.executable, ECHELON, "check"], timeout=120)
    erreurs = [l.strip() for l in out_check.splitlines() if l.startswith(" ERR")]
    alertes = [l.strip() for l in out_check.splitlines() if l.startswith(" att.")]

    # Tout le reseau en parallele : un serveur mort coute son delai complet, et
    # les enchainer rendait la page blanche une dizaine de secondes.
    canaux, serveurs = {}, {}
    taches = []

    def _canal(c):
        m = _get(RELEASES + "/" + c + "/manifest.json?t=%d" % time.time(), timeout=8)
        canaux[c] = ({"version": m.get("client_version") or m.get("mod_version"),
                      "sha": (m.get("client_sha256") or m.get("mod_sha256") or "")[:12]}
                     if m else {"version": None})

    def _serveur(gid, hote, port):
        try:
            serveurs[gid] = ping(hote, port, timeout=3)
        except Exception:
            serveurs[gid] = {"erreur": "adresse invalide"}

    vus = {"client"}
    for g in local.get("games", []):
        if g.get("channel"):
            vus.add(str(g["channel"]))
        for e in g.get("extra", []) or []:
            if isinstance(e, dict) and e.get("channel"):
                vus.add(str(e["channel"]))
    for c in sorted(vus):
        taches.append(threading.Thread(target=_canal, args=(c,), daemon=True))
    for g in local.get("games", []):
        adr = str(g.get("server") or "")
        if ":" in adr:
            h, pt = adr.rsplit(":", 1)
            try:
                taches.append(threading.Thread(target=_serveur,
                                               args=(g["id"], h, int(pt)), daemon=True))
            except Exception:
                serveurs[g["id"]] = {"erreur": "adresse invalide"}
    for t in taches:
        t.start()
    for t in taches:
        t.join(timeout=9)

    gitinfo = git_etat()
    depot = _git(["show", "HEAD:catalog.json"])
    try:
        ecart_depot = (json.loads(depot) != local) if depot else True
    except Exception:
        ecart_depot = True
    gitinfo["ecart_depot"] = ecart_depot

    # images embarquees dans l'exe : un projet qui s'appuie dessus n'a pas
    # besoin de logo_url, contrairement a un projet arrive par le catalogue.
    embarques = {}
    try:
        for f in os.listdir(os.path.join(ROOT, "client", "assets")):
            for role in ("logo", "bg"):
                if f.endswith("_%s.png" % role):
                    embarques.setdefault(f[:-(len(role) + 5)], []).append(role)
    except Exception:
        pass

    return {"catalogue": local, "publie": publie, "embarques": embarques,
            "identique_a_la_prod": publie == local,
            "check": {"code": code_check, "erreurs": erreurs, "alertes": alertes},
            "canaux": canaux, "serveurs": serveurs,
            "git": gitinfo,
            "journal": JOURNAL[:25], "racine": ROOT}


PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Studio Echelon — gestion</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0A0C0E;--pan:#11171A;--pan2:#161E22;--tr:#1E2A28;--tx:#EAF6EF;
--dim:#7A948A;--acc:#5AE68C;--red:#F2777A;--org:#F0C36A;--a:var(--acc)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);display:flex;min-height:100vh;
font:14px/1.55 "Segoe UI",system-ui,sans-serif}
nav{width:206px;flex:0 0 206px;background:#080A0C;border-right:1px solid var(--tr);
padding:18px 0;position:sticky;top:0;height:100vh;overflow:auto}
nav .marque{padding:0 18px 14px;font-size:13px;letter-spacing:.16em;font-weight:700;
border-bottom:1px solid var(--tr);margin-bottom:12px}
nav a{display:flex;gap:10px;align-items:center;padding:9px 18px;color:var(--dim);
cursor:pointer;font-size:13px;font-weight:600;letter-spacing:.05em}
nav a:hover{color:var(--tx)}
nav a.on{color:var(--tx);background:#131B1E;box-shadow:inset 3px 0 0 var(--a)}
main{flex:1;min-width:0;padding:24px 30px 60px;max-width:1080px}
h2{font-size:19px;margin:0 0 3px;letter-spacing:.02em}
.sous{color:var(--dim);font-size:12.5px;margin-bottom:20px}
.bd{padding:11px 15px;border-radius:11px;margin-bottom:18px;font-weight:600;font-size:13px}
.ok{background:rgba(90,230,140,.10);color:var(--acc);border:1px solid rgba(90,230,140,.28)}
.warn{background:rgba(240,195,106,.09);color:var(--org);border:1px solid rgba(240,195,106,.28)}
.bad{background:rgba(242,119,122,.11);color:var(--red);border:1px solid rgba(242,119,122,.32)}
.carte{background:var(--pan);border:1px solid var(--tr);border-radius:15px;
padding:18px;margin-bottom:16px}
.carte h3{margin:0 0 3px;font-size:16px;display:flex;align-items:center;gap:9px}
.pt{width:11px;height:11px;border-radius:50%;flex:0 0 auto}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:820px){.g2{grid-template-columns:1fr}body{flex-direction:column}
nav{width:100%;height:auto;position:static;display:flex;flex-wrap:wrap}}
label{display:block;font-size:10.5px;color:var(--dim);margin:12px 0 5px;
text-transform:uppercase;letter-spacing:.09em}
input[type=text],textarea,select{width:100%;background:#0B1013;color:var(--tx);
border:1px solid var(--tr);border-radius:9px;padding:9px 11px;font:inherit}
input:focus,textarea:focus{outline:none;border-color:var(--a)}
textarea{min-height:74px;resize:vertical}
input[type=color]{width:44px;height:34px;padding:2px;border:1px solid var(--tr);
border-radius:9px;background:#0B1013}
.l{display:flex;gap:8px;align-items:center}
button{background:var(--pan2);color:var(--tx);border:1px solid var(--tr);
border-radius:9px;padding:8px 14px;font:inherit;cursor:pointer;white-space:nowrap}
button:hover{background:#1F2A2E}
button.go{background:var(--a);color:#06140C;border-color:transparent;font-weight:700}
button.min{padding:5px 9px;font-size:12px}
button.dg{background:#3A1D20;color:#F6C9C9;border-color:#5A2C30}
button:disabled{opacity:.38;cursor:not-allowed}
.sw{display:inline-flex;align-items:center;gap:8px;cursor:pointer;margin-right:16px;
font-size:13px}
.sw input{accent-color:var(--a);width:16px;height:16px}
pre{background:#070A0B;border:1px solid var(--tr);border-radius:10px;padding:12px;
overflow:auto;max-height:340px;font-size:12px;white-space:pre-wrap;margin:0}
.tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;
border:1px solid var(--tr);color:var(--dim);margin:0 5px 5px 0}
.tag.on{color:var(--acc);border-color:rgba(90,230,140,.4)}
.tag.off{color:var(--red);border-color:rgba(242,119,122,.4)}
.tag.wa{color:var(--org);border-color:rgba(240,195,106,.4)}
.mod{display:flex;gap:11px;align-items:center;padding:9px 11px;border:1px solid var(--tr);
border-radius:10px;margin-bottom:7px;background:#0D1315}
.mod img{width:32px;height:32px;border-radius:7px;flex:0 0 auto;background:#1A2326}
.mod .nom{font-weight:600}
.mod .meta{color:var(--dim);font-size:11.5px}
.mod .sp{flex:1;min-width:0}
.hint{font-size:11.5px;color:var(--dim);margin-top:6px}
.err{color:var(--red);font-size:12px;margin-top:6px}
.vide{color:var(--dim);font-size:13px;padding:10px 0}
.zone{border:1.5px dashed var(--tr);border-radius:12px;padding:26px 16px;
text-align:center;color:var(--dim);font-size:13px;cursor:pointer;background:#0B1013}
.zone:hover{border-color:var(--a)}
.zone.sur{border-color:var(--a);color:var(--tx);background:#0E1618}
.lien{color:var(--a);text-decoration:underline}
.art{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:5px}
.fente{border:1.5px dashed var(--tr);border-radius:11px;padding:8px;cursor:pointer;
background:#0B1013;text-align:center}
.fente:hover,.fente.sur{border-color:var(--a)}
.fente .apercu{height:92px;border-radius:8px;background:#141C1F;display:flex;
align-items:center;justify-content:center;overflow:hidden;margin-bottom:6px}
.fente .apercu img{max-width:100%;max-height:92px;object-fit:contain}
.fente .r{font-size:12px;font-weight:600}
.fente .d{font-size:10.5px;color:var(--dim)}
.pret{background:#0D1315;border:1px solid var(--tr);border-radius:12px;
padding:13px 15px;margin-top:14px}
.pret .t{font-size:12px;font-weight:700;letter-spacing:.05em;margin-bottom:9px}
.pas{display:flex;gap:9px;align-items:baseline;font-size:12.5px;padding:3px 0}
.pas .m{width:15px;flex:0 0 auto;font-weight:700}
.pas .q{color:var(--dim);font-size:11.5px}
.pas.non .m{color:var(--red)}
.pas.oui .m{color:var(--acc)}
.pas.mou .m{color:var(--org)}
</style></head><body>
<nav>
  <div class="marque">STUDIO ECHELON</div>
  <a data-s="projets" class="on">◆ &nbsp;Projets</a>
  <a data-s="modpack">▦ &nbsp;Modpack</a>
  <a data-s="reglages">✦ &nbsp;Réglages</a>
  <a data-s="publier">⬆ &nbsp;Publier</a>
  <a data-s="depot">⑂ &nbsp;Dépôt</a>
  <a data-s="journal">≡ &nbsp;Journal</a>
</nav>
<input type="file" id="fart" accept="image/png,image/jpeg" hidden>
<main>
  <div id="bd" class="bd warn">chargement…</div>
  <div id="vue"></div>
</main>
<script>
let E=null, SEC='projets', SEL=null, RES={}, JAR=null, TC=null, ARTC=null;
const ART=[{role:'logo',champ:'logo_url',nom:'Logo',taille:'PNG transparent · 620×200'},
           {role:'bg',  champ:'bg_url',  nom:'Key-art',  taille:'1920×1140'},
           {role:'card',champ:'card_url',nom:'Carte 3:4',taille:'600×800'}];
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const RESERVE=/^(true|oui|yes|false|non|no|null|none|-?\d+)$/i;
const api=(r,b)=>fetch(r,b?{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(b)}:{}).then(x=>x.json());
const jeux=()=>((E&&E.catalogue.games)||[]);
const jeu=id=>jeux().find(g=>g.id===id);
const mcDe=g=>g.mc_version||(E.catalogue.config||{}).mc_version||'1.21.1';

document.querySelectorAll('nav a').forEach(a=>a.onclick=()=>{
  SEC=a.dataset.s;
  document.querySelectorAll('nav a').forEach(x=>x.classList.toggle('on',x===a));
  rendre();
});

async function charger(){
  E=await api('/api/etat');
  if(E.fatal){bd('bad',E.fatal);return;}
  if(!SEL||!jeu(SEL)) SEL=(jeux()[0]||{}).id||null;
  const g=jeu(SEL); if(g) document.documentElement.style.setProperty('--a',g.accent||'#5AE68C');
  bandeau(); rendre();
}
function bd(c,t){const b=$('#bd');b.className='bd '+c;b.textContent=t;}
function bandeau(){
  const c=E.check;
  if(c.code!==0) bd('bad','PUBLICATION BLOQUÉE — '+c.erreurs.join(' | '));
  else if(!E.git.propre) bd('warn','Dépôt modifié — à commiter avant de publier');
  else if(c.alertes.length) bd('warn',c.alertes.length+' avertissement(s) — '+c.alertes.join(' | '));
  else bd('ok','Catalogue valide');
}
function rendre(){
  const v=$('#vue');
  if(SEC==='projets'){ v.innerHTML=vProjets(); brancherArt(); }
  else if(SEC==='modpack') {v.innerHTML=vModpack(); brancherDepot(); montrerJar(); majMods();}
  else if(SEC==='reglages') v.innerHTML=vReglages();
  else if(SEC==='publier') v.innerHTML=vPublier();
  else if(SEC==='depot') v.innerHTML=vDepot();
  else v.innerHTML=vJournal();
}
function onglets(){
  return `<div style="margin-bottom:14px">${jeux().map(g=>
    `<button class="${g.id===SEL?'go':''}" onclick="choisir('${g.id}')">${esc(g.name)}</button>`
  ).join(' ')}</div>`;
}
function choisir(id){SEL=id;const g=jeu(id);JAR=null;
  document.documentElement.style.setProperty('--a',g.accent||'#5AE68C');rendre();}

/* ---------- projets ---------- */
function vProjets(){
  return `<h2>Projets</h2><div class="sous">Ce que voient les joueurs dans le hub.</div>`
   + jeux().map(g=>{
    const s=E.serveurs[g.id]||{}, ch=E.canaux[g.channel]||{};
    const srv=!g.server?'<span class="tag">pas de serveur</span>'
      :s.erreur?'<span class="tag off">serveur injoignable</span>'
      :`<span class="tag on">${s.en_ligne}/${s.max} joueurs</span>`;
    return `<div class="carte">
      <h3><span class="pt" style="background:${esc(g.accent)}"></span>${esc(g.name)}</h3>
      <div class="sous">${esc(g.id)} · canal ${esc(g.channel)} · mod publié ${esc(ch.version||'aucun')}</div>
      <div>${srv}
        <span class="tag ${g.featured?'on':''}">${g.featured?'en une':'pas en une'}</span>
        <span class="tag ${g.hidden?'off':'on'}">${g.hidden?'masqué':'visible'}</span></div>
      <div class="g2">
        <div><label>Nom affiché</label><div class="l">
          <input type="text" id="n-${g.id}" value="${esc(g.name)}">
          <button class="min" onclick="champ('${g.id}','name','n-${g.id}')">OK</button></div></div>
        <div><label>Serveur (hôte:port)</label><div class="l">
          <input type="text" id="s-${g.id}" value="${esc(g.server||'')}">
          <button class="min" onclick="champ('${g.id}','server','s-${g.id}')">OK</button></div></div>
      </div>
      <label>Accroche (fr)</label><div class="l">
        <input type="text" id="t-${g.id}" value="${esc((g.tagline||{}).fr||'')}">
        <button class="min" onclick="champ('${g.id}','tagline.fr','t-${g.id}')">OK</button></div>
      <label>Couleur d'accent</label><div class="l">
        <input type="color" id="c-${g.id}" value="${esc(g.accent)}"
          oninput="document.getElementById('ch-${g.id}').value=this.value.toUpperCase()">
        <input type="text" id="ch-${g.id}" value="${esc(g.accent)}" style="max-width:130px">
        <button class="min" onclick="couleur('${g.id}')">OK</button></div>
      <label>Identité visuelle</label>
      <div class="art">${ART.map(r=>{const u=g[r.champ]||'';
        return `<div class="fente" data-jeu="${g.id}" data-role="${r.role}"
            onclick="choisirArt('${g.id}','${r.role}')">
          <div class="apercu">${u?`<img src="${esc(u)}" alt="">`
            :'<span class="d">à déposer</span>'}</div>
          <div class="r">${esc(r.nom)}</div><div class="d">${esc(r.taille)}</div>
          ${u?`<button class="min dg" style="margin-top:6px"
            onclick="event.stopPropagation();retirerArt('${g.id}','${r.role}')">Retirer</button>`
            :''}</div>`;}).join('')}</div>
      <div class="hint">Dépose une image, ou clique. Le hub les télécharge depuis le
        catalogue et les garde en cache — l'URL porte l'empreinte du fichier, donc
        remplacer une image la remplace vraiment chez les joueurs.</div>
      <pre id="art-${g.id}" style="display:none;margin-top:10px"></pre>
      <label>Nouveautés fr — une par ligne, 4 maximum</label>
      <textarea id="nw-${g.id}">${esc(((g.news||{}).fr||[]).join('\n'))}</textarea>
      <div class="l" style="margin-top:9px"><button onclick="news('${g.id}')">Enregistrer les nouveautés</button></div>
      <div class="l" style="margin-top:14px">
        <label class="sw"><input type="checkbox" ${g.featured?'checked':''}
          onchange="bool('${g.id}','featured',this.checked)"> en une</label>
        <label class="sw"><input type="checkbox" ${g.hidden?'':'checked'}
          onchange="bool('${g.id}','hidden',!this.checked)"> visible par les joueurs</label>
      </div>
      ${blocPret(g)}
      <div id="e-${g.id}" class="err"></div></div>`;
   }).join('')
   + `<div class="carte"><h3>Ajouter un projet</h3>
      <div class="sous">Créé masqué : il n'apparaîtra pas tant que tu ne l'auras pas ouvert.</div>
      <div class="g2">
        <div><label>Identifiant (définitif)</label><input type="text" id="np-id" placeholder="dac"></div>
        <div><label>Nom affiché</label><input type="text" id="np-nom" placeholder="Divide &amp; Conquer"></div>
        <div><label>Canal de mod</label><input type="text" id="np-canal" placeholder="dac"></div>
        <div><label>Couleur</label><input type="color" id="np-col" value="#FF3D8B"></div>
        <div><label>Serveur (optionnel)</label><input type="text" id="np-srv" placeholder="1.2.3.4:25565"></div>
        <div><label>Accroche fr</label><input type="text" id="np-tag"></div>
      </div>
      <div class="l" style="margin-top:14px"><button class="go" onclick="creer()">Créer le projet</button></div>
      <div id="np-err" class="err"></div></div>`;
}

/* ---------- modpack ---------- */
function vModpack(){
  const g=jeu(SEL); if(!g) return '<h2>Modpack</h2><div class="vide">Aucun projet.</div>';
  const deps=g.deps||{}, purge=g.purge||[];
  const extra=(g.extra||[]).filter(e=>e&&e.channel);
  return `<h2>Modpack</h2>
   <div class="sous">Les mods que le hub installe automatiquement chez le joueur, en plus du tien.
     Minecraft ${esc(mcDe(g))} · Fabric.</div>${onglets()}
   <div class="carte"><h3>Ajouter un mod</h3>
     <div class="l"><input type="text" id="q" placeholder="sodium, carpet, journeymap…"
       onkeydown="if(event.key==='Enter')chercher()">
       <button class="go" onclick="chercher()">Chercher</button></div>
     <div class="hint">Seuls les mods ayant une version <b>Fabric ${esc(mcDe(g))}</b> sont proposés —
       un mod sans build compatible fait planter le lancement chez le joueur.</div>
     <div id="res" style="margin-top:12px"></div></div>
   <div class="carte"><h3>Tes propres mods (.jar)</h3>
     <div class="sous">Un mod que tu as compilé toi-même, hors Modrinth. Il part sur son propre
       canal de mise à jour : ensuite tu republies une version et les joueurs l'ont au
       lancement suivant, sans rien réinstaller.</div>
     <div id="zone" class="zone">Dépose un <b>.jar</b> ici — ou <span class="lien">choisis un fichier</span>
       <input type="file" id="fj" accept=".jar" hidden></div>
     <div id="jinfo"></div></div>
   <div class="carte"><h3>Mods maison de ${esc(g.name)} (${extra.length})</h3>
     <div class="sous">Le hub les télécharge depuis leur canal, vérifie le sha256, et ne
       retélécharge que si la version publiée a changé.</div>
     ${extra.map(e=>{const c=(E.canaux||{})[e.channel]||{};
       return `<div class="mod"><div class="sp"><div class="nom">${esc(e.channel)}</div>
         <div class="meta">installé sous <code>${esc(e.file)}</code> · ${c.version
           ? 'canal publié en <b>'+esc(c.version)+'</b>'
           : '<span style="color:var(--red)">canal jamais publié — le hub ne téléchargera rien</span>'}</div></div>
         <button class="min" onclick="retirerExtra('${esc(e.channel)}',0)">Retirer</button>
         <button class="min dg" onclick="retirerExtra('${esc(e.channel)}',1)">Retirer + effacer chez les joueurs</button></div>`;
       }).join('') || '<div class="vide">Aucun mod maison. Dépose un jar au-dessus.</div>'}</div>
   <div class="carte"><h3>Mods installés automatiquement (${Object.keys(deps).length})</h3>
     <div id="deps">${Object.entries(deps).map(([p,s])=>`
       <div class="mod"><img id="ic-${esc(p)}" alt="">
         <div class="sp"><div class="nom">${esc(s)}</div>
           <div class="meta">préfixe <code>${esc(p)}</code> · <span id="v-${esc(p)}">vérification…</span></div></div>
         <button class="min dg" onclick="retirerDep('${esc(p)}')">Retirer</button></div>`).join('')
       || '<div class="vide">Aucun mod supplémentaire.</div>'}</div></div>
   <div class="carte"><h3>Mods à supprimer chez le joueur (${purge.length})</h3>
     <div class="sous">Le hub efface tout fichier du dossier mods commençant par ces préfixes.</div>
     ${purge.map(p=>`<div class="mod"><div class="sp"><code>${esc(p)}</code></div>
        <button class="min dg" onclick="retirerPurge('${esc(p)}')">Retirer</button></div>`).join('')
       || '<div class="vide">Aucun.</div>'}
     <div class="l" style="margin-top:9px"><input type="text" id="np" placeholder="firstperson">
       <button onclick="ajoutPurge()">Ajouter</button></div></div>`;
}
async function chercher(){
  const g=jeu(SEL), q=$('#q').value.trim(); if(!q) return;
  $('#res').innerHTML='<div class="vide">recherche…</div>';
  const r=await api('/api/modrinth?q='+encodeURIComponent(q)+'&mc='+encodeURIComponent(mcDe(g)));
  RES=r; $('#res').innerHTML=(r.resultats||[]).map(m=>`
    <div class="mod"><img src="${esc(m.icone||'')}" alt="">
      <div class="sp"><div class="nom">${esc(m.titre)} <span class="tag">${esc(m.slug)}</span></div>
        <div class="meta">${esc(m.desc)}</div>
        <div class="meta">${(m.dl||0).toLocaleString('fr')} téléchargements · serveur ${esc(m.serveur)}</div></div>
      <button class="min go" onclick="ajouterDep('${esc(m.slug)}')">Ajouter</button></div>`).join('')
    || '<div class="vide">Aucun mod compatible trouvé.</div>';
}
async function majMods(){
  const g=jeu(SEL); if(!g) return;
  for(const [p,s] of Object.entries(g.deps||{})){
    const r=await api('/api/verifier?slug='+encodeURIComponent(s)+'&mc='+encodeURIComponent(mcDe(g)));
    const el=document.getElementById('v-'+p), ic=document.getElementById('ic-'+p);
    if(!el) continue;
    if(r.ok){ el.innerHTML='<span style="color:var(--acc)">compatible</span> · '+esc(r.fichier);
      if(r.prefixe && r.prefixe!==p) el.innerHTML+=' <span class="tag wa">préfixe attendu '+esc(r.prefixe)+'</span>';
    } else el.innerHTML='<span style="color:var(--red)">AUCUNE version Fabric '+esc(mcDe(g))
      +' — le lancement plantera</span>';
    if(ic&&r.icone) ic.src=r.icone;
  }
}
async function ajouterDep(slug){
  const g=jeu(SEL);
  const r=await api('/api/verifier?slug='+encodeURIComponent(slug)+'&mc='+encodeURIComponent(mcDe(g)));
  if(!r.ok){ alert('Ce mod n\'a aucune version Fabric '+mcDe(g)+'. Ajout refusé.'); return; }
  await lancer(['set',g.id,'deps.'+r.prefixe,slug]);
}
async function retirerDep(p){ await lancer(['set',SEL,'deps.'+p,'null']); }

/* ---------- prêt à sortir ---------- */
const emb=(g,role)=>(((E.embarques||{})[g.id])||[]).includes(role);
function pret(g){
  const c=(E.canaux||{})[g.channel]||{}, t=g.tagline||{};
  return [
   {ok:!!g.logo_url||emb(g,'logo'), t:'Logo'+(emb(g,'logo')&&!g.logo_url?' · image embarquée':''),
    q:'dépose-le dans la fente Logo ci-dessus'},
   {ok:!!g.bg_url||emb(g,'bg'), t:'Key-art'+(emb(g,'bg')&&!g.bg_url?' · image embarquée':''),
    q:'sans lui le hub afficherait un fond vide'},
   {ok:!!c.version, t:'Mod publié sur le canal '+esc(g.channel),
    q:'dépose le jar dans Modpack › Tes propres mods — sinon le joueur installe '
     +'dix minutes puis échoue'},
   {ok:Object.keys(g.deps||{}).length>0, t:'Modpack renseigné',
    q:'au minimum fabric-api, dans la section Modpack'},
   {ok:!!(t.fr&&t.en), t:'Accroche fr et en', q:'une phrase dans chaque langue'},
   {ok:!!g.card_url, mou:true, t:'Carte 3:4',
    q:'facultatif — à défaut le key-art est recadré'},
  ];
}
function blocPret(g){
  const l=pret(g), manque=l.filter(x=>!x.ok&&!x.mou);
  const bloque = manque.length || E.check.code!==0;
  const dejaLa = !g.hidden && E.identique_a_la_prod;
  return `<div class="pret"><div class="t">PRÊT À SORTIR ?</div>
    ${l.map(x=>`<div class="pas ${x.ok?'oui':(x.mou?'mou':'non')}">
      <span class="m">${x.ok?'✓':(x.mou?'~':'✗')}</span>
      <span><b>${x.t}</b>${x.ok?'':' — <span class="q">'+x.q+'</span>'}</span></div>`).join('')}
    <div class="l" style="margin-top:12px">
      <button class="go" ${bloque||dejaLa?'disabled':''}
        onclick="mettreEnLigne('${g.id}')">${g.hidden?'Mettre en ligne':'Publier les modifications'}</button>
      ${dejaLa?'<span class="tag on">déjà en ligne, rien à envoyer</span>':''}</div>
    ${E.check.code!==0&&!manque.length
      ? '<div class="err">un AUTRE projet bloque la validation : '+esc(E.check.erreurs.join(' | '))+'</div>'
      : ''}</div>`;
}
async function mettreEnLigne(id){
  const g=jeu(id);
  if(!confirm((g.hidden?'Mettre '+g.name+' en ligne ?':'Publier les modifications de '+g.name+' ?')
    +'\n\nTous les joueurs le verront au prochain démarrage du launcher,'
    +'\net sous 2 minutes pour ceux qui l\'ont déjà ouvert.')) return;
  if(g.hidden){
    const r=await lancer(['set',id,'hidden','false']);
    if(r.code!==0){ bd('bad','Échec : '+(r.out||'').trim().split('\n')[0]); return; }
  }
  const r=await lancer(['publish'],true);
  await charger();
  bd(r.code===0?'ok':'bad', r.code===0
    ? g.name+' est en ligne — les joueurs le recevront au prochain démarrage'
    : 'Publication refusée : '+(r.out||'').trim().split('\n').slice(-1)[0]);
}

/* ---------- identité visuelle ---------- */
function brancherArt(){
  document.querySelectorAll('.fente').forEach(z=>{
    ['dragenter','dragover'].forEach(n=>z.addEventListener(n,e=>{
      e.preventDefault(); z.classList.add('sur'); }));
    ['dragleave','drop'].forEach(n=>z.addEventListener(n,e=>{
      e.preventDefault(); z.classList.remove('sur'); }));
    z.addEventListener('drop',e=>{ const f=e.dataTransfer.files[0]; if(!f) return;
      ARTC={jeu:z.dataset.jeu,role:z.dataset.role}; envoyerArt(f); });
  });
}
function choisirArt(jeu,role){ ARTC={jeu,role}; const f=$('#fart'); f.value=''; f.click(); }
async function envoyerArt(f){
  if(!ARTC) return;
  const jeu=ARTC.jeu, role=ARTC.role, o=document.getElementById('art-'+jeu);
  if(!o) return;
  o.style.display='block'; o.textContent='lecture de '+f.name+'…';
  let r;
  try{
    r=await fetch('/api/art?jeu='+encodeURIComponent(jeu)+'&role='+role
      +'&nom='+encodeURIComponent(f.name),{method:'POST',body:f}).then(x=>x.json());
  }catch(e){ o.textContent='envoi impossible : '+e; return; }
  if(!r.ok){ o.textContent=r.erreur||'image refusée'; return; }
  const v=await api('/api/art/publier',{jeu,role,id:r.id,confirme:false});
  o.textContent=(v.out||'').trim()||('code '+v.code);
  if(v.code!==0) return;
  const d=document.createElement('div');
  d.className='l'; d.style.marginTop='9px';
  d.innerHTML='<button class="go">Mettre cette image en place</button><button>Annuler</button>';
  o.after(d);
  d.children[0].onclick=async()=>{
    d.remove(); o.textContent='envoi de l\'image…';
    const w=await api('/api/art/publier',{jeu,role,id:r.id,confirme:true});
    if(w.code!==0){ o.textContent=(w.out||'').trim(); return; }
    await charger();
    bd('ok','Image en place — il reste à publier le catalogue pour que les joueurs la voient');
  };
  d.children[1].onclick=()=>{ d.remove(); o.style.display='none'; };
}
async function retirerArt(jeu,role){
  if(!confirm('Retirer cette image de '+jeu+' ?')) return;
  const r=await api('/api/art/retirer',{jeu,role});
  await charger();
  if(r.code!==0) bd('bad','Échec : '+(r.out||'').trim().split('\n')[0]);
}

/* ---------- mods maison (.jar) ---------- */
function brancherDepot(){
  const z=$('#zone'), f=$('#fj'); if(!z||!f) return;
  z.onclick=()=>f.click();
  f.onchange=()=>{ if(f.files[0]) envoyerJar(f.files[0]); f.value=''; };
  ['dragenter','dragover'].forEach(n=>z.addEventListener(n,e=>{
    e.preventDefault(); z.classList.add('sur'); }));
  ['dragleave','drop'].forEach(n=>z.addEventListener(n,e=>{
    e.preventDefault(); z.classList.remove('sur'); }));
  z.addEventListener('drop',e=>{ const x=e.dataTransfer.files[0]; if(x) envoyerJar(x); });
}
async function envoyerJar(f){
  const d=$('#jinfo');
  if(!/\.jar$/i.test(f.name)){ JAR=null; d.innerHTML='<div class="err">Il faut un fichier .jar.</div>'; return; }
  d.innerHTML='<div class="vide">lecture de '+esc(f.name)+' — '+(f.size/1048576).toFixed(1)+' Mo…</div>';
  try{
    JAR=await fetch('/api/jar?nom='+encodeURIComponent(f.name)
      +'&mc='+encodeURIComponent(mcDe(jeu(SEL))),{method:'POST',body:f}).then(x=>x.json());
  }catch(e){ JAR=null; d.innerHTML='<div class="err">envoi impossible : '+esc(e)+'</div>'; return; }
  montrerJar();
}
function montrerJar(){
  const d=$('#jinfo'); if(!d) return;
  if(!JAR){ d.innerHTML=''; return; }
  if(!JAR.ok){ d.innerHTML='<div class="err">'+esc(JAR.erreur||'jar refusé')+'</div>'; return; }
  const mcv=mcDe(jeu(SEL));
  const mc=JAR.mc_ok===true ? '<span class="tag on">Minecraft '+esc(JAR.mc_spec)+'</span>'
    : JAR.mc_ok===false ? '<span class="tag off">le jar annonce '+esc(JAR.mc_spec)+', pas '+esc(mcv)+'</span>'
    : '<span class="tag wa">aucune version Minecraft déclarée</span>';
  const env=JAR.env==='client' ? '<span class="tag">client seul</span>'
    : JAR.env==='server' ? '<span class="tag">serveur seul</span>'
    : '<span class="tag wa">client + serveur — le serveur devra tourner le même jar</span>';
  d.innerHTML=`<div class="mod" style="margin-top:12px"><div class="sp">
     <div class="nom">${esc(JAR.nom)} <span class="tag">${esc(JAR.mod_id)}</span></div>
     <div class="meta">${esc(JAR.fichier)} · ${(JAR.taille/1048576).toFixed(1)} Mo · sha ${esc((JAR.sha||'').slice(0,12))}…</div>
     <div class="meta" style="margin-top:5px">${mc} ${env}</div></div></div>
   ${JAR.alerte?'<div class="err">'+esc(JAR.alerte)+'</div>':''}
   <div class="g2" style="margin-top:8px">
     <div><label>Canal de mise à jour</label>
       <input type="text" id="j-canal" value="${esc(JAR.canal||'')}"
         oninput="clearTimeout(TC);TC=setTimeout(verifCanal,400)">
       <div class="hint" id="j-canal-h">…</div></div>
     <div><label>Version à publier</label>
       <input type="text" id="j-ver" value="${esc(JAR.version||'')}" placeholder="1.0.0">
       <div class="hint">Les launchers comparent ce numéro : il doit monter à chaque envoi,
         sinon personne ne voit la mise à jour.</div></div></div>
   <div class="l" style="margin-top:12px">
     <button onclick="publierJar(0)">Vérifier — n'envoie rien</button>
     <button class="go" id="j-go" onclick="publierJar(1)">Publier aux joueurs</button>
     <button onclick="JAR=null;montrerJar()">Annuler</button></div>
   <pre id="j-out" style="margin-top:11px">—</pre>`;
  verifCanal();
}
async function verifCanal(){
  const i=$('#j-canal'), h=$('#j-canal-h'), b=$('#j-go'); if(!i) return;
  h.textContent='vérification…'; b.disabled=true;
  const r=await api('/api/canal?nom='+encodeURIComponent(i.value.trim().toLowerCase()));
  if(!$('#j-canal')) return;
  if(r.erreur){ h.innerHTML='<span style="color:var(--red)">'+esc(r.erreur)+'</span>'; return; }
  b.disabled=false;
  h.innerHTML=r.version ? 'déjà publié en <b>'+esc(r.version)+'</b> — donne un numéro supérieur'
                        : 'nouveau canal : il sera créé à la publication.';
  if((r.utilise_par||[]).length) h.innerHTML+=' · déjà dans '+esc(r.utilise_par.join(', '));
}
async function publierJar(go){
  const canal=$('#j-canal').value.trim().toLowerCase(), ver=$('#j-ver').value.trim();
  if(go && !confirm('Publier '+canal+' '+ver+' ?\n\nTous les joueurs de '+SEL
    +' recevront ce jar au prochain lancement.\nSi le mod tourne aussi côté serveur,'
    +' le serveur doit être redémarré avec le MÊME jar.')) return;
  $('#j-out').textContent='…';
  const r=await api('/api/jar/publier',{id:JAR.id,canal,version:ver,jeu:SEL,confirme:!!go});
  const o=$('#j-out'); if(o) o.textContent=(r.out||'').trim()||('code '+r.code);
  if(go && r.code===0){ JAR=null; await charger(); }
}
async function retirerExtra(canal,purger){
  if(!confirm(purger
    ? 'Retirer '+canal+' ET l\'effacer du dossier mods des joueurs au prochain lancement ?'
    : 'Retirer '+canal+' du modpack ?\n\nLe jar restera chez ceux qui l\'ont déjà.')) return;
  const r=await api('/api/jar/retirer',{jeu:SEL,canal,purger:!!purger});
  if(r.code!==0) bd('bad','Échec : '+(r.out||'').trim().split('\n')[0]);
  await charger();
}
async function ajoutPurge(){
  const g=jeu(SEL), v=$('#np').value.trim(); if(!v) return;
  const sien=[g.mod_file||''].concat((g.extra||[]).map(e=>e&&e.file||''))
    .filter(f=>f&&f.startsWith(v));
  if(sien.length){ alert('Refusé : ce préfixe effacerait '+sien.join(', ')
    +', que le hub vient d\'installer. Le mod disparaîtrait à chaque lancement.'); return; }
  const l=(g.purge||[]).concat([v]);
  await lancer(['set',g.id,'purge',JSON.stringify(l)]);
}
async function retirerPurge(p){
  const g=jeu(SEL), l=(g.purge||[]).filter(x=>x!==p);
  await lancer(['set',g.id,'purge',JSON.stringify(l)]);
}

/* ---------- reglages ---------- */
function vReglages(){
  const c=E.catalogue.config||{};
  const f=[['mc_version','Version de Minecraft'],['java_runtime','Runtime Java'],
           ['discord_invite','Invitation Discord (compteur de membres)'],['site_url','Site du studio']];
  return `<h2>Réglages</h2><div class="sous">Appliqués à tous les projets, sans reconstruire l'exe.</div>
   <div class="carte"><div class="g2">${f.map(([k,l])=>`<div><label>${l}</label><div class="l">
     <input type="text" id="cf-${k}" value="${esc(c[k]||'')}">
     <button class="min" onclick="cfg('${k}')">OK</button></div></div>`).join('')}</div>
     <label>Annonce affichée à tous les joueurs (vide = aucune)</label>
     <div class="l"><input type="text" id="an" value="${esc((c.announce||{}).fr||'')}"
       placeholder="Maintenance à 21h"><button onclick="annonce()">Appliquer</button></div>
     <div class="hint">Bandeau dans le rail du launcher, visible sur toutes les pages.</div></div>`;
}
/* ---------- publier ---------- */
function vPublier(){
  const r=[];
  if(E.check.code!==0) r.push('le catalogue ne passe pas la validation');
  if(E.git.ecart_depot) r.push('le catalogue du DÉPÔT diffère de ta copie : publier republierait la version du dépôt');
  const sansMod=jeux().filter(g=>!g.hidden && g.channel && !((E.canaux||{})[g.channel]||{}).version);
  if(sansMod.length) r.push('projet visible sans mod publié : '
    +sansMod.map(g=>g.name+' (canal '+g.channel+')').join(', ')
    +" — le joueur installerait tout puis échouerait à la fin");
  return `<h2>Publier</h2><div class="sous">Le catalogue part chez tous les joueurs, au prochain démarrage du launcher.</div>
   <div class="carte">
     <div>${E.identique_a_la_prod?'<span class="tag on">ta copie est identique à la prod</span>'
       :'<span class="tag wa">des modifications ne sont pas encore en ligne</span>'}
       <span class="tag ${E.git.propre?'on':'off'}">${E.git.propre?'dépôt propre':'dépôt modifié'}</span></div>
     <div class="l" style="margin-top:14px;flex-wrap:wrap">
       <button onclick="lancer(['check'])">Valider</button>
       <button onclick="lancer(['preview'])">Aperçu local</button>
       <button class="go" ${r.length?'disabled':''} onclick="publier()">Publier le catalogue</button></div>
     ${r.length?'<div class="err">'+esc(r.join(' ; '))+'</div>':''}
     <div class="hint">Dernier commit : ${esc(E.git.dernier||'—')}</div></div>
   <div class="carte"><h3>Versions publiées</h3>
     ${Object.entries(E.canaux).map(([c,v])=>`<span class="tag ${v.version?'on':'off'}">${esc(c)} : ${esc(v.version||'aucune')}</span>`).join('')}</div>`;
}
function vDepot(){
  const g=E.git||{}, f=g.fichiers||[];
  const lourds=f.filter(x=>x.lourd);
  const rien=!f.length && !g.devant;
  return `<h2>Dépôt</h2>
   <div class="sous">${esc(g.origine||'aucune origine configurée')} · branche
     <b>${esc(g.branche||'?')}</b>${g.amont?' → '+esc(g.amont):' · aucun suivi distant'}</div>
   <div class="carte">
     <div><span class="tag ${g.propre?'on':'wa'}">${g.propre?'rien à commiter'
        :f.length+' fichier(s) modifié(s)'}</span>
       <span class="tag ${g.devant?'wa':'on'}">${g.devant?g.devant+' commit(s) non poussé(s)'
        :'à jour avec GitHub'}</span>
       ${g.derriere?'<span class="tag off">'+g.derriere+' commit(s) de retard — fais un git pull avant</span>':''}
       <span class="tag ${E.identique_a_la_prod?'on':'wa'}">${E.identique_a_la_prod
        ?'catalogue en ligne = ta copie':'catalogue en ligne différent de ta copie'}</span></div>
     <div class="hint" style="margin-top:8px">Dernier commit : ${esc(g.dernier||'—')}</div></div>
   <div class="carte"><h3>Ce qui partirait (${f.length})</h3>
     ${f.map(x=>`<div class="mod"><div class="sp">
       <div class="nom"><code>${esc(x.chemin)}</code> <span class="tag">${esc(x.marque)}</span></div>
       <div class="meta">${x.taille?Math.round(x.taille/1024)+' Ko':'—'}${x.lourd
         ?' · <span style="color:var(--red)">binaire : refusé</span>':''}</div></div></div>`).join('')
       || '<div class="vide">Rien de modifié.</div>'}
     ${lourds.length?'<div class="err">Un binaire commité reste dans l\'historique pour '
       +'toujours, même supprimé ensuite. Les jars passent par la section Modpack, pas par git.</div>':''}</div>
   <div class="carte"><h3>Envoyer sur GitHub</h3>
     <div class="sous">Pousser <code>catalog.json</code> déclenche l\'action GitHub
       qui republie le catalogue à tous les joueurs.</div>
     <label>Message de commit</label>
     <input type="text" id="gmsg" placeholder="ce que ce commit change, en une ligne">
     <div class="l" style="margin-top:12px">
       <button class="go" ${rien||lourds.length?'disabled':''}
         onclick="envoyerGit()">Commiter et pousser</button>
       ${rien?'<span class="tag on">rien à envoyer</span>':''}</div>
     <pre id="gout" style="margin-top:11px;display:none"></pre></div>`;
}
async function envoyerGit(){
  const m=$('#gmsg').value.trim();
  if(m.length<5){ bd('bad','Écris un message de commit un peu plus parlant.'); return; }
  if(!confirm('Envoyer sur GitHub ?\n\n'+m+'\n\nSi catalog.json en fait partie,'
    +' le catalogue sera republié à tous les joueurs.')) return;
  const o=$('#gout'); o.style.display='block'; o.textContent='envoi…';
  const r=await api('/api/git',{message:m,confirme:true});
  const t=(r.out||'').trim();
  await charger();
  const o2=$('#gout'); if(o2){ o2.style.display='block'; o2.textContent=t; }
  bd(r.code===0?'ok':'bad', r.code===0?'Envoyé sur GitHub':'Échec de l\'envoi — voir la sortie');
}
function vJournal(){
  return `<h2>Journal</h2><div class="sous">Les commandes exécutées par ce panneau.</div>
   <div class="carte"><pre>${esc((E.journal||[]).map(j=>
     `[${j.t}] ${j.cmd}\n${j.code===0?'  ok':'  ÉCHEC '+j.code}  ${j.out}`).join('\n\n')||'—')}</pre></div>`;
}
/* ---------- actions ---------- */
async function lancer(args,conf){
  const r=await api('/api/cmd',{args,confirme:!!conf});
  if(r.code!==0 && !conf) bd('bad','Échec : '+(r.out||'').trim().split('\n')[0]);
  await charger(); if(SEC==='modpack') majMods();
  return r;
}
async function champ(id,ch,el){
  const v=document.getElementById(el).value.trim(), e=document.getElementById('e-'+id);
  if(e) e.textContent='';
  if(v&&RESERVE.test(v)){ if(e) e.textContent='valeur réservée ("'+v+'") : elle serait convertie.'; return; }
  await lancer(['set',id,ch,v===''?'null':v]);
}
async function couleur(id){
  const h=document.getElementById('ch-'+id).value.trim().toUpperCase();
  const e=document.getElementById('e-'+id); e.textContent='';
  if(!/^#[0-9A-F]{6}$/.test(h)){e.textContent='couleur attendue au format #RRGGBB';return;}
  await lancer(['set',id,'accent',h]);
}
async function bool(id,ch,v){ await lancer(['set',id,ch,v?'true':'false']); }
async function news(id){
  const l=document.getElementById('nw-'+id).value.split('\n').map(s=>s.trim()).filter(Boolean).slice(0,4);
  await lancer(['news',id,'clear','fr']);
  for(const x of l) await lancer(['news',id,'add',x,'fr']);
}
async function cfg(k){
  const v=document.getElementById('cf-'+k).value.trim();
  await lancer(['config',k,v===''?'null':v]);
}
async function annonce(){
  const v=$('#an').value.trim();
  await lancer(['config','announce.fr',v===''?'null':v]);
}
async function creer(){
  const e=$('#np-err'); e.textContent='';
  const id=$('#np-id').value.trim().toLowerCase();
  if(!/^[a-z0-9][a-z0-9-]*$/.test(id)){e.textContent='identifiant : minuscules, chiffres, tirets';return;}
  const o={id,name:$('#np-nom').value.trim()||id.toUpperCase(),
    channel:$('#np-canal').value.trim()||id,accent:$('#np-col').value.toUpperCase(),
    tagline:{fr:$('#np-tag').value.trim(),en:$('#np-tag').value.trim()}};
  const s=$('#np-srv').value.trim(); if(s) o.server=s;
  const r=await lancer(['add',JSON.stringify(o)]);
  if(r.code===0){ SEL=id; SEC='modpack';
    document.querySelectorAll('nav a').forEach(x=>x.classList.toggle('on',x.dataset.s==='modpack'));
    rendre(); majMods(); }
  else e.textContent=(r.out||'').trim().split('\n')[0];
}
async function publier(){
  if(!confirm('Publier le catalogue ?\n\nTous les joueurs le recevront au prochain démarrage du launcher.')) return;
  const r=await lancer(['publish'],true);
  alert(r.code===0?'Catalogue publié.':'Échec :\n'+r.out);
}
$('#fart').onchange=()=>{ const f=$('#fart').files[0]; if(f) envoyerArt(f); };
charger(); setInterval(()=>{ if(SEC!=='modpack') charger(); },90000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _envoi(self, code, corps, ctype="application/json; charset=utf-8"):
        data = corps if isinstance(corps, bytes) else corps.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/etat":
            return self._envoi(200, json.dumps(etat(), ensure_ascii=False))
        if u.path == "/api/modrinth":
            mc = (q.get("mc") or ["1.21.1"])[0]
            return self._envoi(200, json.dumps(
                {"resultats": mr_search((q.get("q") or [""])[0], mc)}, ensure_ascii=False))
        if u.path == "/api/verifier":
            slug = (q.get("slug") or [""])[0]
            mc = (q.get("mc") or ["1.21.1"])[0]
            v = mr_versions(slug, mc)
            if not v:
                return self._envoi(200, json.dumps({"ok": False, "slug": slug}))
            f = (v[0].get("files") or [{}])[0].get("filename", "")
            proj = _get("%s/project/%s" % (MODRINTH, urllib.parse.quote(slug)), cache=600) or {}
            return self._envoi(200, json.dumps(
                {"ok": True, "slug": slug, "fichier": f, "versions": len(v),
                 "prefixe": mr_prefixe(f, slug), "icone": proj.get("icon_url")},
                ensure_ascii=False))
        if u.path.startswith("/api/art/"):
            f = os.path.join(ARTS, os.path.basename(u.path[9:]))
            if not os.path.isfile(f):
                return self._envoi(404, json.dumps({"erreur": "inconnu"}))
            t = "image/png" if f.lower().endswith(".png") else "image/jpeg"
            return self._envoi(200, open(f, "rb").read(), t)
        if u.path == "/api/canal":
            try:
                local = json.load(open(CATALOG, encoding="utf-8"))
            except Exception as e:
                return self._envoi(200, json.dumps({"erreur": "catalogue illisible : %s" % e}))
            nom = (q.get("nom") or [""])[0].strip().lower()
            return self._envoi(200, json.dumps(etat_canal(local, nom), ensure_ascii=False))
        if u.path in ("/", "/index.html"):
            return self._envoi(200, PAGE, "text/html; charset=utf-8")
        self._envoi(404, json.dumps({"erreur": "inconnu"}))

    def _catalogue(self):
        return json.load(open(CATALOG, encoding="utf-8"))

    def _depot(self, u):
        """Le navigateur poste les octets bruts du jar : pas de multipart a lire."""
        q = urllib.parse.parse_qs(u.query)
        nom = os.path.basename((q.get("nom") or ["mod.jar"])[0])
        nom = re.sub(r"[^A-Za-z0-9._+-]", "_", nom)[:80] or "mod.jar"
        mc = (q.get("mc") or ["1.21.1"])[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0:
            return self._envoi(400, json.dumps({"ok": False, "erreur": "fichier vide"}))
        if n > MAX_JAR:
            return self._envoi(400, json.dumps(
                {"ok": False, "erreur": "%.0f Mo — au-dela de la limite de %d Mo"
                 % (n / 1048576.0, MAX_JAR // 1048576)}))
        os.makedirs(JARS, exist_ok=True)
        jid = time.strftime("%Y%m%d-%H%M%S-") + nom
        dst, reste = os.path.join(JARS, jid), n
        with open(dst, "wb") as f:
            while reste > 0:
                bloc = self.rfile.read(min(262144, reste))
                if not bloc:
                    break
                f.write(bloc)
                reste -= len(bloc)
        if reste:
            os.remove(dst)
            return self._envoi(400, json.dumps({"ok": False, "erreur": "envoi interrompu"}))
        for vieux in sorted(os.listdir(JARS))[:-20]:
            try:
                os.remove(os.path.join(JARS, vieux))
            except Exception:
                pass
        info = jar_info(dst, mc)
        info["id"], info["fichier"] = jid, nom
        if info.get("ok"):
            base = (info["mod_id"] or nom.rsplit(".", 1)[0]).lower()
            canal = re.sub(r"[^a-z0-9-]+", "-", base).strip("-")[:32] or "mod"
            info["canal"] = canal
            try:
                info["etat_canal"] = etat_canal(self._catalogue(), canal)
            except Exception:
                info["etat_canal"] = {}
        self._envoi(200, json.dumps(info, ensure_ascii=False))

    def _depot_art(self, u):
        q = urllib.parse.parse_qs(u.query)
        role = (q.get("role") or [""])[0]
        if role not in ROLES:
            return self._envoi(400, json.dumps({"ok": False, "erreur": "role inconnu"}))
        nom = os.path.basename((q.get("nom") or ["image.png"])[0])
        nom = re.sub(r"[^A-Za-z0-9._+-]", "_", nom)[:80] or "image.png"
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0 or n > MAX_ART:
            return self._envoi(400, json.dumps(
                {"ok": False, "erreur": "image vide ou au-dela de %d Mo"
                 % (MAX_ART // 1048576)}))
        os.makedirs(ARTS, exist_ok=True)
        aid = time.strftime("%Y%m%d-%H%M%S-") + nom
        dst, reste = os.path.join(ARTS, aid), n
        with open(dst, "wb") as f:
            while reste > 0:
                bloc = self.rfile.read(min(262144, reste))
                if not bloc:
                    break
                f.write(bloc)
                reste -= len(bloc)
        if reste:
            os.remove(dst)
            return self._envoi(400, json.dumps({"ok": False, "erreur": "envoi interrompu"}))
        for vieux in sorted(os.listdir(ARTS))[:-30]:
            try:
                os.remove(os.path.join(ARTS, vieux))
            except Exception:
                pass
        self._envoi(200, json.dumps({"ok": True, "id": aid, "octets": n}))

    def _art(self, corps, retirer=False):
        gid, role = str(corps.get("jeu") or ""), str(corps.get("role") or "")
        if role not in ROLES:
            return {"code": 1, "out": "role inconnu : %s" % role}
        if retirer:
            return dict(zip(("code", "out"),
                            echelon(["art", gid, role, "--none"])[:2]))
        aid = os.path.basename(str(corps.get("id") or ""))
        chemin = os.path.join(ARTS, aid)
        if not aid or not os.path.isfile(chemin):
            return {"code": 1, "out": "image introuvable — redepose-la"}
        go = bool(corps.get("confirme"))
        code, out, _ = echelon(["art", gid, role, chemin] + (["--yes"] if go else []),
                               confirme=go)
        return {"code": code, "out": out}

    def _git_envoyer(self, corps):
        """add + commit + push, avec le meme esprit que le reste : on montre
        ce qui part, on refuse les binaires, on exige une confirmation."""
        if not corps.get("confirme"):
            return {"code": 1, "out": "envoi vers GitHub : confirmation requise"}
        msg = str(corps.get("message") or "").strip()
        if len(msg) < 5:
            return {"code": 1, "out": "message de commit trop court"}
        g = git_etat()
        if not g["branche"]:
            return {"code": 1, "out": "pas un dépôt git"}
        lourds = [f["chemin"] for f in g["fichiers"] if f["lourd"]]
        if lourds and not corps.get("forcer"):
            return {"code": 1, "out": "refusé : %s resterait dans l'historique git "
                                      "pour toujours. Les jars passent par "
                                      "./echelon release, pas par git."
                                      % ", ".join(lourds[:5])}
        etapes, sortie = [], []
        if g["fichiers"]:
            etapes += [["add", "-A"], ["commit", "-m", msg]]
        if not etapes and not g["devant"]:
            return {"code": 1, "out": "rien à envoyer : le dépôt est propre et à jour"}
        etapes.append(["push"])
        with VERROU:
            for args in etapes:
                code, out = _run(["git", "-C", ROOT] + args, timeout=300)
                sortie.append("$ git %s\n%s" % (" ".join(args), out.strip()))
                JOURNAL.insert(0, {"t": time.strftime("%H:%M:%S"),
                                   "cmd": "git " + " ".join(args),
                                   "code": code, "out": out.strip()[-2000:]})
                if code != 0:
                    del JOURNAL[60:]
                    return {"code": code, "out": "\n\n".join(sortie)}
            del JOURNAL[60:]
        return {"code": 0, "out": "\n\n".join(sortie)}

    def _publier_jar(self, corps):
        jid = os.path.basename(str(corps.get("id") or ""))
        chemin = os.path.join(JARS, jid)
        if not jid or not os.path.isfile(chemin):
            return {"code": 1, "out": "jar introuvable — redepose-le"}
        try:
            cat = self._catalogue()
        except Exception as e:
            return {"code": 1, "out": "catalogue illisible : %s" % e}
        gid = str(corps.get("jeu") or "")
        jeu = next((g for g in cat.get("games", []) if g.get("id") == gid), None)
        if jeu is None:
            return {"code": 1, "out": "projet inconnu : %s" % gid}
        canal = str(corps.get("canal") or "").strip().lower()
        st = etat_canal(cat, canal)
        if st.get("erreur"):
            return {"code": 1, "out": st["erreur"]}
        ver = str(corps.get("version") or "").strip()
        if not re.fullmatch(r"[\w.+-]{1,32}", ver):
            return {"code": 1, "out": "version invalide : lettres, chiffres, . _ + -"}
        go = bool(corps.get("confirme"))
        args = ["release", canal, chemin, ver] + (["--yes"] if go else [])
        code, out, _ = echelon(args, confirme=go)
        if go and code == 0:
            extra = [e for e in (jeu.get("extra") or []) if isinstance(e, dict)]
            if not any(e.get("channel") == canal for e in extra):
                extra.append({"channel": canal, "file": canal + ".jar"})
                c2, o2, _ = echelon(["set", gid, "extra",
                                     json.dumps(extra, ensure_ascii=False)])
                out += "\n" + o2
                code = code or c2
        return {"code": code, "out": out}

    def _retirer_jar(self, corps):
        try:
            cat = self._catalogue()
        except Exception as e:
            return {"code": 1, "out": "catalogue illisible : %s" % e}
        gid, canal = str(corps.get("jeu") or ""), str(corps.get("canal") or "")
        jeu = next((g for g in cat.get("games", []) if g.get("id") == gid), None)
        if jeu is None:
            return {"code": 1, "out": "projet inconnu : %s" % gid}
        extra = [e for e in (jeu.get("extra") or [])
                 if isinstance(e, dict) and e.get("channel") != canal]
        code, out, _ = echelon(["set", gid, "extra", json.dumps(extra, ensure_ascii=False)])
        if code == 0 and corps.get("purger"):
            # sans purge le jar reste dans le dossier mods du joueur pour toujours
            pl = [x for x in (jeu.get("purge") or []) if isinstance(x, str)]
            if canal not in pl:
                pl.append(canal)
                c2, o2, _ = echelon(["set", gid, "purge", json.dumps(pl)])
                out += "\n" + o2
                code = code or c2
        return {"code": code, "out": out}

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/jar":
            return self._depot(u)
        if u.path == "/api/art":
            return self._depot_art(u)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corps = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._envoi(400, json.dumps({"erreur": "corps illisible: %s" % e}))
        if u.path == "/api/jar/publier":
            return self._envoi(200, json.dumps(self._publier_jar(corps), ensure_ascii=False))
        if u.path == "/api/jar/retirer":
            return self._envoi(200, json.dumps(self._retirer_jar(corps), ensure_ascii=False))
        if u.path == "/api/art/publier":
            return self._envoi(200, json.dumps(self._art(corps), ensure_ascii=False))
        if u.path == "/api/art/retirer":
            return self._envoi(200, json.dumps(self._art(corps, True), ensure_ascii=False))
        if u.path == "/api/git":
            return self._envoi(200, json.dumps(self._git_envoyer(corps), ensure_ascii=False))
        if self.path.startswith("/api/cmd"):
            args = corps.get("args") or []
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                return self._envoi(400, json.dumps({"erreur": "args invalides"}))
            code, out, sauve = echelon(args, confirme=bool(corps.get("confirme")))
            return self._envoi(200, json.dumps({"code": code, "out": out,
                                                "sauvegarde": sauve}, ensure_ascii=False))
        self._envoi(404, json.dumps({"erreur": "inconnu"}))

    def log_message(self, *a):
        pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://127.0.0.1:%d" % PORT
    print("panneau de gestion : %s" % url)
    print("  racine : %s" % ROOT)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\narret")


if __name__ == "__main__":
    main()
