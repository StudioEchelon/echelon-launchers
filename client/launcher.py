#!/usr/bin/env python3
"""
STUDIO ECHELON CLIENT — LE launcher des jeux Echelon : tout est intégré.
Sidebar de logos, key-art plein écran, pseudo, JOUER → installe MC + Fabric +
Java + le mod (bootstrap GitHub) et lance le jeu. Pas de launcher tiers.
Police Zalando Sans Expanded embarquée.
"""
import os, sys, math, random, json, shutil, platform, subprocess, threading, uuid, webbrowser
import collections

# ── lancement du jeu ────────────────────────────────────────────────────
# Sans ça, Windows ouvre une console noire par-dessus le jeu : ça inquiète
# les joueurs (« on me hacke ? »). CREATE_NO_WINDOW la supprime, et la sortie
# part dans un fichier + un tampon mémoire que la page Journal affiche.
GAME_LOG = collections.deque(maxlen=800)


def launch_game(cmd, cwd):
    """Lance le jeu sans console visible et capte sa sortie."""
    kwargs = {"cwd": cwd, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT,
              "text": True, "errors": "replace", "bufsize": 1}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, **kwargs)

    def pump():
        try:
            log_path = os.path.join(cwd, "logs")
            os.makedirs(log_path, exist_ok=True)
            f = open(os.path.join(log_path, "launcher-game.log"), "w",
                     encoding="utf-8", errors="replace")
        except Exception:
            f = None
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                GAME_LOG.append(line)
                if f:
                    f.write(line + "\n"); f.flush()
        except Exception:
            pass
        finally:
            if f:
                f.close()

    threading.Thread(target=pump, daemon=True).start()
    return proc

import tkinter as tk
import tkinter.font as tkfont

try:
    from PIL import Image, ImageTk, ImageEnhance, ImageDraw, ImageFilter
except ImportError:
    print("pip install pillow")
    sys.exit(1)
try:
    import minecraft_launcher_lib as mll
except ImportError:
    mll = None   # l'UI s'ouvre quand même ; erreur propre au clic JOUER

W, H = 1180, 700
SIDEBAR = 210
FPS_MS = 40
MC_VERSION = "1.21.1"
JAVA_RUNTIME = "java-runtime-delta"
RELEASES = "https://github.com/StudioEchelon/echelon-launchers/releases/download"
BG = "#0A0C0E"
FADE_STEPS = 7
CLIENT_VERSION = "1.4"
CLIENT_BASE = RELEASES + "/client"   # manifest.json + StudioEchelonClient.exe


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ── journal : StudioEchelon/launcher.log (diagnostic joueurs) ─────────
import logging


def setup_log():
    try:
        d = game_root("StudioEchelon")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "launcher.log")
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, path + ".old")   # rotation simple
        logging.basicConfig(filename=path, level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
        logging.info("=== Studio Echelon Client v%s — %s ===",
                     CLIENT_VERSION, platform.platform())
    except Exception:
        pass


def GT(g, key, lang, default=""):
    """champ de catalogue traduisible : dict {lang: …} ou valeur brute."""
    v = g.get(key, default)
    if isinstance(v, dict):
        return v.get(lang) or v.get("fr") or next(iter(v.values()), default)
    return v


def game_root(name):
    if platform.system() == "Windows":
        return os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), name)
    return os.path.expanduser("~/" + name)


# ── i18n : 7 langues principales ──────────────────────────────────────
LANGS = [
    ("fr", "Français", "🇫🇷"),
    ("en", "English", "🇬🇧"),
    ("es", "Español", "🇪🇸"),
    ("de", "Deutsch", "🇩🇪"),
    ("pt", "Português", "🇵🇹"),
    ("it", "Italiano", "🇮🇹"),
    ("ru", "Русский", "🇷🇺"),
]

TR = {
    "online": {"fr": "En ligne", "en": "Online", "es": "En línea", "de": "Online",
               "pt": "Online", "it": "Online", "ru": "В сети"},
    "discord": {"fr": "Rejoindre le Discord", "en": "Join the Discord", "es": "Unirse al Discord",
                "de": "Discord beitreten", "pt": "Entrar no Discord", "it": "Unisciti al Discord",
                "ru": "Присоединиться к Discord"},
    "pseudo": {"fr": "PSEUDO", "en": "USERNAME", "es": "USUARIO", "de": "NAME",
               "pt": "USUÁRIO", "it": "NOME", "ru": "ИМЯ"},
    "play": {"fr": "JOUER", "en": "PLAY", "es": "JUGAR", "de": "SPIELEN",
             "pt": "JOGAR", "it": "GIOCA", "ru": "ИГРАТЬ"},
    "installing": {"fr": "INSTALLATION…", "en": "INSTALLING…", "es": "INSTALANDO…",
                   "de": "INSTALLATION…", "pt": "INSTALANDO…", "it": "INSTALLAZIONE…",
                   "ru": "УСТАНОВКА…"},
    "options": {"fr": "OPTIONS", "en": "OPTIONS", "es": "OPCIONES", "de": "OPTIONEN",
                "pt": "OPÇÕES", "it": "OPZIONI", "ru": "НАСТРОЙКИ"},
    "opt_sub": {"fr": "réglages propres à {n}", "en": "settings for {n}", "es": "ajustes de {n}",
                "de": "Einstellungen für {n}", "pt": "ajustes de {n}", "it": "impostazioni per {n}",
                "ru": "настройки для {n}"},
    "ram": {"fr": "Mémoire allouée", "en": "Allocated memory", "es": "Memoria asignada",
            "de": "Zugewiesener Speicher", "pt": "Memória alocada", "it": "Memoria allocata",
            "ru": "Выделенная память"},
    "ram_sub": {"fr": "RAM réservée au jeu", "en": "RAM reserved for the game",
                "es": "RAM reservada al juego", "de": "Für das Spiel reservierter RAM",
                "pt": "RAM reservada ao jogo", "it": "RAM riservata al gioco",
                "ru": "ОЗУ для игры"},
    "rpc": {"fr": "Discord Rich Presence", "en": "Discord Rich Presence",
            "es": "Discord Rich Presence", "de": "Discord Rich Presence",
            "pt": "Discord Rich Presence", "it": "Discord Rich Presence",
            "ru": "Discord Rich Presence"},
    "rpc_sub": {"fr": "affiche ta partie sur ton profil Discord",
                "en": "shows your session on your Discord profile",
                "es": "muestra tu partida en tu perfil de Discord",
                "de": "zeigt dein Spiel in deinem Discord-Profil",
                "pt": "mostra a sua partida no seu perfil Discord",
                "it": "mostra la tua partita sul profilo Discord",
                "ru": "показывает игру в профиле Discord"},
    "close": {"fr": "Fermer au lancement", "en": "Close on launch", "es": "Cerrar al iniciar",
              "de": "Beim Start schließen", "pt": "Fechar ao iniciar", "it": "Chiudi all'avvio",
              "ru": "Закрыть при запуске"},
    "close_sub": {"fr": "le launcher se ferme quand le jeu démarre",
                  "en": "the launcher closes when the game starts",
                  "es": "el launcher se cierra al iniciar el juego",
                  "de": "der Launcher schließt beim Spielstart",
                  "pt": "o launcher fecha quando o jogo inicia",
                  "it": "il launcher si chiude all'avvio del gioco",
                  "ru": "лаунчер закрывается при старте игры"},
    "folder": {"fr": "Dossier du jeu", "en": "Game folder", "es": "Carpeta del juego",
               "de": "Spielordner", "pt": "Pasta do jogo", "it": "Cartella del gioco",
               "ru": "Папка игры"},
    "open": {"fr": "OUVRIR", "en": "OPEN", "es": "ABRIR", "de": "ÖFFNEN",
             "pt": "ABRIR", "it": "APRI", "ru": "ОТКРЫТЬ"},
    "done": {"fr": "TERMINÉ", "en": "DONE", "es": "HECHO", "de": "FERTIG",
             "pt": "CONCLUÍDO", "it": "FATTO", "ru": "ГОТОВО"},
    "studio_role": {"fr": "Éditeur & créateur de ces projets",
                    "en": "Publisher & creator of these projects",
                    "es": "Editor y creador de estos proyectos",
                    "de": "Herausgeber & Schöpfer dieser Projekte",
                    "pt": "Editor e criador destes projetos",
                    "it": "Editore e creatore di questi progetti",
                    "ru": "Издатель и создатель этих проектов"},
    "see_site": {"fr": "Voir le site", "en": "Visit the website", "es": "Ver el sitio",
                 "de": "Website besuchen", "pt": "Ver o site", "it": "Vai al sito",
                 "ru": "Открыть сайт"},
    "language": {"fr": "Langue", "en": "Language", "es": "Idioma", "de": "Sprache",
                 "pt": "Idioma", "it": "Lingua", "ru": "Язык"},
    "ready": {"fr": "", "en": "", "es": "", "de": "", "pt": "", "it": "", "ru": ""},
    "installing_mc": {"fr": "Installation de Minecraft {v} + Fabric…",
                      "en": "Installing Minecraft {v} + Fabric…",
                      "es": "Instalando Minecraft {v} + Fabric…",
                      "de": "Installiere Minecraft {v} + Fabric…",
                      "pt": "Instalando Minecraft {v} + Fabric…",
                      "it": "Installazione di Minecraft {v} + Fabric…",
                      "ru": "Установка Minecraft {v} + Fabric…"},
    "installing_java": {"fr": "Installation de Java 21 (Mojang)…",
                        "en": "Installing Java 21 (Mojang)…", "es": "Instalando Java 21 (Mojang)…",
                        "de": "Installiere Java 21 (Mojang)…", "pt": "Instalando Java 21 (Mojang)…",
                        "it": "Installazione di Java 21 (Mojang)…", "ru": "Установка Java 21 (Mojang)…"},
    "launching": {"fr": "Lancement de {n}…", "en": "Launching {n}…", "es": "Iniciando {n}…",
                  "de": "Starte {n}…", "pt": "Iniciando {n}…", "it": "Avvio di {n}…",
                  "ru": "Запуск {n}…"},
    "cancel": {"fr": "ANNULER", "en": "CANCEL", "es": "CANCELAR", "de": "ABBRECHEN",
               "pt": "CANCELAR", "it": "ANNULLA", "ru": "ОТМЕНА"},
    "cancelled": {"fr": "Annulé.", "en": "Cancelled.", "es": "Cancelado.", "de": "Abgebrochen.",
                  "pt": "Cancelado.", "it": "Annullato.", "ru": "Отменено."},
    "offline": {"fr": "Hors ligne", "en": "Offline", "es": "Desconectado", "de": "Offline",
                "pt": "Offline", "it": "Offline", "ru": "Не в сети"},
    "players": {"fr": "en ligne", "en": "online", "es": "en línea", "de": "online",
                "pt": "online", "it": "online", "ru": "в сети"},
    "news": {"fr": "NOUVEAUTÉS", "en": "NEWS", "es": "NOVEDADES", "de": "NEUIGKEITEN",
             "pt": "NOVIDADES", "it": "NOVITÀ", "ru": "НОВОСТИ"},
    "downloading": {"fr": "Téléchargement de {n}…", "en": "Downloading {n}…",
                    "es": "Descargando {n}…", "de": "Lade {n} herunter…",
                    "pt": "Baixando {n}…", "it": "Scaricamento di {n}…",
                    "ru": "Загрузка {n}…"},
    "skin": {"fr": "Skin du joueur", "en": "Player skin", "es": "Skin del jugador",
             "de": "Spieler-Skin", "pt": "Skin do jogador", "it": "Skin del giocatore",
             "ru": "Скин игрока"},
    "skin_sub": {"fr": "visible par tous les joueurs en jeu", "en": "visible to every player in game",
                 "es": "visible para todos en el juego", "de": "für alle Spieler sichtbar",
                 "pt": "visível para todos no jogo", "it": "visibile a tutti in gioco",
                 "ru": "виден всем игрокам"},
    "change": {"fr": "CHANGER", "en": "CHANGE", "es": "CAMBIAR", "de": "ÄNDERN",
               "pt": "MUDAR", "it": "CAMBIA", "ru": "СМЕНИТЬ"},
    "skin_premium": {"fr": "Depuis un pseudo Minecraft premium", "en": "From a premium Minecraft username",
                     "es": "Desde un usuario premium", "de": "Von einem Premium-Namen",
                     "pt": "De um nick premium", "it": "Da un nickname premium",
                     "ru": "По нику premium-аккаунта"},
    "import": {"fr": "IMPORTER", "en": "IMPORT", "es": "IMPORTAR", "de": "IMPORTIEREN",
               "pt": "IMPORTAR", "it": "IMPORTA", "ru": "ИМПОРТ"},
    "skin_file": {"fr": "OU CHOISIR UN FICHIER…", "en": "OR PICK A FILE…", "es": "O ELEGIR ARCHIVO…",
                  "de": "ODER DATEI WÄHLEN…", "pt": "OU ESCOLHER ARQUIVO…", "it": "O SCEGLI UN FILE…",
                  "ru": "ИЛИ ВЫБРАТЬ ФАЙЛ…"},
    "skin_ok": {"fr": "Skin appliqué !", "en": "Skin applied!", "es": "¡Skin aplicada!",
                "de": "Skin angewendet!", "pt": "Skin aplicada!", "it": "Skin applicata!",
                "ru": "Скин применён!"},
    "skin_err": {"fr": "Introuvable — pseudo premium ?", "en": "Not found — premium name?",
                 "es": "No encontrado", "de": "Nicht gefunden", "pt": "Não encontrado",
                 "it": "Non trovato", "ru": "Не найден"},
    "skin_none": {"fr": "Aucun skin — Steve par défaut", "en": "No skin — default Steve",
                  "es": "Sin skin", "de": "Kein Skin", "pt": "Sem skin", "it": "Nessuna skin",
                  "ru": "Нет скина"},
    "log": {"fr": "Journal", "en": "Log", "es": "Registro", "de": "Protokoll",
            "pt": "Registo", "it": "Registro", "ru": "Журнал"},
    "log_sub": {"fr": "sortie du jeu — utile pour signaler un bug",
                "en": "game output — useful to report a bug",
                "es": "salida del juego — útil para reportar un fallo",
                "de": "Spielausgabe — nützlich für Fehlerberichte",
                "pt": "saída do jogo — útil para reportar um bug",
                "it": "output del gioco — utile per segnalare un bug",
                "ru": "вывод игры — пригодится для отчёта об ошибке"},
    "log_empty": {"fr": "Aucun journal — lance le jeu d'abord.",
                  "en": "No log yet — launch the game first.",
                  "es": "Sin registro — inicia el juego primero.",
                  "de": "Kein Protokoll — starte zuerst das Spiel.",
                  "pt": "Sem registo — inicia o jogo primeiro.",
                  "it": "Nessun registro — avvia prima il gioco.",
                  "ru": "Журнал пуст — сначала запусти игру."},
    "log_prev": {"fr": "Un fichier de la session précédente existe : logs/launcher-game.log",
                 "en": "A file from the previous session exists: logs/launcher-game.log",
                 "es": "Existe un archivo de la sesión anterior: logs/launcher-game.log",
                 "de": "Datei der letzten Sitzung vorhanden: logs/launcher-game.log",
                 "pt": "Existe um ficheiro da sessão anterior: logs/launcher-game.log",
                 "it": "Esiste un file della sessione precedente: logs/launcher-game.log",
                 "ru": "Есть файл прошлой сессии: logs/launcher-game.log"},
    "log_copy": {"fr": "COPIER", "en": "COPY", "es": "COPIAR", "de": "KOPIEREN",
                 "pt": "COPIAR", "it": "COPIA", "ru": "КОПИРОВАТЬ"},
    "log_copied": {"fr": "Journal copié !", "en": "Log copied!", "es": "¡Registro copiado!",
                   "de": "Protokoll kopiert!", "pt": "Registo copiado!",
                   "it": "Registro copiato!", "ru": "Журнал скопирован!"},
    "log_folder": {"fr": "OUVRIR LE DOSSIER", "en": "OPEN FOLDER", "es": "ABRIR CARPETA",
                   "de": "ORDNER ÖFFNEN", "pt": "ABRIR PASTA", "it": "APRI CARTELLA",
                   "ru": "ОТКРЫТЬ ПАПКУ"},
    "log_mod": {"fr": "Mod", "en": "Mod", "es": "Mod", "de": "Mod",
                "pt": "Mod", "it": "Mod", "ru": "Мод"},
    "log_java": {"fr": "Java", "en": "Java", "es": "Java", "de": "Java",
                 "pt": "Java", "it": "Java", "ru": "Java"},
    "log_unknown": {"fr": "inconnu", "en": "unknown", "es": "desconocido", "de": "unbekannt",
                    "pt": "desconhecido", "it": "sconosciuto", "ru": "неизвестно"},
    "have_fun": {"fr": "Bon jeu ! (tu peux fermer le launcher)",
                 "en": "Have fun! (you can close the launcher)",
                 "es": "¡Diviértete! (puedes cerrar el launcher)",
                 "de": "Viel Spaß! (du kannst den Launcher schließen)",
                 "pt": "Bom jogo! (podes fechar o launcher)",
                 "it": "Buon gioco! (puoi chiudere il launcher)",
                 "ru": "Приятной игры! (можно закрыть лаунчер)"},
}


# Catalogue par défaut EMBARQUÉ (fallback si pas de connexion au 1er lancement).
# En vrai, la liste des jeux vient du catalogue distant (catalog.json sur le
# canal client) → ajouter/modifier un projet = éditer ce JSON, sans rebuild.
DEFAULT_GAMES = [
    {
        "id": "harbor",
        "name": "HARBOR",
        "tagline": {"fr": "Raft × Sea of Thieves — survis, navigue, pille.",
                    "en": "Raft × Sea of Thieves — survive, sail, plunder.",
                    "es": "Raft × Sea of Thieves — sobrevive, navega, saquea.",
                    "de": "Raft × Sea of Thieves — überlebe, segle, plündere.",
                    "pt": "Raft × Sea of Thieves — sobrevive, navega, saqueia.",
                    "it": "Raft × Sea of Thieves — sopravvivi, naviga, saccheggia.",
                    "ru": "Raft × Sea of Thieves — выживай, плыви, грабь."},
        "accent": "#5AE68C",
        "accent_dim": "#2E7B4C",
        "logo": "assets/harbor_logo.png",
        "bg": "assets/harbor_bg.png",
        "dir": game_root("Harbor"),
        "base": RELEASES + "/harbor",
        "mod_file": "harbor.jar",
        "seed": "harbor:",
        "deps": {"fabric-api": "fabric-api", "sodium": "sodium", "lithium": "lithium"},
        "purge": [],
        "extra": [{"channel": "echelonskin", "file": "echelonskin.jar"}],
        "server": "144.217.79.184:25569",
        "news": {"fr": ["Ton raft navigue au vent, océan vivant",
                        "10 donjons pirates, Kraken, Sans-Tête",
                        "Cartes au trésor, canons, armure Zircon",
                        "Voix de proximité, emotes, clans"],
                 "en": ["Your raft sails the wind, living ocean",
                        "10 pirate dungeons, Kraken, Headless",
                        "Treasure maps, cannons, Zircon armor",
                        "Proximity voice, emotes, clans"]},
        "play": "JOUER",
        "discord": "https://playechelon.net",
    },
    {
        "id": "donshot",
        "name": "DON SHOT",
        "tagline": {"fr": "Hero shooter — 35 héros, duels, ligues.",
                    "en": "Hero shooter — 35 heroes, duels, leagues.",
                    "es": "Hero shooter — 35 héroes, duelos, ligas.",
                    "de": "Hero-Shooter — 35 Helden, Duelle, Ligen.",
                    "pt": "Hero shooter — 35 heróis, duelos, ligas.",
                    "it": "Hero shooter — 35 eroi, duelli, leghe.",
                    "ru": "Геройский шутер — 35 героев, дуэли, лиги."},
        "accent": "#54E63C",
        "accent_dim": "#2FA84C",
        "logo": "assets/donshot_logo.png",
        "bg": "assets/donshot_bg.png",
        "dir": game_root("DonShot"),
        "base": RELEASES + "/donshot",
        "mod_file": "donshot.jar",
        "seed": "donshot:",
        "deps": {"fabric-api": "fabric-api", "geckolib": "geckolib", "sodium": "sodium",
                 "lithium": "lithium", "notenoughanimations": "not-enough-animations",
                 "PresenceFootsteps": "presence-footsteps"},
        "purge": ["firstperson"],
        "extra": [{"channel": "echelonskin", "file": "echelonskin.jar"}],
        "server": "66.70.176.150:25567",
        "news": {"fr": ["35 héros uniques, armes 3D et ultis",
                        "Duels contre bots, ligues et trophées",
                        "Coffres, cartes, Route du Don"],
                 "en": ["35 unique heroes, 3D guns and ults",
                        "Bot duels, leagues and trophies",
                        "Chests, cards, the Don Road"]},
        "play": "JOUER",
        "discord": "https://playechelon.net",
    },
]

GAMES = []   # rempli au démarrage depuis le catalogue distant (ou le défaut)


def _cache_dir():
    d = os.path.join(game_root("StudioEchelon"), "cache")
    os.makedirs(d, exist_ok=True)
    return d


def _cached_asset(url):
    """télécharge une image d'asset si absente (nom = hash de l'URL) → chemin local."""
    import urllib.request, hashlib
    ext = ".png"
    name = hashlib.sha1(url.encode()).hexdigest()[:16] + ext
    path = os.path.join(_cache_dir(), name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "echelon-client"})
        tmp = path + ".part"
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, path)
    return path


def _normalize(entry):
    """convertit une entrée de catalogue (JSON) en jeu prêt à l'emploi."""
    gid = entry["id"]
    g = dict(entry)
    g["dir"] = game_root(entry.get("dir_name", entry["name"].replace(" ", "")))
    g["base"] = RELEASES + "/" + entry.get("channel", gid)
    g["seed"] = gid + ":"
    g["mod_file"] = entry.get("mod_file", gid + ".jar")
    g["deps"] = entry.get("deps", {"fabric-api": "fabric-api", "sodium": "sodium", "lithium": "lithium"})
    g["purge"] = entry.get("purge", [])
    g["extra"] = entry.get("extra", [])
    g["accent_dim"] = entry.get("accent_dim", entry["accent"])
    # assets : URL distante (cache local) sinon chemin embarqué
    for k, urlk in (("logo", "logo_url"), ("bg", "bg_url")):
        if entry.get(urlk):
            try:
                g[k] = _cached_asset(entry[urlk])
            except Exception:
                g[k] = entry.get(k, f"assets/{gid}_{k}.png")   # repli embarqué
        else:
            g[k] = entry.get(k, f"assets/{gid}_{k}.png")
    return g


def load_games():
    """catalogue distant → cache → défaut embarqué. Jamais bloquant."""
    import urllib.request
    raw = None
    cache = os.path.join(game_root("StudioEchelon"), "catalog.json")
    try:
        req = urllib.request.Request(CLIENT_BASE + "/catalog.json",
                                     headers={"User-Agent": "echelon-client"})
        raw = json.load(urllib.request.urlopen(req, timeout=8)).get("games")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump({"games": raw}, open(cache, "w"))
    except Exception:
        try:
            raw = json.load(open(cache)).get("games")
        except Exception:
            raw = None
    if not raw:
        return list(DEFAULT_GAMES)
    out = []
    for entry in raw:
        try:
            out.append(_normalize(entry))
        except Exception:
            pass
    return out or list(DEFAULT_GAMES)


class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        # auto-update du hub AVANT toute UI : si un nouvel exe est publié,
        # on le télécharge, on se remplace et on redémarre.
        if self._self_update():
            self.destroy()
            return
        global GAMES
        GAMES = load_games()   # catalogue distant → cache → défaut
        self.title("Studio Echelon")
        self._install_font()
        try:
            icon = Image.open(resource("assets/studio_icon.png"))
            icon.thumbnail((128, 128))
            self._app_icon = ImageTk.PhotoImage(icon)
            self.iconphoto(True, self._app_icon)
        except Exception:
            pass
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.configure(bg=BG)

        fams = set(tkfont.families())
        self.FONT = "Zalando Sans Expanded" if "Zalando Sans Expanded" in fams else "Helvetica"

        self.selected = 0
        self.lang = self._state().get("lang", "fr")
        if self.lang not in [c for c, _, _ in LANGS]:
            self.lang = "fr"
        self.lang_open = False
        self.options_open = False
        self.skin_open = False
        # page Journal : sortie du jeu (GAME_LOG), scroll + auto-suivi
        self.log_open = False
        self.log_off = 0          # nb de lignes remontées depuis le bas (0 = suit)
        self.log_status = ""
        self._log_job = None
        self._log_items = []
        self._log_drag_y = None
        self._java_path = None
        self.skin_input = ""
        self.skin_focus = False
        self.skin_status = ""
        self.status = tk.StringVar(value="")
        self.progress_val = tk.DoubleVar(value=0)
        self.busy = False
        self._cancel = False
        self._online = {}   # id de jeu → nb de joueurs (None = injoignable)
        self._img_cache = {}
        self._fade_cache = {}
        self._fading = None
        self.hover = None
        self.t = 0.0
        self.particles = [[random.uniform(SIDEBAR, W), random.uniform(0, H),
                           random.uniform(0.25, 0.9), random.randint(1, 3)] for _ in range(26)]

        self.canvas = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg=BG)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)
        # molette + glissement : uniquement utiles à la page Journal
        self.canvas.bind("<MouseWheel>", self._log_wheel)          # Windows / macOS
        self.canvas.bind("<Button-4>", self._log_wheel)            # Linux
        self.canvas.bind("<Button-5>", self._log_wheel)
        self.canvas.bind("<B1-Motion>", self._log_drag)
        self.canvas.bind("<ButtonRelease-1>", self._log_drag_end)

        # champ pseudo 100 % canvas : aucun widget natif, aucun chrome
        self.pseudo_text = self._load_pseudo()
        self.pseudo_focus = False
        self.bind("<Key>", self._key)

        threading.Thread(target=self._ping_loop, daemon=True).start()
        self._draw()
        self.after(FPS_MS, self._tick)

    # ── ping serveurs (Server List Ping, zéro dépendance) ─────────────
    @staticmethod
    def _slp(hostport, timeout=3.0):
        """interroge un serveur MC : nb de joueurs en ligne, ou None."""
        import socket, struct

        def varint(n):
            out = b""
            while True:
                b7 = n & 0x7F
                n >>= 7
                out += bytes([b7 | (0x80 if n else 0)])
                if not n:
                    return out

        def read_varint(sock):
            n = shift = 0
            while True:
                b = sock.recv(1)
                if not b:
                    raise IOError("eof")
                n |= (b[0] & 0x7F) << shift
                if not b[0] & 0x80:
                    return n
                shift += 7

        host, _, port = hostport.partition(":")
        port = int(port or 25565)
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            addr = host.encode()
            handshake = varint(0) + varint(767) + varint(len(addr)) + addr + struct.pack(">H", port) + varint(1)
            sock.sendall(varint(len(handshake)) + handshake + b"\x01\x00")
            read_varint(sock)            # taille du paquet
            read_varint(sock)            # id
            ln = read_varint(sock)       # taille du JSON
            data = b""
            while len(data) < ln:
                chunk = sock.recv(ln - len(data))
                if not chunk:
                    break
                data += chunk
            st = json.loads(data.decode("utf-8", "replace"))
            return int(st.get("players", {}).get("online", 0))

    def _ping_loop(self):
        import time
        while True:
            for g in list(GAMES):
                if not g.get("server"):
                    continue
                try:
                    self._online[g["id"]] = self._slp(g["server"])
                except Exception:
                    self._online[g["id"]] = None
            time.sleep(45)

    def _self_update(self):
        """remplace le hub par une version plus récente publiée sur le canal client.
        Ne s'active que sur l'exe figé (Windows) ; no-op en dev."""
        if not getattr(sys, "frozen", False):
            return False
        try:
            import urllib.request, hashlib
            req = urllib.request.Request(CLIENT_BASE + "/manifest.json",
                                         headers={"User-Agent": "echelon-client"})
            m = json.load(urllib.request.urlopen(req, timeout=8))

            def v(x): return tuple(int(i) for i in str(x).split("."))
            if v(m.get("client_version", "0")) <= v(CLIENT_VERSION):
                return False

            exe = sys.executable
            new = exe + ".new"
            req = urllib.request.Request(m.get("client_url", CLIENT_BASE + "/StudioEchelonClient.exe"),
                                         headers={"User-Agent": "echelon-client"})
            with urllib.request.urlopen(req, timeout=180) as r, open(new, "wb") as f:
                shutil.copyfileobj(r, f)
            if m.get("client_sha256"):
                sha = hashlib.sha256(open(new, "rb").read()).hexdigest()
                if sha != m["client_sha256"]:
                    os.remove(new)
                    return False
            # swap différé + relance (l'exe courant doit d'abord se fermer)
            if platform.system() == "Windows":
                bat = os.path.join(game_root("StudioEchelon"), "update.bat")
                os.makedirs(os.path.dirname(bat), exist_ok=True)
                with open(bat, "w") as f:
                    f.write(f'''@echo off
timeout /t 2 /nobreak >nul
move /y "{new}" "{exe}" >nul
start "" "{exe}"
del "%~f0"
''')
                subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
            else:
                os.replace(new, exe)
                subprocess.Popen([exe])
            return True
        except Exception:
            return False   # hors-ligne / erreur : on lance la version en place

    def _install_font(self):
        """Zalando embarquée : enregistrée au vol sous Windows, installée sur mac."""
        if platform.system() == "Windows":
            try:
                import ctypes
                for f in ("assets/zalando.ttf", "assets/zalando_bold.ttf"):
                    ctypes.windll.gdi32.AddFontResourceExW(resource(f), 0x10, 0)
            except Exception:
                pass

    def F(self, size, bold=False):
        return (self.FONT, size, "bold") if bold else (self.FONT, size)

    def T(self, key, **kw):
        s = TR.get(key, {}).get(self.lang) or TR.get(key, {}).get("fr", key)
        return s.format(**kw) if kw else s

    # ── images ────────────────────────────────────────────────────────
    @staticmethod
    def _hex(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

    @staticmethod
    def _asset_path(path):
        return path if os.path.isabs(path) else resource(path)

    def _load(self, path, size=None, dim=1.0):
        key = (path, size, dim)
        if key not in self._img_cache:
            im = Image.open(self._asset_path(path)).convert("RGBA")
            if size:
                im.thumbnail(size, Image.LANCZOS)
            if dim < 1.0:
                im = ImageEnhance.Brightness(im).enhance(dim)
            self._img_cache[key] = ImageTk.PhotoImage(im)
        return self._img_cache[key]

    def _bg_pil(self, game):
        key = ("bgpil", game["id"])
        if key not in self._img_cache:
            im = Image.open(self._asset_path(game["bg"])).convert("RGB")
            ratio = max(W / im.width, H / im.height)
            im = im.resize((int(im.width * ratio) + 1, int(im.height * ratio) + 1), Image.LANCZOS)
            x0 = (im.width - W) // 2
            y0 = (im.height - H) // 2
            im = im.crop((x0, y0, x0 + W, y0 + H))
            im = ImageEnhance.Brightness(im).enhance(0.85)
            grad = Image.new("L", (W, 1), 0)
            gd = ImageDraw.Draw(grad)
            for x in range(W):
                t = min(1.0, max(0.0, (x - SIDEBAR * 0.4) / (SIDEBAR * 2.2)))
                gd.point((x, 0), fill=int(255 * t))
            grad = grad.resize((W, H))
            dark = Image.new("RGB", (W, H), (8, 9, 11))
            self._img_cache[key] = Image.composite(im, dark, grad)
        return self._img_cache[key]

    def _bg_composed(self, game):
        key = ("bg", game["id"])
        if key not in self._img_cache:
            self._img_cache[key] = ImageTk.PhotoImage(self._bg_pil(game))
        return self._img_cache[key]

    def _fade_frames(self, a, b):
        key = (a["id"], b["id"])
        if key not in self._fade_cache:
            pa, pb = self._bg_pil(a), self._bg_pil(b)
            self._fade_cache[key] = [
                ImageTk.PhotoImage(Image.blend(pa, pb, (i + 1) / (FADE_STEPS + 1)))
                for i in range(FADE_STEPS)
            ]
        return self._fade_cache[key]

    def _flat(self, key, w, h, rgba, radius, top_light=False):
        ck = ("f", key, w, h)
        if ck in self._img_cache:
            return self._img_cache[ck]
        S, pad = 4, 14
        ws, hs, ps, rs = w * S, h * S, pad * S, radius * S
        im = Image.new("RGBA", ((w + pad * 2) * S, (h + pad * 2) * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((ps, ps, ps + ws - 1, ps + hs - 1), radius=rs, fill=rgba)
        if top_light:
            d.rounded_rectangle((ps + S, ps + S, ps + ws - S, ps + int(hs * 0.5)),
                                radius=rs - S, outline=(255, 255, 255, 16), width=S)
        im = im.resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
        self._img_cache[ck] = ImageTk.PhotoImage(im)
        return self._img_cache[ck]

    def _btn_frames(self, key, w, h, color, radius, n=8):
        ck = ("bf", key, w, h)
        if ck in self._img_cache:
            return self._img_cache[ck]
        r, g, b = self._hex(color)
        frames = []
        for i in range(n):
            f = i / (n - 1)
            col = (min(255, int(r + 34 * f)), min(255, int(g + 26 * f)),
                   min(255, int(b + 34 * f)), 255)
            frames.append(self._flat(f"{key}#{i}", w, h, col, radius))
        self._img_cache[ck] = frames
        return frames

    # ── animation ─────────────────────────────────────────────────────
    def _tick(self):
        self.t += FPS_MS / 1000.0
        c = self.canvas

        if self._fading:
            frames, idx = self._fading
            if idx < len(frames):
                c.itemconfig(self._bg_item, image=frames[idx])
                self._fading = (frames, idx + 1)
            else:
                self._fading = None
                c.itemconfig(self._bg_item, image=self._bg_composed(GAMES[self.selected]))

        if hasattr(self, "_sel_logo_item"):
            base_y = self._sel_logo_y + math.sin(self.t * 2.2) * 4
            c.coords(self._sel_logo_item, SIDEBAR // 2 + 6, base_y)

        if hasattr(self, "_dot_item"):
            lbl, lcol = self._online_label(GAMES[self.selected])
            if lcol == "#5AE68C":   # en ligne : le point pulse
                bright = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.t * 4.5))
                g = int(0x5A + (0xFF - 0x5A) * bright * 0.4)
                lcol = f"#{int(0x2A * bright):02x}{g:02x}{int(0x55 + 0x30 * bright):02x}"
                c.itemconfig(self._dot_item, fill=lcol)
                c.itemconfig(self._online_item, text=lbl, fill="#5AE68C")
            else:
                c.itemconfig(self._dot_item, fill=lcol)
                c.itemconfig(self._online_item, text=lbl, fill=lcol)

        # hover JOUER : fondu
        if hasattr(self, "_play_item"):
            target = 1.0 if (self.hover == "play" and not self.busy) else 0.0
            self._play_anim = getattr(self, "_play_anim", 0.0)
            self._play_anim += (target - self._play_anim) * 0.28
            idx = round(self._play_anim * (len(self._play_frames) - 1))
            c.itemconfig(self._play_item, image=self._play_frames[idx])

        # curseur du champ pseudo (clignote quand focus)
        if hasattr(self, "_input_cursor"):
            if self.pseudo_focus and (int(self.t * 2.4) % 2 == 0):
                bbox = c.bbox(self._input_text)
                cxr = bbox[2] + 2 if bbox and self.pseudo_text else \
                    (self._input_zone[0] + self._input_zone[2]) // 2
                cyc = (self._input_zone[1] + self._input_zone[3]) // 2
                c.coords(self._input_cursor, cxr, cyc - 8, cxr + 2, cyc + 8)
            else:
                c.coords(self._input_cursor, 0, 0, 0, 0)

        # progression + statut
        if hasattr(self, "_bar_fill"):
            bx0, by0, bw, bh = self._bar_geom
            frac = max(0.0, min(1.0, self.progress_val.get() / 100.0))
            c.coords(self._bar_fill, bx0, by0, bx0 + bw * frac, by0 + bh)
            c.itemconfig(self._status_item, text=self.status.get())

        acc = GAMES[self.selected]["accent"]
        for i, p in enumerate(self.particles):
            p[1] -= p[2]
            p[0] += math.sin(self.t * 0.8 + i) * 0.18
            if p[1] < -4:
                p[0], p[1] = random.uniform(SIDEBAR, W), H + 4
                p[2] = random.uniform(0.25, 0.9)
            item = self._particle_items[i]
            c.coords(item, p[0], p[1], p[0] + p[3], p[1] + p[3])
            c.itemconfig(item, fill=acc if i % 3 == 0 else "#C8D8CC")

        self.after(FPS_MS, self._tick)

    def _online_label(self, g):
        """(texte, couleur) du statut serveur : joueurs en ligne / hors ligne."""
        if not g.get("server"):
            return self.T("online"), "#5AE68C"
        n = self._online.get(g["id"], "…")
        if n is None:
            return self.T("offline"), "#7A8A84"
        if n == "…":
            return self.T("online"), "#5AE68C"
        return f"{n} {self.T('players')}", "#5AE68C"

    # ── dessin ────────────────────────────────────────────────────────
    def _select(self, idx):
        if idx == self.selected or self.busy:
            return
        prev = GAMES[self.selected]
        self.selected = idx
        self._draw(fade_from=prev)

    def _draw(self, fade_from=None):
        c = self.canvas
        c.delete("all")
        g = GAMES[self.selected]
        accent = g["accent"]

        self._bg_item = c.create_image(0, 0, anchor="nw", image=self._bg_composed(g))
        if fade_from is not None:
            self._fading = (self._fade_frames(fade_from, g), 0)
            c.itemconfig(self._bg_item, image=self._bg_composed(fade_from))

        self._particle_items = [
            c.create_oval(p[0], p[1], p[0] + p[3], p[1] + p[3], fill="#C8D8CC", width=0)
            for p in self.particles
        ]

        # sidebar
        y = 60
        self._logo_zones = []
        for i, game in enumerate(GAMES):
            sel = i == self.selected
            hov = self.hover == ("logo", i)
            logo = self._load(game["logo"], size=(170, 120), dim=1.0 if sel else (0.72 if hov else 0.42))
            item = c.create_image(SIDEBAR // 2 + 6, y + 60, image=logo)
            if sel:
                self._sel_logo_item = item
                self._sel_logo_y = y + 60
                c.create_rectangle(6, y + 10, 9, y + 110, fill=accent, width=0)
            self._logo_zones.append((10, y, SIDEBAR, y + 120, i))
            y += 190

        studio_hov = self.hover == "studio"
        c.create_image(30, H - 30, image=self._load("assets/studio_icon.png", size=(26, 26),
                                                    dim=1.0 if studio_hov else 0.9))
        c.create_image(30 + 14 + 31, H - 30, image=self._load("assets/studio_wordmark.png",
                                                              size=(100, 20), dim=1.0 if studio_hov else 0.8))
        self._studio_zone = (14, H - 46, 14 + 130, H - 14)
        if studio_hov:
            self._draw_studio_tooltip(c)

        # ── sélecteur de langue (haut-droite)
        cur = next((l for l in LANGS if l[0] == self.lang), LANGS[0])
        lw, lh = 78, 30
        lx, ly = W - lw - 18, 16
        self._lang_zone = (lx, ly, lx + lw, ly + lh)
        lang_hov = self.hover == "lang"
        c.create_image(lx + lw // 2, ly + lh // 2,
                       image=self._flat("langbtn" + ("_h" if lang_hov else ""), lw, lh,
                                        (22, 30, 34, 235) if lang_hov else (14, 20, 23, 210), radius=12))
        c.create_text(lx + 20, ly + lh // 2, text=cur[2], font=(self.FONT, 13))
        c.create_text(lx + 40, ly + lh // 2, text=cur[0].upper(), fill="#DCE8E0", font=self.F(9, True))
        c.create_text(lx + lw - 14, ly + lh // 2, text="▾", fill="#7A948A", font=self.F(8))
        if self.lang_open:
            self._draw_lang_menu(c, lx, ly + lh + 6, lw)

        # ── bouton Journal (discret, à gauche du sélecteur de langue)
        jw = 30
        jx, jy = lx - jw - 8, ly
        self._log_zone = (jx, jy, jx + jw, jy + lh)
        jhov = self.hover == "logbtn"
        c.create_image(jx + jw // 2, jy + lh // 2,
                       image=self._flat("logbtn" + ("_h" if jhov else ""), jw, lh,
                                        (22, 30, 34, 235) if jhov else (14, 20, 23, 210), radius=12))
        c.create_text(jx + jw // 2, jy + lh // 2 - 1, text="▤",
                      fill=accent if jhov else "#7A948A", font=(self.FONT, 12))

        # ── news du jeu (catalogue distant → modifiable sans rebuild)
        news = GT(g, "news", self.lang, [])
        if news:
            news = news[:4]
            nw, nh = 350, 40 + 18 * len(news)
            nx, ny = SIDEBAR + 34, H - nh - 34
            c.create_image(nx + nw // 2, ny + nh // 2,
                           image=self._flat("news" + g["id"] + str(len(news)), nw, nh,
                                            (10, 15, 17, 205), radius=16))
            c.create_text(nx + 18, ny + 17, anchor="w", text=self.T("news"),
                          fill=accent, font=self.F(9, True))
            for i, line in enumerate(news):
                c.create_text(nx + 18, ny + 40 + i * 18, anchor="w", text="•  " + line,
                              fill="#C8DCD0", font=self.F(9))

        # ── colonne droite : carte info, pseudo, JOUER, progression
        cw = 280
        cx = W - cw - 34

        # carte info (verre)
        cy = H - 330
        card = self._flat("card", cw, 116, (14, 20, 24, 216), radius=16)
        c.create_image(cx + cw // 2, cy + 58, image=card)
        mini = self._load(g["logo"], size=(82, 54))
        c.create_image(cx + 52, cy + 34, image=mini)
        lbl, lcol = self._online_label(g)
        self._dot_item = c.create_oval(cx + 112, cy + 20, cx + 120, cy + 28, fill=lcol, width=0)
        self._online_item = c.create_text(cx + 128, cy + 24, anchor="w", text=lbl,
                                          fill=lcol, font=self.F(10, True))
        c.create_text(cx + 112, cy + 48, anchor="w", text=GT(g, "tagline", self.lang)[:44],
                      fill="#9AB0A4", font=self.F(8), width=156)
        bw2, bh2 = cw - 24, 32
        bx0, by0 = cx + 12, cy + 116 - bh2 - 12
        self._discord_zone = (bx0, by0, bx0 + bw2, by0 + bh2)
        self._discord_frames = self._btn_frames("discord", bw2, bh2, "#5865F2", 12)
        hovd = 1.0 if self.hover == "discord" else 0.0
        c.create_image(bx0 + bw2 // 2, by0 + bh2 // 2,
                       image=self._discord_frames[round(hovd * 7)])
        c.create_image(bx0 + 24, by0 + bh2 // 2, image=self._load("assets/discord_mark.png", size=(20, 15)))
        c.create_text(bx0 + bw2 // 2 + 8, by0 + bh2 // 2, text=self.T("discord"),
                      fill="white", font=self.F(10, True))

        # pseudo (pilule verre, champ dessiné à la main)
        iy = H - 164
        self._input_zone = (cx, iy - 19, cx + cw, iy + 19)
        c.create_image(cx + cw // 2, iy,
                       image=self._flat("input" + ("_f" if self.pseudo_focus else ""),
                                        cw, 38, (12, 18, 21, 255), radius=12))
        self._input_text = c.create_text(cx + cw // 2, iy, text=self.pseudo_text,
                                         fill="#EAF6EF", font=self.F(12, True))
        self._input_cursor = c.create_rectangle(0, 0, 0, 0, fill="#5AE68C", width=0)
        c.create_text(cx + cw // 2, iy - 30, text=self.T("pseudo"), fill="#7A948A", font=self.F(8, True))

        # JOUER + ⚙ options (séparées par jeu)
        ph2 = 54
        py0 = H - 129
        pw2 = cw - 62
        self._play_zone = (cx, py0, cx + pw2, py0 + ph2)
        self._play_frames = self._btn_frames("play:" + g["id"], pw2, ph2, accent, 12)
        self._play_item = c.create_image(cx + pw2 // 2, py0 + ph2 // 2, image=self._play_frames[0])
        label = self.T("cancel") if self.busy else self.T("play")
        c.create_text(cx + pw2 // 2, py0 + ph2 // 2, text=label,
                      fill="#06140C", font=self.F(13, True))
        gx = cx + cw - 54
        self._gear_zone = (gx, py0, gx + 54, py0 + ph2)
        gear_hov = self.hover == "gear"
        c.create_image(gx + 27, py0 + ph2 // 2,
                       image=self._flat("gear" + ("_h" if gear_hov else ""), 54, ph2,
                                        (28, 38, 34, 235) if gear_hov else (18, 26, 23, 220),
                                        radius=12))
        c.create_text(gx + 27, py0 + ph2 // 2, text="⚙", fill="#C8D8CC", font=(self.FONT, 19))

        if self.options_open:
            self._draw_options(c, g)
        if self.skin_open:
            self._draw_skin(c, g)
        if self.log_open:
            self._draw_log(c, g)

        # progression + statut
        bw3, bh3 = cw, 5
        by3 = H - 39
        self._bar_geom = (cx, by3, bw3, bh3)
        c.create_image(cx + cw // 2, by3 + bh3 // 2,
                       image=self._flat("track", bw3, bh3, (255, 255, 255, 26), radius=bh3 // 2))
        self._bar_fill = c.create_rectangle(cx, by3, cx, by3 + bh3, fill=accent, width=0)
        self._status_item = c.create_text(cx + cw // 2, by3 - 14, text=self.status.get(),
                                          fill="#C8D8CC", font=self.F(8), width=cw)

    # ── options par jeu ───────────────────────────────────────────────
    def _opts(self, g):
        return self._state().get("opt_" + g["id"], {"ram": 3, "close": False})

    def _set_opt(self, g, **kv):
        o = self._opts(g)
        o.update(kv)
        self._save_state(**{"opt_" + g["id"]: o})

    def _draw_lang_menu(self, c, mx, my, mw):
        """liste déroulante des 7 langues."""
        mw = 150
        rowh = 30
        mh = rowh * len(LANGS) + 10
        mx = W - mw - 18
        c.create_image(mx + mw // 2, my + mh // 2,
                       image=self._flat("langmenu", mw, mh, (16, 22, 26, 250), radius=12))
        self._lang_rows = []
        for i, (code, name, flag) in enumerate(LANGS):
            ry = my + 5 + i * rowh
            sel = code == self.lang
            hov = self.hover == ("lang", code)
            if sel or hov:
                c.create_image(mx + mw // 2, ry + rowh // 2,
                               image=self._flat("langrow" + code + ("s" if sel else "h"),
                                                mw - 10, rowh - 2,
                                                self._hex(GAMES[self.selected]["accent"]) + (40,) if sel
                                                else (255, 255, 255, 18), radius=8))
            c.create_text(mx + 22, ry + rowh // 2, text=flag, font=(self.FONT, 13))
            c.create_text(mx + 42, ry + rowh // 2, anchor="w", text=name,
                          fill="#EAF6EF" if (sel or hov) else "#B8C8BE", font=self.F(9, True))
            self._lang_rows.append((mx, ry, mx + mw, ry + rowh, code))

    def _draw_studio_tooltip(self, c):
        """bulle au survol du logo studio : rôle + bouton Voir le site."""
        tw, th = 236, 92
        tx, ty = 20, H - 46 - th - 10
        c.create_image(tx + tw // 2, ty + th // 2,
                       image=self._flat("stt", tw, th, (16, 22, 26, 248), radius=14))
        c.create_image(tx + 26, ty + 24, image=self._load("assets/studio_icon.png", size=(24, 24)))
        c.create_text(tx + 46, ty + 18, anchor="w", text="Studio Echelon",
                      fill="#EAF6EF", font=self.F(11, True))
        c.create_text(tx + 46, ty + 34, anchor="w", text=self.T("studio_role"),
                      fill="#9AB0A4", font=self.F(8))
        # bouton Voir le site
        bx0, by0, bw, bh = tx + 14, ty + th - 34, tw - 28, 24
        self._site_zone = (bx0, by0, bx0 + bw, by0 + bh)
        site_hov = self.hover == "studio_site"
        c.create_image(bx0 + bw // 2, by0 + bh // 2,
                       image=self._flat("stsite" + ("_h" if site_hov else ""), bw, bh,
                                        self._hex("#5AE68C") + (255,) if site_hov else (34, 46, 40, 255),
                                        radius=10))
        c.create_text(bx0 + bw // 2, by0 + bh // 2, text="🌐  " + self.T("see_site"),
                      fill="#06140C" if site_hov else "#DCE8E0", font=self.F(9, True))

    def _dim_overlay(self):
        if "dim" not in self._img_cache:
            self._img_cache["dim"] = ImageTk.PhotoImage(
                Image.new("RGBA", (W, H), (4, 7, 8, 165)))
        return self._img_cache["dim"]

    def _toggle(self, c, zone, on, accent):
        """switch iOS-like : rail + poucet, couleur accent quand actif."""
        zx = (zone[0] + zone[2]) // 2
        zy = (zone[1] + zone[3]) // 2
        c.create_image(zx, zy, image=self._flat("tg" + ("1" if on else "0") + accent, 50, 26,
                                                self._hex(accent) + (255,) if on else (44, 52, 49, 255),
                                                radius=13))
        kx = zone[2] - 15 if on else zone[0] + 15
        c.create_oval(kx - 9, zy - 9, kx + 9, zy + 9,
                      fill="#0C1512" if on else "#B8C8BE", width=0)

    def _draw_options(self, c, g):
        """panneau OPTIONS du jeu sélectionné : lignes propres + séparateurs."""
        o = self._opts(g)
        acc = g["accent"]
        pw, ph = 430, 372
        px, py = SIDEBAR + (W - SIDEBAR) // 2 - pw // 2, H // 2 - ph // 2
        c.create_image(0, 0, anchor="nw", image=self._dim_overlay())
        c.create_image(px + pw // 2, py + ph // 2,
                       image=self._flat("optpanel", pw, ph, (13, 18, 21, 248), radius=16))

        # en-tête : mini logo + titre
        c.create_image(px + 44, py + 40, image=self._load(g["logo"], size=(56, 38)))
        c.create_text(px + 82, py + 32, anchor="w", text=self.T("options"),
                      fill="#EAF6EF", font=self.F(14, True))
        c.create_text(px + 82, py + 52, anchor="w", text=self.T("opt_sub", n=g["name"]),
                      fill="#7A948A", font=self.F(8))

        rows_y = py + 92
        row_h = 52
        lx = px + 28
        rx = px + pw - 28

        def sep(y):
            c.create_rectangle(lx, y, rx, y + 1, fill="#1C2622", width=0)

        # ── RAM
        y0 = rows_y
        c.create_text(lx, y0 + 14, anchor="w", text=self.T("ram"),
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y0 + 30, anchor="w", text=self.T("ram_sub"),
                      fill="#6A7E74", font=self.F(8))
        self._ram_minus = (rx - 118, y0 + 8, rx - 88, y0 + 36)
        self._ram_plus = (rx - 30, y0 + 8, rx, y0 + 36)
        for zone, sign in ((self._ram_minus, "–"), (self._ram_plus, "+")):
            c.create_image((zone[0] + zone[2]) // 2, (zone[1] + zone[3]) // 2,
                           image=self._flat("step", 30, 28, (32, 42, 38, 255), radius=10))
            c.create_text((zone[0] + zone[2]) // 2, (zone[1] + zone[3]) // 2 - 1, text=sign,
                          fill=acc, font=self.F(13, True))
        c.create_text(rx - 59, y0 + 22, text=f"{o.get('ram', 3)} Go",
                      fill="#EAF6EF", font=self.F(11, True))
        sep(y0 + row_h - 6)

        # ── Rich Presence
        y1 = rows_y + row_h
        c.create_text(lx, y1 + 14, anchor="w", text=self.T("rpc"),
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y1 + 30, anchor="w", text=self.T("rpc_sub"),
                      fill="#6A7E74", font=self.F(8), width=pw - 140)
        self._rpc_zone = (rx - 50, y1 + 9, rx, y1 + 35)
        self._toggle(c, self._rpc_zone, o.get("rpc", True), acc)
        sep(y1 + row_h - 6)

        # ── fermeture auto
        y2 = rows_y + row_h * 2
        c.create_text(lx, y2 + 14, anchor="w", text=self.T("close"),
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y2 + 30, anchor="w", text=self.T("close_sub"),
                      fill="#6A7E74", font=self.F(8), width=pw - 140)
        self._close_zone = (rx - 50, y2 + 9, rx, y2 + 35)
        self._toggle(c, self._close_zone, o.get("close", False), acc)
        sep(y2 + row_h - 6)

        # ── dossier du jeu
        y3 = rows_y + row_h * 3
        c.create_text(lx, y3 + 14, anchor="w", text=self.T("folder"),
                      fill="#DCE8E0", font=self.F(10, True))
        path = g["dir"]
        if len(path) > 34:
            path = "…" + path[-33:]
        c.create_text(lx, y3 + 30, anchor="w", text=path,
                      fill="#6A7E74", font=self.F(7), width=pw - 160)
        self._folder_zone = (rx - 92, y3 + 8, rx, y3 + 36)
        c.create_image((rx - 92 + rx) // 2, y3 + 22,
                       image=self._flat("folder", 92, 28, (32, 42, 38, 255), radius=10))
        c.create_text((rx - 92 + rx) // 2, y3 + 22, text=self.T("open"),
                      fill="#DCE8E0", font=self.F(9, True))

        # ── skin
        y4 = rows_y + row_h * 4
        c.create_text(lx, y4 + 14, anchor="w", text=self.T("skin"),
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y4 + 30, anchor="w", text=self.T("skin_sub"),
                      fill="#6A7E74", font=self.F(8))
        self._optskin_zone = (rx - 100, y4 + 8, rx, y4 + 36)
        c.create_image((rx - 100 + rx) // 2, y4 + 22,
                       image=self._flat("optskin", 100, 28, (32, 42, 38, 255), radius=10))
        c.create_text((rx - 100 + rx) // 2, y4 + 22, text=self.T("change"),
                      fill="#DCE8E0", font=self.F(9, True))

        # ── fermer (accent)
        self._optclose_zone = (px + pw // 2 - 74, py + ph - 58, px + pw // 2 + 74, py + ph - 24)
        c.create_image(px + pw // 2, py + ph - 41,
                       image=self._flat("optclose" + g["id"], 148, 34,
                                        self._hex(acc) + (255,), radius=12))
        c.create_text(px + pw // 2, py + ph - 41, text=self.T("done"),
                      fill="#06140C", font=self.F(10, True))

    # ── skins : partagé entre les jeux (StudioEchelon/skin.png) ───────
    def _skin_path(self):
        return os.path.join(game_root("StudioEchelon"), "skin.png")

    def _skin_meta(self):
        try:
            return json.load(open(self._skin_path() + ".json"))
        except Exception:
            return {}

    def _fetch_skin(self, name):
        """récupère le skin d'un compte premium via l'API Mojang."""
        import urllib.request, base64
        try:
            req = urllib.request.Request(
                "https://api.mojang.com/users/profiles/minecraft/" + name,
                headers={"User-Agent": "echelon-client"})
            uid = json.load(urllib.request.urlopen(req, timeout=8))["id"]
            req = urllib.request.Request(
                "https://sessionserver.mojang.com/session/minecraft/profile/" + uid,
                headers={"User-Agent": "echelon-client"})
            prof = json.load(urllib.request.urlopen(req, timeout=8))
            tex = json.loads(base64.b64decode(prof["properties"][0]["value"]))["textures"]
            url = tex["SKIN"]["url"]
            slim = tex["SKIN"].get("metadata", {}).get("model") == "slim"
            req = urllib.request.Request(url, headers={"User-Agent": "echelon-client"})
            data = urllib.request.urlopen(req, timeout=15).read()
            self._set_skin(data, slim)
            self.skin_status = self.T("skin_ok")
            logging.info("skin importé depuis %s (slim=%s)", name, slim)
        except Exception:
            self.skin_status = self.T("skin_err")
        self.after(0, self._draw)

    def _set_skin(self, png_bytes, slim):
        import io
        im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        if im.size == (64, 32):   # vieux format → conversion 64x64
            new = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            new.paste(im, (0, 0))
            im = new
        if im.size != (64, 64):
            raise ValueError("format de skin invalide")
        im.save(self._skin_path())
        json.dump({"slim": bool(slim)}, open(self._skin_path() + ".json", "w"))
        # invalide la préview en cache
        self._img_cache = {k: v for k, v in self._img_cache.items()
                           if not (isinstance(k, tuple) and k[0] == "skinprev")}

    def _pick_skin_file(self):
        from tkinter import filedialog
        f = filedialog.askopenfilename(title="Skin Minecraft (PNG 64x64)",
                                       filetypes=[("PNG", "*.png")])
        if not f:
            return
        try:
            self._set_skin(open(f, "rb").read(), False)
            self.skin_status = self.T("skin_ok")
        except Exception:
            self.skin_status = self.T("skin_err")
        self._draw()

    def _skin_preview(self, scale=6):
        """rendu 2D de face (tête+torse+bras+jambes, calques chapeau inclus)."""
        try:
            mtime = int(os.path.getmtime(self._skin_path()))
        except Exception:
            return None
        key = ("skinprev", mtime, scale)
        if key in self._img_cache:
            return self._img_cache[key]
        sk = Image.open(self._skin_path()).convert("RGBA")
        out = Image.new("RGBA", (16, 32), (0, 0, 0, 0))
        out.paste(sk.crop((8, 8, 16, 16)), (4, 0))                    # tête
        hat = sk.crop((40, 8, 48, 16))
        out.paste(hat, (4, 0), hat)                                   # chapeau
        out.paste(sk.crop((20, 20, 28, 32)), (4, 8))                  # torse
        out.paste(sk.crop((44, 20, 48, 32)), (0, 8))                  # bras D
        out.paste(sk.crop((36, 52, 40, 64)), (12, 8))                 # bras G
        out.paste(sk.crop((4, 20, 8, 32)), (4, 20))                   # jambe D
        out.paste(sk.crop((20, 52, 24, 64)), (8, 20))                 # jambe G
        out = out.resize((16 * scale, 32 * scale), Image.NEAREST)
        self._img_cache[key] = ImageTk.PhotoImage(out)
        return self._img_cache[key]

    def _draw_skin(self, c, g):
        """panneau SKIN : préview + import premium + fichier."""
        acc = g["accent"]
        pw, ph = 440, 330
        px, py = SIDEBAR + (W - SIDEBAR) // 2 - pw // 2, H // 2 - ph // 2
        c.create_image(0, 0, anchor="nw", image=self._dim_overlay())
        c.create_image(px + pw // 2, py + ph // 2,
                       image=self._flat("skinpanel", pw, ph, (13, 18, 21, 248), radius=16))
        c.create_text(px + 26, py + 30, anchor="w", text=self.T("skin"),
                      fill="#EAF6EF", font=self.F(13, True))
        c.create_text(px + 26, py + 50, anchor="w", text=self.T("skin_sub"),
                      fill="#7A948A", font=self.F(8))

        # préview à gauche
        prev = self._skin_preview()
        if prev:
            c.create_image(px + 88, py + 178, image=prev)
        else:
            c.create_text(px + 88, py + 178, text=self.T("skin_none"),
                          fill="#6A7E74", font=self.F(8), width=110)

        # import premium
        rx0 = px + 176
        c.create_text(rx0, py + 92, anchor="w", text=self.T("skin_premium"),
                      fill="#C8D8CC", font=self.F(9, True))
        iw2 = pw - (rx0 - px) - 26
        self._skin_input_zone = (rx0, py + 108, rx0 + iw2, py + 144)
        c.create_image(rx0 + iw2 // 2, py + 126,
                       image=self._flat("skininput", iw2, 36, (10, 15, 17, 255), radius=12))
        self._skin_input_item = c.create_text(rx0 + iw2 // 2, py + 126,
                                              text=self.skin_input or ("|" if self.skin_focus else "Notch"),
                                              fill="#EAF6EF" if self.skin_input else "#4A5E54",
                                              font=self.F(11, True))
        self._skin_import_zone = (rx0, py + 156, rx0 + iw2, py + 192)
        c.create_image(rx0 + iw2 // 2, py + 174,
                       image=self._flat("skinimp" + g["id"], iw2, 36, self._hex(acc) + (255,), radius=12))
        c.create_text(rx0 + iw2 // 2, py + 174, text=self.T("import"),
                      fill="#06140C", font=self.F(10, True))

        # fichier local
        self._skin_file_zone = (rx0, py + 204, rx0 + iw2, py + 240)
        c.create_image(rx0 + iw2 // 2, py + 222,
                       image=self._flat("skinfile", iw2, 36, (32, 42, 38, 255), radius=12))
        c.create_text(rx0 + iw2 // 2, py + 222, text=self.T("skin_file"),
                      fill="#DCE8E0", font=self.F(9, True))

        if self.skin_status:
            c.create_text(rx0 + iw2 // 2, py + 258, text=self.skin_status,
                          fill=acc, font=self.F(9))

        self._skinclose_zone = (px + pw // 2 - 74, py + ph - 56, px + pw // 2 + 74, py + ph - 22)
        c.create_image(px + pw // 2, py + ph - 39,
                       image=self._flat("skinclose" + g["id"], 148, 34, self._hex(acc) + (255,), radius=12))
        c.create_text(px + pw // 2, py + ph - 39, text=self.T("done"),
                      fill="#06140C", font=self.F(10, True))

    # ── page Journal (sortie du jeu) ──────────────────────────────────
    LOG_LH = 14          # hauteur d'une ligne
    LOG_MAXC = 108       # troncature horizontale (pas de scroll latéral)

    @staticmethod
    def _log_lines():
        """copie de la deque : elle est alimentée par le thread de lecture."""
        return list(GAME_LOG)

    @staticmethod
    def _log_color(line):
        u = line.upper()
        if "ERROR" in u or "EXCEPTION" in u or "FATAL" in u or "SEVERE" in u:
            return "#E8908C"
        if "WARN" in u:
            return "#E6C079"
        return "#A8B8B0"

    def _log_dir(self, g):
        return os.path.join(g["dir"], "logs")

    def _mod_version(self, g):
        channel = g["base"].rsplit("/", 1)[1]
        return self._state().get("mod_" + channel) or self.T("log_unknown")

    def _open_path(self, path):
        """ouvre un dossier dans l'explorateur (sans rouvrir de console Windows)."""
        try:
            os.makedirs(path, exist_ok=True)
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", path], creationflags=0x08000000)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _draw_log(self, c, g):
        """console du jeu : en-tête diagnostic + lignes colorées + actions."""
        acc = g["accent"]
        pw, ph = 760, 520
        px, py = SIDEBAR + (W - SIDEBAR) // 2 - pw // 2, H // 2 - ph // 2
        c.create_image(0, 0, anchor="nw", image=self._dim_overlay())
        c.create_image(px + pw // 2, py + ph // 2,
                       image=self._flat("logpanel", pw, ph, (13, 18, 21, 248), radius=16))

        c.create_text(px + 26, py + 28, anchor="w", text=self.T("log"),
                      fill="#EAF6EF", font=self.F(13, True))
        c.create_text(px + 26, py + 48, anchor="w", text=self.T("log_sub"),
                      fill="#7A948A", font=self.F(8))

        # en-tête diagnostic : mod, dossier, java
        java = self._java_path or self.T("log_unknown")
        if len(java) > 62:
            java = "…" + java[-61:]
        folder = g["dir"]
        if len(folder) > 62:
            folder = "…" + folder[-61:]
        infos = [f"{g['name']} · {self.T('log_mod')} {self._mod_version(g)}",
                 f"{self.T('folder')} : {folder}",
                 f"{self.T('log_java')} : {java}"]
        for i, line in enumerate(infos):
            c.create_text(px + 26, py + 72 + i * 14, anchor="w", text=line,
                          fill="#6A7E74", font=self.F(8))

        # zone console
        lx, ly = px + 22, py + 122
        lw, lh = pw - 44, ph - 122 - 68
        self._log_area = (lx, ly, lw, lh)
        c.create_image(lx + lw // 2, ly + lh // 2,
                       image=self._flat("logbox", lw, lh, (7, 11, 13, 255), radius=12))

        lines = self._log_lines()
        self._log_items = []
        if lines:
            n = max(1, (lh - 14) // self.LOG_LH)
            for i in range(n):
                self._log_items.append(
                    c.create_text(lx + 12, ly + 12 + i * self.LOG_LH, anchor="nw", text="",
                                  fill="#A8B8B0", font=("Courier New", 9)))
            self._log_thumb = c.create_rectangle(0, 0, 0, 0, fill="#2E3E38", width=0)
            self._log_render()
        else:
            self._log_thumb = c.create_rectangle(0, 0, 0, 0, fill="", width=0)
            c.create_text(lx + lw // 2, ly + lh // 2 - 10, text=self.T("log_empty"),
                          fill="#7A948A", font=self.F(10, True))
            if os.path.exists(os.path.join(self._log_dir(g), "launcher-game.log")):
                c.create_text(lx + lw // 2, ly + lh // 2 + 14, text=self.T("log_prev"),
                              fill="#5A6E64", font=self.F(8), width=lw - 60, justify="center")

        # actions
        by = py + ph - 50
        self._logcopy_zone = (px + 22, by, px + 22 + 120, by + 32)
        c.create_image(px + 22 + 60, by + 16,
                       image=self._flat("logcopy", 120, 32, (32, 42, 38, 255), radius=10))
        c.create_text(px + 22 + 60, by + 16, text=self.T("log_copy"),
                      fill="#DCE8E0", font=self.F(9, True))

        self._logfolder_zone = (px + 154, by, px + 154 + 180, by + 32)
        c.create_image(px + 154 + 90, by + 16,
                       image=self._flat("logfolder", 180, 32, (32, 42, 38, 255), radius=10))
        c.create_text(px + 154 + 90, by + 16, text=self.T("log_folder"),
                      fill="#DCE8E0", font=self.F(9, True))

        if self.log_status:
            c.create_text(px + 352, by + 16, anchor="w", text=self.log_status,
                          fill=acc, font=self.F(9))

        self._logclose_zone = (px + pw - 150, by, px + pw - 22, by + 32)
        c.create_image(px + pw - 86, by + 16,
                       image=self._flat("logclose" + g["id"], 128, 32,
                                        self._hex(acc) + (255,), radius=10))
        c.create_text(px + pw - 86, by + 16, text=self.T("done"),
                      fill="#06140C", font=self.F(10, True))

    def _log_render(self):
        """remplit les items texte avec la tranche visible (appelé aussi par le tick)."""
        if not self._log_items:
            return
        c = self.canvas
        lines = self._log_lines()
        total, vis = len(lines), len(self._log_items)
        self.log_off = max(0, min(self.log_off, max(0, total - vis)))
        end = total - self.log_off
        start = max(0, end - vis)
        chunk = lines[start:end]
        for i, item in enumerate(self._log_items):
            if i < len(chunk):
                txt = chunk[i][:self.LOG_MAXC]
                c.itemconfig(item, text=txt, fill=self._log_color(chunk[i]))
            else:
                c.itemconfig(item, text="")
        # ascenseur : simple repère de position
        lx, ly, lw, lh = self._log_area
        if total > vis:
            frac = vis / total
            th = max(24, int((lh - 16) * frac))
            pos = 0 if total == vis else (start / max(1, total - vis))
            ty = ly + 8 + int((lh - 16 - th) * pos)
            c.coords(self._log_thumb, lx + lw - 10, ty, lx + lw - 6, ty + th)
        else:
            c.coords(self._log_thumb, 0, 0, 0, 0)

    def _log_tick(self):
        """rafraîchit la console pendant que le jeu tourne (arrêt à la fermeture)."""
        if not self.log_open:
            self._log_job = None
            return
        try:
            self._log_render()
        except Exception:
            pass
        self._log_job = self.after(250, self._log_tick)

    def _log_show(self):
        self.log_open = True
        self.log_off = 0
        self.log_status = ""
        self._draw()
        if self._log_job is None:
            self._log_job = self.after(250, self._log_tick)

    def _log_hide(self):
        self.log_open = False
        self._log_items = []
        if self._log_job is not None:
            try:
                self.after_cancel(self._log_job)
            except Exception:
                pass
            self._log_job = None
        self._draw()

    def _log_scroll_by(self, lines):
        if not self.log_open or not self._log_items:
            return
        self.log_off = max(0, self.log_off + lines)
        self._log_render()

    def _log_wheel(self, e):
        if not self.log_open:
            return
        if getattr(e, "num", None) == 4:
            step = 3
        elif getattr(e, "num", None) == 5:
            step = -3
        else:
            step = 3 if e.delta > 0 else -3
        self._log_scroll_by(step)

    def _log_drag(self, e):
        """glissement dans la console ; sinon on retombe sur le survol normal."""
        if not self.log_open:
            self._motion(e)
            return
        if self._log_drag_y is None:
            self._log_drag_y = e.y
            return
        dy = e.y - self._log_drag_y
        if abs(dy) >= self.LOG_LH:
            self._log_scroll_by(int(dy / self.LOG_LH))
            self._log_drag_y = e.y

    def _log_drag_end(self, _e):
        self._log_drag_y = None

    def _log_copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append("\n".join(self._log_lines()))
            self.log_status = self.T("log_copied")
        except Exception:
            self.log_status = ""

    # ── interactions ──────────────────────────────────────────────────
    def _hit(self, zone, x, y):
        return zone[0] <= x <= zone[2] and zone[1] <= y <= zone[3]

    # caractères valides d'un pseudo Minecraft : lettres, chiffres, underscore
    _PSEUDO_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")

    def _key(self, e):
        """saisie du pseudo, gérée à la main (champ canvas). Sauvegarde en direct."""
        if self.log_open:
            if e.keysym == "Escape":
                self._log_hide()
            elif e.keysym in ("Prior", "Next", "Up", "Down"):
                self._log_scroll_by({"Prior": 10, "Up": 1, "Next": -10, "Down": -1}[e.keysym])
            return
        if self.skin_open and self.skin_focus:
            if e.keysym == "BackSpace":
                self.skin_input = self.skin_input[:-1]
            elif e.keysym in ("Return",):
                if self.skin_input.strip():
                    self.skin_status = "…"
                    threading.Thread(target=self._fetch_skin,
                                     args=(self.skin_input.strip(),), daemon=True).start()
            elif e.keysym == "underscore" and len(self.skin_input) < 16:
                self.skin_input += "_"
            elif e.char and e.char in self._PSEUDO_OK and len(self.skin_input) < 16:
                self.skin_input += e.char
            self.canvas.itemconfig(self._skin_input_item, text=self.skin_input or "|",
                                   fill="#EAF6EF" if self.skin_input else "#4A5E54")
            return
        if not self.pseudo_focus:
            return
        if e.keysym == "BackSpace":
            self.pseudo_text = self.pseudo_text[:-1]
        elif e.keysym in ("Return", "Escape", "Tab"):
            self.pseudo_focus = False
        elif e.keysym == "underscore" and len(self.pseudo_text) < 16:
            self.pseudo_text += "_"
        elif e.char and e.char in self._PSEUDO_OK and len(self.pseudo_text) < 16:
            self.pseudo_text += e.char
        self.canvas.itemconfig(self._input_text, text=self.pseudo_text)
        if self.pseudo_text.strip():
            self._save_state(pseudo=self.pseudo_text)   # sauvegardé à chaque frappe

    def _click(self, e):
        g = GAMES[self.selected]
        if self.lang_open:   # menu langue ouvert : capte tout
            picked = None
            for (x0, y0, x1, y1, code) in getattr(self, "_lang_rows", []):
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    picked = code
                    break
            if picked:
                self.lang = picked
                self._save_state(lang=picked)
            self.lang_open = False
            self._draw()
            return
        if self._hit(self._lang_zone, e.x, e.y):
            self.lang_open = True
            self._draw()
            return
        if hasattr(self, "_log_zone") and self._hit(self._log_zone, e.x, e.y):
            self._log_show()
            return
        if self.log_open:   # modal : la page Journal capte tout
            if self._hit(self._logcopy_zone, e.x, e.y):
                self._log_copy()
                self._draw()
            elif self._hit(self._logfolder_zone, e.x, e.y):
                self._open_path(self._log_dir(g))
            elif self._hit(self._logclose_zone, e.x, e.y):
                self._log_hide()
            return
        if self.options_open:   # modal : tout passe par le panneau
            if self._hit(self._ram_minus, e.x, e.y):
                self._set_opt(g, ram=max(2, self._opts(g).get("ram", 3) - 1))
            elif self._hit(self._ram_plus, e.x, e.y):
                self._set_opt(g, ram=min(8, self._opts(g).get("ram", 3) + 1))
            elif self._hit(self._rpc_zone, e.x, e.y):
                self._set_opt(g, rpc=not self._opts(g).get("rpc", True))
            elif self._hit(self._close_zone, e.x, e.y):
                self._set_opt(g, close=not self._opts(g).get("close", False))
            elif self._hit(self._folder_zone, e.x, e.y):
                os.makedirs(g["dir"], exist_ok=True)
                if platform.system() == "Windows":
                    os.startfile(g["dir"])
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", g["dir"]])
                else:
                    subprocess.Popen(["xdg-open", g["dir"]])
            elif self._hit(self._optskin_zone, e.x, e.y):
                self.options_open = False
                self.skin_open = True
                self.skin_status = ""
            elif self._hit(self._optclose_zone, e.x, e.y):
                self.options_open = False
            self._draw()
            return
        for (x0, y0, x1, y1, i) in self._logo_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._select(i)
                return
        was_focus = self.pseudo_focus
        self.pseudo_focus = self._hit(self._input_zone, e.x, e.y)
        if self.pseudo_focus != was_focus and not self.pseudo_focus:
            self.canvas.itemconfig(self._input_text, text=self.pseudo_text)
        if self.pseudo_focus:
            return
        if self._hit(self._play_zone, e.x, e.y):
            if self.busy:
                self._cancel = True   # annulation demandée
            else:
                self._play()
        elif self._hit(self._gear_zone, e.x, e.y):
            self.options_open = True
            self._draw()
        elif self._hit(self._discord_zone, e.x, e.y):
            webbrowser.open(GAMES[self.selected]["discord"])
        elif hasattr(self, "_site_zone") and self.hover == "studio_site" \
                and self._hit(self._site_zone, e.x, e.y):
            webbrowser.open("https://studioechelon.fr")

    def _motion(self, e):
        prev = self.hover
        self.hover = None
        if self.log_open:   # page Journal : curseur seulement, pas de redraw
            self.hover = prev
            over = any(self._hit(z, e.x, e.y) for z in
                       (self._logcopy_zone, self._logfolder_zone, self._logclose_zone))
            self.configure(cursor="hand2" if over else "")
            return
        if self.lang_open:   # menu langue : hover des lignes
            for (x0, y0, x1, y1, code) in getattr(self, "_lang_rows", []):
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    self.hover = ("lang", code)
                    break
            if not self._hit(self._lang_zone, e.x, e.y):
                pass
            self.configure(cursor="hand2" if self.hover else "")
            if prev != self.hover:
                self._draw()
            return
        # le bouton du site a priorité (le tooltip est ouvert dessus)
        if hasattr(self, "_site_zone") and isinstance(prev, str) and prev.startswith("studio") \
                and self._hit(self._site_zone, e.x, e.y):
            self.hover = "studio_site"
        elif self._hit(self._play_zone, e.x, e.y):
            self.hover = "play"
        elif self._hit(self._gear_zone, e.x, e.y):
            self.hover = "gear"
        elif self._hit(self._lang_zone, e.x, e.y):
            self.hover = "lang"
        elif hasattr(self, "_log_zone") and self._hit(self._log_zone, e.x, e.y):
            self.hover = "logbtn"
        elif self._hit(self._discord_zone, e.x, e.y):
            self.hover = "discord"
        elif self._hit(self._studio_zone, e.x, e.y) \
                or (isinstance(prev, str) and prev.startswith("studio")
                    and hasattr(self, "_site_zone")
                    and self._hit((self._studio_zone[0], self._site_zone[1] - 12,
                                   self._site_zone[2], self._studio_zone[3]), e.x, e.y)):
            self.hover = "studio"
        else:
            for (x0, y0, x1, y1, i) in self._logo_zones:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    self.hover = ("logo", i)
                    break
        self.configure(cursor="hand2" if self.hover else "")
        # les logos + discord + studio changent d'état par redraw
        if prev != self.hover and self._fading is None \
                and (isinstance(prev, tuple) or isinstance(self.hover, tuple)
                     or (isinstance(prev, str) and prev.startswith("studio"))
                     or (isinstance(self.hover, str) and self.hover.startswith("studio"))
                     or "discord" in (prev, self.hover) or "gear" in (prev, self.hover)
                     or "lang" in (prev, self.hover) or "logbtn" in (prev, self.hover)):
            self._draw()

    # ── persistance ───────────────────────────────────────────────────
    def _cfg(self):
        return os.path.join(game_root("StudioEchelon"), "client.json")

    def _state(self):
        try:
            return json.load(open(self._cfg()))
        except Exception:
            return {}

    def _save_state(self, **kv):
        os.makedirs(os.path.dirname(self._cfg()), exist_ok=True)
        st = self._state()
        st.update(kv)
        json.dump(st, open(self._cfg(), "w"))

    def _load_pseudo(self):
        return self._state().get("pseudo", "Joueur")

    # ── installation + lancement intégrés ─────────────────────────────
    def _callbacks(self):
        state = {"max": 100}
        return {
            "setStatus": lambda s: self.status.set(s),
            "setProgress": lambda v: self.progress_val.set(v / max(1, state["max"]) * 100),
            "setMax": lambda m: state.update(max=m),
        }

    def _play(self):
        if self.busy:
            return
        if mll is None:
            self.status.set("minecraft-launcher-lib manquant (pip install)")
            return
        self.busy = True
        self._draw()
        threading.Thread(target=self._play_thread, args=(GAMES[self.selected],), daemon=True).start()

    def _play_thread(self, g):
        try:
            self._cancel = False
            pseudo = (self.pseudo_text.strip() or "Joueur")[:16]
            self._save_state(pseudo=pseudo)
            os.makedirs(g["dir"], exist_ok=True)
            logging.info("JOUER %s (pseudo=%s)", g["id"], pseudo)

            self.status.set(self.T("installing_mc", v=MC_VERSION))
            mll.fabric.install_fabric(MC_VERSION, g["dir"], callback=self._callbacks())
            self._check_cancel()
            fabric_version = None
            for v in mll.utils.get_installed_versions(g["dir"]):
                if "fabric" in v["id"] and MC_VERSION in v["id"]:
                    fabric_version = v["id"]
            if not fabric_version:
                raise RuntimeError("Fabric introuvable après installation")

            # Java PARTAGÉ entre les jeux : téléchargé une seule fois
            java = None
            try:
                jroot = game_root("StudioEchelon")
                java = mll.runtime.get_executable_path(JAVA_RUNTIME, jroot)
                if java is None:
                    self.status.set(self.T("installing_java"))
                    mll.runtime.install_jvm_runtime(JAVA_RUNTIME, jroot, callback=self._callbacks())
                    java = mll.runtime.get_executable_path(JAVA_RUNTIME, jroot)
            except Exception:
                java = None
            self._java_path = java or "system PATH"
            self._check_cancel()

            mods = os.path.join(g["dir"], "mods")
            os.makedirs(mods, exist_ok=True)
            self._sync_mod(g, mods)
            self._ensure_deps(g, mods)

            # options lues par le mod en jeu (Rich Presence…)
            cfg_dir = os.path.join(g["dir"], "config")
            os.makedirs(cfg_dir, exist_ok=True)
            json.dump({"rich_presence": self._opts(g).get("rpc", True)},
                      open(os.path.join(cfg_dir, "echelon-launcher.json"), "w"))
            sp = self._skin_path()
            if os.path.exists(sp):
                shutil.copy(sp, os.path.join(cfg_dir, "echelon-skin.png"))
                meta = self._skin_meta()
                json.dump(meta, open(os.path.join(cfg_dir, "echelon-skin.json"), "w"))

            self.status.set(self.T("launching", n=g["name"]))
            o = self._opts(g)
            options = {
                "username": pseudo,
                "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, g["seed"] + pseudo)),
                "token": "0",
                "jvmArguments": [f"-Xmx{o.get('ram', 3)}G"],
            }
            if java:
                options["executablePath"] = java
            cmd = mll.command.get_minecraft_command(fabric_version, g["dir"], options)
            self.progress_val.set(100)
            self.status.set(self.T("have_fun"))
            launch_game(cmd, g["dir"])
            logging.info("lancé %s", g["id"])
            if o.get("close", False):
                self.after(1500, self.destroy)
        except Hub._Cancelled:
            self.progress_val.set(0)
            self.status.set(self.T("cancelled"))
            logging.info("annulé par l'utilisateur")
        except Exception as e:
            import traceback
            logging.error("échec lancement %s\n%s", g["id"], traceback.format_exc())
            self.status.set(f"Erreur : {e}")
        finally:
            self.busy = False
            self.after(0, self._draw)

    class _Cancelled(Exception):
        pass

    def _check_cancel(self):
        if self._cancel:
            raise Hub._Cancelled()

    def _download(self, url, dest, label=""):
        """téléchargement par blocs : barre de progression VIVANTE + annulable."""
        import urllib.request
        self._check_cancel()
        if label:
            self.status.set(self.T("downloading", n=label))
        req = urllib.request.Request(url, headers={"User-Agent": "echelon-client"})
        tmp = dest + ".part"
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                self._check_cancel()
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    self.progress_val.set(done / total * 100)
        os.replace(tmp, dest)
        logging.info("téléchargé %s (%d octets)", url, os.path.getsize(dest))

    def _sync_channel(self, channel, mod_file, label, mods, required):
        """synchronise un canal GitHub (manifest + jar, sha256 vérifié)."""
        import urllib.request, hashlib
        base = RELEASES + "/" + channel
        target = os.path.join(mods, mod_file)
        manifest = None
        try:
            req = urllib.request.Request(base + "/manifest.json",
                                         headers={"User-Agent": "echelon-client"})
            manifest = json.load(urllib.request.urlopen(req, timeout=8))
        except Exception:
            pass
        if manifest:
            want = manifest.get("mod_version", "")
            have = self._state().get("mod_" + channel, "")
            if want != have or not os.path.exists(target):
                logging.info("maj %s : %s -> %s", channel, have, want)
                self._download(base + "/" + manifest.get("mod_file", mod_file),
                               target + ".new", label=f"{label} {want}")
                sha = hashlib.sha256(open(target + ".new", "rb").read()).hexdigest()
                if manifest.get("mod_sha256") and sha != manifest["mod_sha256"]:
                    os.remove(target + ".new")
                    raise RuntimeError("Fichier corrompu (sha256) — réessaie.")
                shutil.move(target + ".new", target)
                self._save_state(**{"mod_" + channel: want})
        elif required and not os.path.exists(target):
            raise RuntimeError("Pas de connexion pour télécharger le jeu.")

    def _sync_mod(self, g, mods):
        """mod principal + mods annexes (EchelonSkin…) du jeu."""
        self._sync_channel(g["base"].rsplit("/", 1)[1], g["mod_file"], g["name"], mods, True)
        for ex in g.get("extra", []):
            self._check_cancel()
            self._sync_channel(ex["channel"], ex["file"], ex["channel"], mods, False)

    def _ensure_deps(self, g, mods):
        import urllib.request
        for f in os.listdir(mods):
            if any(f.startswith(p) for p in g["purge"]):
                logging.info("purge %s", f)
                os.remove(os.path.join(mods, f))
        for prefix, project in g["deps"].items():
            self._check_cancel()
            if any(f.startswith(prefix) for f in os.listdir(mods)):
                continue
            api = ("https://api.modrinth.com/v2/project/" + project
                   + "/version?game_versions=[%22" + MC_VERSION + "%22]&loaders=[%22fabric%22]")
            req = urllib.request.Request(api, headers={"User-Agent": "echelon-client"})
            versions = json.load(urllib.request.urlopen(req))
            f0 = versions[0]["files"][0]
            self._download(f0["url"], os.path.join(mods, f0["filename"]), label=project)


if __name__ == "__main__":
    setup_log()
    Hub().mainloop()
