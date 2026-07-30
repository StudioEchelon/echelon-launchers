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

# `launch_game` protégeait le jeu, mais l'INSTALLATION passait par
# minecraft_launcher_lib, qui lance l'installeur Fabric via `java` : chacun de
# ces sous-process ouvrait sa propre console noire — c'est ce qui donnait
# l'impression d'un truc de hackeur au joueur. On force le drapeau au niveau de
# subprocess : plus rien, jamais, ne peut faire clignoter un terminal.
if os.name == "nt":
    CREATE_NO_WINDOW = 0x08000000
    _popen_init = subprocess.Popen.__init__

    def _popen_no_window(self, *args, **kwargs):
        kwargs["creationflags"] = (kwargs.get("creationflags") or 0) | CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _popen_no_window


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

W, H = 1280, 760
SIDEBAR = 210
FPS_MS = 40
MC_VERSION = "1.21.1"
JAVA_RUNTIME = "java-runtime-delta"
RELEASES = "https://github.com/StudioEchelon/echelon-launchers/releases/download"
BG = "#0A0C0E"
FADE_STEPS = 7
CLIENT_VERSION = "1.9"
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
    "members": {"fr": "membres", "en": "members", "es": "miembros", "de": "Mitglieder",
                "pt": "membros", "it": "membri", "ru": "участников"},
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
    # ── coquille v2 : sections du rail + pages ────────────────────────
    "nav_home": {"fr": "ACCUEIL", "en": "HOME", "es": "INICIO", "de": "START",
                 "pt": "INÍCIO", "it": "HOME", "ru": "ГЛАВНАЯ"},
    "nav_library": {"fr": "BIBLIOTHÈQUE", "en": "LIBRARY", "es": "BIBLIOTECA",
                    "de": "BIBLIOTHEK", "pt": "BIBLIOTECA", "it": "LIBRERIA",
                    "ru": "БИБЛИОТЕКА"},
    "nav_news": {"fr": "NOUVEAUTÉS", "en": "NEWS", "es": "NOVEDADES", "de": "NEUIGKEITEN",
                 "pt": "NOVIDADES", "it": "NOVITÀ", "ru": "НОВОСТИ"},
    "nav_dl": {"fr": "TÉLÉCHARGEMENTS", "en": "DOWNLOADS", "es": "DESCARGAS",
               "de": "DOWNLOADS", "pt": "DOWNLOADS", "it": "DOWNLOAD", "ru": "ЗАГРУЗКИ"},
    "nav_log": {"fr": "JOURNAL", "en": "LOG", "es": "REGISTRO", "de": "PROTOKOLL",
                "pt": "REGISTO", "it": "REGISTRO", "ru": "ЖУРНАЛ"},
    "featured": {"fr": "EN UNE", "en": "FEATURED", "es": "DESTACADOS", "de": "IM FOKUS",
                 "pt": "DESTAQUES", "it": "IN PRIMO PIANO", "ru": "В ЦЕНТРЕ"},
    "lib_sub": {"fr": "{n} projets Studio Echelon", "en": "{n} Studio Echelon projects",
                "es": "{n} proyectos Studio Echelon", "de": "{n} Studio-Echelon-Projekte",
                "pt": "{n} projetos Studio Echelon", "it": "{n} progetti Studio Echelon",
                "ru": "{n} проектов Studio Echelon"},
    "search": {"fr": "Rechercher…", "en": "Search…", "es": "Buscar…", "de": "Suchen…",
               "pt": "Procurar…", "it": "Cerca…", "ru": "Поиск…"},
    "no_results": {"fr": "Aucun projet ne correspond.", "en": "No project matches.",
                   "es": "Ningún proyecto coincide.", "de": "Kein Projekt gefunden.",
                   "pt": "Nenhum projeto corresponde.", "it": "Nessun progetto trovato.",
                   "ru": "Ничего не найдено."},
    "installed": {"fr": "Installé", "en": "Installed", "es": "Instalado", "de": "Installiert",
                  "pt": "Instalado", "it": "Installato", "ru": "Установлено"},
    "not_installed": {"fr": "Non installé", "en": "Not installed", "es": "No instalado",
                      "de": "Nicht installiert", "pt": "Não instalado", "it": "Non installato",
                      "ru": "Не установлено"},
    "dl_empty": {"fr": "Aucun téléchargement en cours.", "en": "No download in progress.",
                 "es": "Sin descargas en curso.", "de": "Kein Download aktiv.",
                 "pt": "Nenhum download em curso.", "it": "Nessun download in corso.",
                 "ru": "Нет активных загрузок."},
    "dl_current": {"fr": "En cours", "en": "In progress", "es": "En curso", "de": "Läuft",
                   "pt": "Em curso", "it": "In corso", "ru": "Выполняется"},
    "dl_sub": {"fr": "installations et mises à jour", "en": "installs and updates",
               "es": "instalaciones y actualizaciones", "de": "Installationen und Updates",
               "pt": "instalações e atualizações", "it": "installazioni e aggiornamenti",
               "ru": "установки и обновления"},
    "announce": {"fr": "ANNONCE", "en": "NOTICE", "es": "AVISO", "de": "HINWEIS",
                 "pt": "AVISO", "it": "AVVISO", "ru": "ОБЪЯВЛЕНИЕ"},
    "prof_pseudo": {"fr": "Changer de pseudo", "en": "Change username",
                    "es": "Cambiar usuario", "de": "Namen ändern",
                    "pt": "Mudar nick", "it": "Cambia nome", "ru": "Сменить ник"},
    "prof_sub": {"fr": "ton profil, partagé par tous les projets",
                 "en": "your profile, shared across all projects",
                 "es": "tu perfil, común a todos los proyectos",
                 "de": "dein Profil, für alle Projekte",
                 "pt": "o teu perfil, comum a todos os projetos",
                 "it": "il tuo profilo, comune a tutti i progetti",
                 "ru": "твой профиль, общий для всех проектов"},
    "updating": {"fr": "MISE À JOUR…", "en": "UPDATING…", "es": "ACTUALIZANDO…",
                 "de": "UPDATE…", "pt": "ATUALIZANDO…", "it": "AGGIORNAMENTO…",
                 "ru": "ОБНОВЛЕНИЕ…"},
    "up_to_date": {"fr": "À jour.", "en": "Up to date.", "es": "Actualizado.",
                   "de": "Aktuell.", "pt": "Atualizado.", "it": "Aggiornato.",
                   "ru": "Обновлено."},
    "update_avail": {"fr": "Mise à jour", "en": "Update", "es": "Actualización",
                     "de": "Update", "pt": "Atualização", "it": "Aggiornamento",
                     "ru": "Обновление"},
    "f_all": {"fr": "Tous", "en": "All", "es": "Todos", "de": "Alle",
              "pt": "Todos", "it": "Tutti", "ru": "Все"},
    "f_installed": {"fr": "Installés", "en": "Installed", "es": "Instalados",
                    "de": "Installiert", "pt": "Instalados", "it": "Installati",
                    "ru": "Установленные"},
    "f_online": {"fr": "En ligne", "en": "Online", "es": "En línea", "de": "Online",
                 "pt": "Online", "it": "Online", "ru": "В сети"},
    "news_sub": {"fr": "tout ce qui bouge sur les projets", "en": "everything moving on the projects",
                 "es": "todo lo que se mueve en los proyectos",
                 "de": "alles Neue zu den Projekten",
                 "pt": "tudo o que mexe nos projetos", "it": "tutto ciò che si muove sui progetti",
                 "ru": "всё новое по проектам"},
}

# Sections du rail de gauche : la navigation porte les PAGES, pas les jeux —
# c'est ce qui permet d'aligner 20 projets sans jamais toucher au rail.
PAGES = [
    ("home", "nav_home", "◆"),
    ("library", "nav_library", "▦"),
    ("news", "nav_news", "✦"),
]

# zone hors écran : un hit-test la traverse toujours sans jamais matcher
NOZONE = (-9, -9, -9, -9)

# Accueil : rangée « en une » (3 projets phares)
FEAT_W, FEAT_H, FEAT_GAP = 168, 104, 16
FEAT_TOP = H - 178

# Bibliothèque : grille de cartes portrait 3:4
CARD_W, CARD_H, CARD_GAP, CARD_COLS = 150, 200, 18, 6
CARD_PITCH = CARD_H + 46

# animations : douces et courtes, jamais de mouvement qui retarde un clic
PAGE_FADE_STEPS = 8      # fondu d'entrée d'une page
CARD_LIFT = 6            # de combien une carte se soulève au survol
LIFT_EASE = 0.3          # inertie du soulèvement (0 = figé, 1 = instantané)
NAV_EASE = 0.28          # inertie de l'indicateur du rail

LIB_FILTERS = ("all", "installed", "online")


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
RPC = {}     # bloc `rpc` du catalogue : {"app_id": "...", ...} — une seule app
CONF = {}    # bloc `config` : tout ce qui se règle SANS republier l'exe


def conf(key, default=None):
    """Réglage du catalogue, sinon la valeur par défaut embarquée.

    Le but est qu'un maximum de choses se change en publiant `catalog.json` au
    lieu de reconstruire et redistribuer un exe : version de Minecraft, runtime
    Java, invitation Discord, bornes de RAM, textes, annonce globale.
    """
    cur = CONF
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur if cur is not None else default


def mc_version(game=None):
    """Version de Minecraft : par jeu, sinon globale, sinon la valeur embarquée."""
    if game and game.get("mc_version"):
        return str(game["mc_version"])
    return str(conf("mc_version", MC_VERSION))


def java_runtime(game=None):
    if game and game.get("java_runtime"):
        return str(game["java_runtime"])
    return str(conf("java_runtime", JAVA_RUNTIME))


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


class RichPresence(object):
    """Rich Presence Discord avec UNE SEULE application pour tous les projets.

    Le piège classique est une app Discord par jeu : un application_id par
    projet, des assets à re-uploader partout, et 20 apps à maintenir. Ici il y a
    un seul `app_id` (dans `catalog.json`) et une clé d'asset par projet
    (`rpc_asset`, par défaut l'id du jeu). Ajouter un projet = uploader une image
    dans l'app existante et l'écrire au catalogue. Zéro code.

    Protocole IPC Discord en direct : pas de dépendance, socket nommé sous
    Windows, socket unix ailleurs. Toute erreur est ignorée — Discord absent ne
    doit jamais empêcher de jouer.
    """
    OP_HANDSHAKE, OP_FRAME = 0, 1

    def __init__(self, app_id):
        self.app_id = str(app_id)
        self.sock = None
        self._pid = os.getpid()

    def _open(self):
        import struct
        if os.name == "nt":
            for i in range(10):
                try:
                    self.sock = open(r"\\.\pipe\discord-ipc-%d" % i, "r+b", 0)
                    break
                except Exception:
                    continue
        else:
            import socket
            base = (os.environ.get("XDG_RUNTIME_DIR")
                    or os.environ.get("TMPDIR") or "/tmp").rstrip("/")
            for i in range(10):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect("%s/discord-ipc-%d" % (base, i))
                    self.sock = s.makefile("rwb", 0)
                    break
                except Exception:
                    continue
        if self.sock is None:
            raise IOError("Discord introuvable")
        self._send(self.OP_HANDSHAKE, {"v": 1, "client_id": self.app_id})
        self._recv()

    def _send(self, op, payload):
        import struct
        data = json.dumps(payload).encode("utf-8")
        self.sock.write(struct.pack("<II", op, len(data)) + data)
        self.sock.flush()

    def _recv(self):
        import struct
        head = self.sock.read(8)
        if len(head) < 8:
            raise IOError("IPC ferme")
        _op, ln = struct.unpack("<II", head)
        return self.sock.read(ln)

    def set(self, activity):
        if self.sock is None:
            self._open()
        self._send(self.OP_FRAME, {
            "cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
            "args": {"pid": self._pid, "activity": activity},
        })
        self._recv()

    def close(self):
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self.sock = None


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
    # visuel portrait 3:4 de la grille Bibliothèque : optionnel, on recadre
    # le key-art quand il manque (donc aucun asset obligatoire par projet).
    g["card"] = None
    if entry.get("card_url"):
        try:
            g["card"] = _cached_asset(entry["card_url"])
        except Exception:
            g["card"] = None
    elif entry.get("card"):
        g["card"] = entry["card"]
    return g


def load_games():
    """catalogue distant → cache → défaut embarqué. Jamais bloquant.

    ECHELON_CATALOG=<chemin> fait lire un catalogue LOCAL : c'est l'aperçu
    (`./echelon preview`) avant publication. Dans ce mode on ne touche pas au
    cache réel, pour ne jamais polluer l'install d'un joueur.
    """
    import urllib.request
    global RPC, CONF
    raw = None
    doc = None
    override = os.environ.get("ECHELON_CATALOG")
    cache = os.path.join(game_root("StudioEchelon"), "catalog.json")
    if override:
        try:
            doc = json.load(open(override, encoding="utf-8"))
            raw = doc.get("games")
            logging.info("catalogue local (aperçu) : %s", override)
        except Exception:
            logging.error("aperçu illisible : %s", override)
            raw = None
    else:
        try:
            req = urllib.request.Request(CLIENT_BASE + "/catalog.json",
                                         headers={"User-Agent": "echelon-client"})
            doc = json.load(urllib.request.urlopen(req, timeout=8))
            raw = doc.get("games")
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump(doc, open(cache, "w"))
        except Exception:
            try:
                doc = json.load(open(cache))
                raw = doc.get("games")
            except Exception:
                raw = None
    if isinstance(doc, dict) and isinstance(doc.get("rpc"), dict):
        RPC = doc["rpc"]     # une app pour tous les projets
    if isinstance(doc, dict) and isinstance(doc.get("config"), dict):
        CONF = doc["config"]
        logging.info("config distante : %s", sorted(CONF.keys()))
    if not raw:
        return list(DEFAULT_GAMES)
    out = []
    for entry in raw:
        if entry.get("hidden"):
            continue   # projet préparé côté catalogue mais pas encore exposé
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
        # coquille v2 : le rail navigue entre PAGES, la sélection de jeu est
        # un état à part (l'Accueil est la fiche du jeu sélectionné).
        self.page = "home"
        self.scroll = {"library": 0, "news": 0, "downloads": 0}
        self.lib_query = ""
        self.lib_focus = False
        self.lib_filter = "all"
        # états d'animation : ils survivent aux redraws (les items, eux, meurent)
        self._nav_ind_y = None
        self._nav_active_y = 100
        self._page_fade = None
        self._lift = {}
        self._card_anim = []
        # versions distantes par jeu, pour un badge « Mise à jour » honnête
        self._remote_ver = {}
        self.lang = self._state().get("lang", "fr")
        if self.lang not in [c for c, _, _ in LANGS]:
            self.lang = "fr"
        self.lang_open = False
        self.prof_open = False
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
        self.autoupdating = False
        self._cancel = False
        self._online = {}   # id de jeu → nb de joueurs (None = injoignable)
        self._discord = None  # (total, en_ligne) du Discord, ou None si injoignable
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
        threading.Thread(target=self._discord_loop, daemon=True).start()
        threading.Thread(target=self._updates_loop, daemon=True).start()
        threading.Thread(target=self._autoupdate_boot, daemon=True).start()
        threading.Thread(target=self._rpc_loop, daemon=True).start()
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

    # ── membres Discord (endpoint invite, pas besoin du widget) ────────
    DISCORD_INVITE = "playharbor"   # defaut ; conf("discord_invite") prime

    def _fetch_discord(self):
        """(total, en_ligne) via l'API invite Discord, ou None."""
        import urllib.request
        url = ("https://discord.com/api/v9/invites/"
               + conf("discord_invite", self.DISCORD_INVITE) + "?with_counts=true")
        req = urllib.request.Request(url, headers={"User-Agent": "echelon-client"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d = json.load(r)
        total = d.get("approximate_member_count")
        online = d.get("approximate_presence_count")
        if total is None:
            return None
        return (int(total), int(online) if online is not None else None)

    def _discord_loop(self):
        import time
        while True:
            try:
                res = self._fetch_discord()
                if res is not None:
                    self._discord = res   # sinon on garde le dernier connu
            except Exception:
                pass                      # hors-ligne : dernier connu conservé
            time.sleep(60)

    # ── mises à jour des jeux : même source que l'install (manifest du canal) ──
    def _updates_loop(self):
        """relève la version publiée de chaque jeu pour un badge non deviné.

        Le paramètre anti-cache n'est pas décoratif : sans lui, un client lancé
        juste après une publication lit un manifest périmé sur un cache
        intermédiaire (constaté en vrai — GitHub envoie `Cache-Control:
        no-cache`, un cache en amont le servait quand même) et croit être à jour.
        """
        import time, urllib.request
        n = 0
        while True:
            n += 1
            for g in list(GAMES):
                try:
                    channel = g["base"].rsplit("/", 1)[1]
                    req = urllib.request.Request(
                        RELEASES + "/" + channel + "/manifest.json?t=%d" % time.time(),
                        headers={"User-Agent": "echelon-client",
                                 "Cache-Control": "no-cache", "Pragma": "no-cache"})
                    m = json.load(urllib.request.urlopen(req, timeout=8))
                    ver = m.get("mod_version")
                    if ver:
                        self._remote_ver[g["id"]] = str(ver)
                except Exception:
                    pass    # hors ligne : on n'affiche simplement pas de badge
            self.after(0, self._draw)
            # les 3 premières passes sont rapprochées : elles rattrapent une
            # première lecture perimee, sinon la maj au demarrage etait manquee
            # pour toute la session.
            time.sleep(20 if n < 3 else 300)

    # ── Rich Presence : une app, un asset par projet ───────────────────
    def _rpc_activity(self, g):
        """charge utile Discord pour le projet courant, tirée du catalogue."""
        act = {
            "details": g["name"],
            "state": GT(g, "tagline", self.lang, "")[:120] or self.T("nav_home"),
            "assets": {
                # clé d'asset uploadée UNE fois dans l'app Echelon
                "large_image": g.get("rpc_asset") or g["id"],
                "large_text": g["name"],
                "small_image": RPC.get("small_asset", "echelon"),
                "small_text": "Studio Echelon",
            },
        }
        n = self._online.get(g["id"])
        if isinstance(n, int):
            act["state"] = "%s · %d %s" % (g["name"], n, self.T("players"))
        url = RPC.get("button_url") or g.get("discord")
        if url:
            act["buttons"] = [{"label": RPC.get("button_label", "Studio Echelon"),
                               "url": url}]
        return act

    def _rpc_loop(self):
        """présence du HUB : reflète le projet sélectionné, sans app par jeu."""
        import time
        app_id = RPC.get("app_id")
        if not app_id:
            logging.info("rpc : pas d'app_id au catalogue, presence desactivee")
            return
        rp = RichPresence(app_id)
        last = None
        while True:
            try:
                g = GAMES[self.selected]
                if self._opts(g).get("rpc", True) and not self.busy:
                    key = (g["id"], self.lang, self._online.get(g["id"]))
                    if key != last:
                        rp.set(self._rpc_activity(g))
                        last = key
                elif last is not None:
                    rp.close()
                    last = None
            except Exception as e:
                rp.close()
                last = None
                logging.debug("rpc indisponible : %s", e)
            time.sleep(5)

    # ── mise à jour appliquée dès le lancement ────────────────────────
    def _autoupdate_boot(self):
        """Le joueur ne doit pas découvrir en cliquant JOUER qu'il doit attendre :
        si un jeu DÉJÀ installé a une version publiée plus récente, on la
        télécharge tout de suite, visiblement, avec l'UI de chargement."""
        import time
        # On ne regarde pas une seule fois : une premiere lecture perimee (cache)
        # ou hors ligne ferait rater la maj pour toute la session. On surveille
        # pendant 2 minutes, puis on laisse le badge faire son travail.
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            if self.busy:
                return                 # une install est deja en cours
            todo = [g for g in GAMES
                    if self._has_update(g)
                    and os.path.isdir(os.path.join(g["dir"], "mods"))]
            if todo:
                logging.info("maj auto au démarrage : %s", [g["id"] for g in todo])
                self.after(0, self._autoupdate_run, todo)
                return

    def _autoupdate_run(self, todo):
        if self.busy:
            return
        self.busy = True
        self.autoupdating = True
        self.selected = GAMES.index(todo[0])
        self.page = "home"
        self._draw()
        threading.Thread(target=self._autoupdate_thread, args=(todo,),
                         daemon=True).start()

    def _autoupdate_thread(self, todo):
        try:
            self._cancel = False
            for g in todo:
                self.selected = GAMES.index(g)
                self.after(0, self._draw)
                self.status.set(self.T("downloading", n=g["name"]))
                mods = os.path.join(g["dir"], "mods")
                self._sync_mod(g, mods)     # écrit mod_<canal> → _has_update tombe
            self.status.set(self.T("up_to_date"))
        except Hub._Cancelled:
            self.status.set(self.T("cancelled"))
        except Exception as e:
            logging.error("maj auto échouée : %s", e)
            self.status.set("")             # au pire, JOUER la refera
        finally:
            self.progress_val.set(0)
            self.busy = False
            self.autoupdating = False
            self.after(0, self._draw)

    def _has_update(self, g):
        """True seulement si on connaît les DEUX versions et qu'elles diffèrent."""
        local = self._state().get("mod_" + g["base"].rsplit("/", 1)[1])
        remote = self._remote_ver.get(g["id"])
        return bool(local and remote and local != remote)

    def _update_count(self):
        return sum(1 for g in GAMES if self._has_update(g))

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
                # `timeout` ECHOUE sans console (et ce .bat tourne en
                # CREATE_NO_WINDOW) : le delai de 2 s ne s'appliquait pas, donc
                # `move` courait contre l'exe encore ouvert, qui tient son
                # fichier. Resultat non deterministe — constate en vrai : exe
                # remplace mais application jamais relancee.
                # `ping` marche sans console, et on reessaie jusqu'a ce que le
                # fichier soit libere : plus de course. Si le remplacement est
                # vraiment impossible, on relance quand meme l'ancien exe pour
                # ne jamais laisser le joueur sans rien.
                # Ce script etait MUET : quand la relance echouait (constate en
                # 1.6 puis 1.7), il ne restait aucune trace et on ne pouvait que
                # speculer. Il journalise maintenant chaque etape dans
                # StudioEchelon/update.log, et il REESSAIE la relance en
                # verifiant que le process apparait vraiment.
                ulog = os.path.join(game_root("StudioEchelon"), "update.log")
                name = os.path.basename(exe)
                with open(bat, "w") as f:
                    f.write(f'''@echo off
set LOG={ulog}
echo [%date% %time%] mise a jour demarree >>"%LOG%"
set n=0
:retry
ping -n 2 127.0.0.1 >nul
move /y "{new}" "{exe}" >nul 2>&1
if not exist "{new}" goto moved
set /a n+=1
echo [%date% %time%] fichier encore verrouille (essai %n%) >>"%LOG%"
if %n% lss 30 goto retry
echo [%date% %time%] ECHEC remplacement, relance de l ancien >>"%LOG%"
goto launch
:moved
echo [%date% %time%] exe remplace apres %n% essai(s) >>"%LOG%"
:launch
set m=0
:again
set /a m+=1
start "" "{exe}"
ping -n 4 127.0.0.1 >nul
tasklist /FI "IMAGENAME eq {name}" | find /I "{name}" >nul
if not errorlevel 1 goto ok
echo [%date% %time%] relance ratee (essai %m%) >>"%LOG%"
if %m% lss 5 goto again
echo [%date% %time%] ECHEC de la relance >>"%LOG%"
goto fin
:ok
echo [%date% %time%] relance OK (essai %m%) >>"%LOG%"
:fin
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
        # `config.text.<langue>.<cle>` permet de corriger n'importe quel libellé
        # depuis le catalogue, sans reconstruire l'exe.
        s = (conf("text.%s.%s" % (self.lang, key))
             or TR.get(key, {}).get(self.lang) or TR.get(key, {}).get("fr", key))
        try:
            return s.format(**kw) if kw else s
        except Exception:
            return s   # un texte distant mal formaté ne doit rien casser

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

        # UI de chargement : barre, pourcentage et points qui battent
        if hasattr(self, "_inst_bar"):
            ibx, iby, ibw, ibh = self._inst_geom
            pct = max(0.0, min(100.0, self.progress_val.get()))
            c.coords(self._inst_bar, ibx, iby, ibx + ibw * pct / 100.0, iby + ibh)
            c.itemconfig(self._inst_pct, text="%d %%" % int(pct))
            c.itemconfig(self._inst_status, text=self.status.get())
            iacc = GAMES[self.selected]["accent"]
            for k, item in enumerate(self._inst_dots):
                a = 0.28 + 0.72 * (0.5 + 0.5 * math.sin(self.t * 4.2 - k * 0.75))
                c.itemconfig(item, fill=self._mix(iacc, a))

        # ── animations légères ────────────────────────────────────────
        # liseré du rail : glisse vers la section active
        if getattr(self, "_nav_ind", None) is not None:
            self._nav_ind_y += (self._nav_active_y - self._nav_ind_y) * NAV_EASE
            c.coords(self._nav_ind, 7, self._nav_ind_y + 7, 10, self._nav_ind_y + 27)

        # cartes : soulèvement amorti au survol
        for key, items, target in self._card_anim:
            cur = self._lift.get(key, 0.0)
            if abs(cur - target) < 0.05:
                cur = float(target)
            else:
                cur += (target - cur) * LIFT_EASE
            self._lift[key] = cur
            if cur > 0.02:
                for item, ix, iy in items:
                    c.coords(item, ix, iy - cur)

        # logo du projet sélectionné : respiration
        if getattr(self, "_feat_logo", None) is not None:
            fx, fy = self._feat_logo_base
            fy -= self._lift.get(self._feat_logo_key, 0.0)
            c.coords(self._feat_logo, fx, fy + math.sin(self.t * 2.2) * 2.5)

        # fondu d'entrée de page
        if self._page_fade is not None and getattr(self, "_pf_item", None) is not None:
            self._page_fade += 1
            if self._page_fade >= PAGE_FADE_STEPS:
                c.delete(self._pf_item)
                self._page_fade = None
                self._pf_item = None
            else:
                c.itemconfig(self._pf_item, image=self._fade_veil(self._page_fade))

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
    # zones/items propres à une page : remis à zéro à chaque redraw, sinon un
    # hit-test d'une autre page répondrait encore (30+ zones absolues).
    _ZONE_ATTRS = ("_play_zone", "_gear_zone", "_input_zone", "_discord_zone",
                   "_site_zone", "_search_zone", "_instcancel_zone", "_chip_zone",
                   "_lang_zone", "_discord_zone")
    _ITEM_ATTRS = ("_dot_item", "_online_item", "_input_text",
                   "_input_cursor", "_play_item", "_play_frames", "_bar_fill",
                   "_status_item", "_bar_geom", "_search_item",
                   "_inst_bar", "_inst_geom", "_inst_status", "_inst_pct", "_inst_dots",
                   "_feat_logo", "_feat_logo_base", "_feat_logo_key", "_pf_item")

    def _select(self, idx):
        if idx == self.selected or self.busy:
            return
        prev = GAMES[self.selected]
        self.selected = idx
        self._draw(fade_from=prev)

    def _pick_game(self, idx):
        """clic sur une carte : sélectionne le jeu ET ramène sur sa fiche."""
        if self.busy and idx != self.selected:
            return
        prev = GAMES[self.selected]
        changed = idx != self.selected
        self.selected = idx
        self.page = "home"
        self.hover = None
        self._draw(fade_from=prev if changed else None)

    def _goto(self, page):
        if page == self.page:
            return
        self.page = page
        self.hover = None
        self._page_fade = 0
        self._draw()

    def _featured(self):
        """indices des 3 projets en une : champ `featured` du catalogue, sinon l'ordre."""
        idx = [i for i, g in enumerate(GAMES) if g.get("featured")]
        return (idx or list(range(len(GAMES))))[:3]

    def _draw(self, fade_from=None):
        c = self.canvas
        c.delete("all")
        for a in self._ITEM_ATTRS:
            self.__dict__.pop(a, None)
        for a in self._ZONE_ATTRS:
            setattr(self, a, NOZONE)
        self._game_zones = []
        self._nav_zones = []
        self._filter_zones = []
        self._prof_zones = []
        self._card_anim = []

        g = GAMES[self.selected]
        accent = g["accent"]

        # le key-art du jeu sélectionné reste le fond de TOUTES les pages :
        # c'est lui qui porte la DA, les autres pages le voilent seulement.
        self._bg_item = c.create_image(0, 0, anchor="nw", image=self._bg_composed(g))
        if fade_from is not None:
            self._fading = (self._fade_frames(fade_from, g), 0)
            c.itemconfig(self._bg_item, image=self._bg_composed(fade_from))

        self._particle_items = [
            c.create_oval(p[0], p[1], p[0] + p[3], p[1] + p[3], fill="#C8D8CC", width=0)
            for p in self.particles
        ]

        if self.page == "home":
            self._draw_home(c, g, accent)
        else:
            c.create_image(0, 0, anchor="nw", image=self._page_veil())
            if self.page == "library":
                self._draw_library(c, accent)
            elif self.page == "news":
                self._draw_news(c, accent)
            elif self.page == "downloads":
                self._draw_downloads(c, accent)

        # rail puis barre haute PAR-DESSUS : ils masquent les débords de grille
        # quand elle défile, ce qui évite d'avoir à clipper le canvas.
        self._draw_rail(c, accent)
        self._draw_topbar(c, accent)

        if self.options_open:
            self._draw_options(c, g)
        if self.skin_open:
            self._draw_skin(c, g)
        if self.log_open:
            self._draw_log(c, g)
        if self.busy:
            self._draw_installing(c, g)   # par-dessus tout : plus de console

        # fondu d'entrée de page : un voile qui s'efface en quelques frames
        if self._page_fade is not None:
            self._pf_item = c.create_image(0, 0, anchor="nw",
                                           image=self._fade_veil(self._page_fade))

    def _fade_veil(self, i):
        key = ("pfade", i)
        if key not in self._img_cache:
            a = int(190 * (1.0 - i / float(PAGE_FADE_STEPS)))
            self._img_cache[key] = ImageTk.PhotoImage(
                Image.new("RGBA", (W, H), (6, 9, 11, a)))
        return self._img_cache[key]

    def _page_veil(self):
        """voile des pages autres que l'Accueil : le key-art reste lisible dessous."""
        if "veil" not in self._img_cache:
            self._img_cache["veil"] = ImageTk.PhotoImage(
                Image.new("RGBA", (W, H), (6, 9, 11, 232)))
        return self._img_cache["veil"]

    # ── rail de gauche : des SECTIONS, pas des jeux ────────────────────
    def _draw_rail(self, c, accent):
        c.create_rectangle(0, 0, SIDEBAR, H, fill="#080A0C", width=0)
        c.create_rectangle(SIDEBAR, 0, SIDEBAR + 1, H, fill="#151D1F", width=0)

        # identité studio en en-tête (place d'un logo d'éditeur)
        studio_hov = self.hover == "studio"
        c.create_image(30, 40, image=self._load("assets/studio_icon.png", size=(26, 26),
                                                dim=1.0 if studio_hov else 0.9))
        c.create_image(30 + 14 + 31, 40,
                       image=self._load("assets/studio_wordmark.png", size=(100, 20),
                                        dim=1.0 if studio_hov else 0.8))
        self._studio_zone = (14, 24, 14 + 130, 56)
        c.create_rectangle(20, 74, SIDEBAR - 20, 75, fill="#161F21", width=0)

        y = 100
        for key, label, glyph in PAGES:
            self._nav_row(c, key, label, glyph, y, accent)
            y += 44

        # bas du rail : ce qui est transverse aux projets
        self._nav_row(c, "downloads", "nav_dl", "⬇", H - 104, accent,
                      badge=self._update_count())
        self._nav_row(c, "log", "nav_log", "≡", H - 60, accent)

        # ── annonce globale, réglable depuis le catalogue ────────────────
        # Dans le rail : visible sur TOUTES les pages et ne peut chevaucher
        # aucun titre. Permet d'annoncer une maintenance sans republier l'exe.
        msg = conf("announce.%s" % self.lang) or conf("announce.fr")
        if msg:
            aw = SIDEBAR - 28
            f8 = tkfont.Font(family=self.FONT, size=8)
            lines = max(1, int(f8.measure(str(msg)) / float(aw - 28)) + 1)
            ah = 34 + 13 * lines
            ay = 100 + 44 * len(PAGES) + 22
            c.create_image(14 + aw // 2, ay + ah // 2,
                           image=self._flat("annonce%d" % ah, aw, ah,
                                            (24, 20, 14, 240), radius=12))
            c.create_text(28, ay + 15, anchor="w", text="!",
                          fill="#F0C36A", font=self.F(10, True))
            c.create_text(40, ay + 15, anchor="w", text=self.T("announce"),
                          fill="#F0C36A", font=self.F(8, True))
            c.create_text(28, ay + 32, anchor="nw", text=str(msg),
                          fill="#D8CBB0", font=self.F(8), width=aw - 28)

        # un seul liseré, qui glisse d'une section à l'autre (animé par _tick)
        if self._nav_ind_y is None:
            self._nav_ind_y = float(self._nav_active_y)
        self._nav_ind = c.create_rectangle(7, self._nav_ind_y + 7, 10, self._nav_ind_y + 27,
                                           fill=accent, width=0)

        if studio_hov:
            self._draw_studio_tooltip(c)

    def _nav_row(self, c, key, label, glyph, y, accent, badge=0):
        active = (self.page == key) or (key == "log" and self.log_open)
        hov = self.hover == ("nav", key)
        if active or hov:
            c.create_image(SIDEBAR // 2, y + 17,
                           image=self._flat("nav" + ("_a" if active else "_h"),
                                            SIDEBAR - 26, 34,
                                            (21, 31, 29, 255) if active else (17, 24, 23, 215),
                                            radius=10))
        if active:
            self._nav_active_y = y
        col = "#EAF6EF" if active else ("#C8D8CC" if hov else "#76918A")
        c.create_text(30, y + 17, text=glyph, fill=accent if active else col,
                      font=(self.FONT, 11))
        c.create_text(48, y + 17, anchor="w", text=self.T(label), fill=col, font=self.F(9, True))
        if badge:
            # pastille sur l'icône : le libellé peut être long selon la langue
            bx, by = 38, y + 9
            c.create_oval(bx - 7, by - 7, bx + 7, by + 7, fill=accent, width=0)
            c.create_text(bx, by, text=str(badge) if badge < 10 else "9+",
                          fill="#06140C", font=self.F(7, True))
        self._nav_zones.append((10, y, SIDEBAR - 14, y + 34, key))

    # ── barre haute : un seul chip profil, qui porte tous les réglages ──
    # Avant, la langue avait sa pastille à part, le skin était rangé dans les
    # options PAR JEU alors qu'il est global, et le Discord était un bouton par
    # projet alors que les projets partagent le même lien. Tout est ici.
    def _draw_topbar(self, c, accent):
        cw, ch = 168, 32
        cxx, cyy = W - cw - 18, 16
        self._chip_zone = (cxx, cyy, cxx + cw, cyy + ch)
        chov = self.hover == "chip" or self.prof_open
        c.create_image(cxx + cw // 2, cyy + ch // 2,
                       image=self._flat("chip" + ("_h" if chov else ""), cw, ch,
                                        (22, 30, 34, 240) if chov else (14, 20, 23, 212),
                                        radius=13))
        self._draw_head(c, cxx + 22, cyy + ch // 2, 22, accent)
        c.create_text(cxx + 42, cyy + ch // 2, anchor="w", text=self.pseudo_text[:13],
                      fill="#EAF6EF" if chov else "#C8D8CC", font=self.F(9, True))
        c.create_text(cxx + cw - 14, cyy + ch // 2, text="▾",
                      fill=accent if chov else "#7A948A", font=self.F(8))

        if self.prof_open:
            self._draw_profile_menu(c, cxx + cw, cyy + ch + 8, accent)

    def _draw_head(self, c, x, y, size, accent):
        """tête de skin, ou initiale sur pastille accent si aucun skin."""
        head = self._skin_head(size)
        if head is not None:
            c.create_image(x, y, image=head)
        else:
            r = size // 2 + 1
            c.create_oval(x - r, y - r, x + r, y + r, fill=accent, width=0)
            c.create_text(x, y, text=(self.pseudo_text or "?")[:1].upper(),
                          fill="#06140C", font=self.F(9, True))

    def _draw_profile_menu(self, c, right, top, accent):
        """menu profil : pseudo, skin, langue, Discord, studio — tout le global."""
        # 320 et pas 268 : en FR « Rejoindre le Discord » + le compteur de
        # membres ne tenaient pas et se chevauchaient.
        mw = 320
        cur = next((l for l in LANGS if l[0] == self.lang), LANGS[0])
        rows = [
            ("pseudo", "✎", self.T("prof_pseudo"), ""),   # déjà dans l'en-tête
            ("skin", "◲", self.T("skin"), ""),
            ("lang", cur[2], self.T("language"), cur[0].upper()),
            ("discord", None, self.T("discord"), self._discord_count()),
            ("site", "◉", self.T("see_site"), ""),
        ]
        rowh, pad = 40, 12
        mh = rowh * len(rows) + pad * 2 + 44
        mx = right - mw
        c.create_image(mx + mw // 2, top + mh // 2,
                       image=self._flat("profmenu", mw, mh, (13, 18, 22, 250), radius=16))

        # en-tête : la tête en grand + le pseudo
        self._draw_head(c, mx + 34, top + 30, 34, accent)
        c.create_text(mx + 62, top + 22, anchor="w", text=self.pseudo_text or "—",
                      fill="#EAF6EF", font=self.F(12, True))
        c.create_text(mx + 62, top + 40, anchor="w", text=self.T("prof_sub"),
                      fill="#6A7E74", font=self.F(8), width=mw - 78)
        c.create_rectangle(mx + 16, top + 56, mx + mw - 16, top + 57, fill="#1C2622", width=0)

        self._prof_zones = []
        y = top + 62
        for key, glyph, label, value in rows:
            hov = self.hover == ("prof", key)
            if hov:
                c.create_image(mx + mw // 2, y + rowh // 2 - 2,
                               image=self._flat("profrow", mw - 20, rowh - 6,
                                                (23, 32, 30, 255), radius=10))
            if key == "discord":
                c.create_image(mx + 32, y + rowh // 2 - 2,
                               image=self._load("assets/discord_mark.png", size=(20, 15)))
            else:
                c.create_text(mx + 32, y + rowh // 2 - 2, text=glyph,
                              fill=accent if hov else "#8AA49A", font=(self.FONT, 12))
            c.create_text(mx + 56, y + rowh // 2 - 2, anchor="w", text=label,
                          fill="#EAF6EF" if hov else "#C8D8CC", font=self.F(9, True))
            if value:
                c.create_text(mx + mw - 24, y + rowh // 2 - 2, anchor="e", text=value,
                              fill="#7A948A", font=self.F(8))
            self._prof_zones.append((mx + 10, y, mx + mw - 10, y + rowh - 4, key))
            y += rowh

        if self.lang_open:
            self._draw_lang_menu(c, mx - 156, top + 62 + rowh * 2, 150)

    def _discord_count(self):
        if self._discord is None:
            return ""
        total, _ = self._discord
        return format(int(total), ",").replace(",", " ") + " " + self.T("members")

    def _skin_head(self, size):
        """tête du skin (calque chapeau compris) pour le chip joueur."""
        try:
            mtime = int(os.path.getmtime(self._skin_path()))
        except Exception:
            return None
        key = ("head", mtime, size)
        if key not in self._img_cache:
            try:
                sk = Image.open(self._skin_path()).convert("RGBA")
                head = sk.crop((8, 8, 16, 16))
                hat = sk.crop((40, 8, 48, 16))
                head.alpha_composite(hat)
                head = head.resize((size, size), Image.NEAREST)
                self._img_cache[key] = ImageTk.PhotoImage(head)
            except Exception:
                return None
        return self._img_cache[key]

    # ── page Accueil : la fiche du jeu sélectionné ─────────────────────
    def _draw_home(self, c, g, accent):
        # ── news du jeu (catalogue distant → modifiable sans rebuild)
        news = GT(g, "news", self.lang, [])
        if news:
            news = news[:4]
            nw, nh = 350, 40 + 18 * len(news)
            nx, ny = SIDEBAR + 34, FEAT_TOP - 34 - nh
            c.create_image(nx + nw // 2, ny + nh // 2,
                           image=self._flat("news" + g["id"] + str(len(news)), nw, nh,
                                            (10, 15, 17, 205), radius=16))
            c.create_text(nx + 18, ny + 17, anchor="w", text=self.T("news"),
                          fill=accent, font=self.F(9, True))
            for i, line in enumerate(news):
                c.create_text(nx + 18, ny + 40 + i * 18, anchor="w", text="•  " + line,
                              fill="#C8DCD0", font=self.F(9))

        # ── rangée « en une » : 3 projets phares, en contenu et non en menu
        fx = SIDEBAR + 34
        c.create_text(fx, FEAT_TOP - 16, anchor="w", text=self.T("featured"),
                      fill="#7A948A", font=self.F(9, True))
        for slot, i in enumerate(self._featured()):
            game = GAMES[i]
            x = fx + slot * (FEAT_W + FEAT_GAP)
            sel = i == self.selected
            hov = self.hover == ("game", i)
            moving = []
            if sel:
                moving.append((c.create_image(
                    x + FEAT_W // 2, FEAT_TOP + FEAT_H // 2,
                    image=self._flat("featsel" + game["id"], FEAT_W + 6, FEAT_H + 6,
                                     self._hex(accent) + (255,), radius=14)),
                    x + FEAT_W // 2, FEAT_TOP + FEAT_H // 2))
            moving.append((c.create_image(
                x + FEAT_W // 2, FEAT_TOP + FEAT_H // 2,
                image=self._cover(game, FEAT_W, FEAT_H,
                                  dim=1.0 if sel else (0.86 if hov else 0.62))),
                x + FEAT_W // 2, FEAT_TOP + FEAT_H // 2))
            # boîte large : les wordmarks très étirés (Glaivolver) restaient
            # illisibles à 30 px de haut.
            lgx, lgy = x + 14 + 65, FEAT_TOP + FEAT_H - 28
            logo = c.create_image(lgx, lgy,
                                  image=self._load(game["logo"], size=(130, 42),
                                                   dim=1.0 if (sel or hov) else 0.85))
            if sel:
                # signature maison : le logo du projet en cours respire
                self._feat_logo = logo
                self._feat_logo_base = (lgx, lgy)
                self._feat_logo_key = ("feat", i)
            else:
                moving.append((logo, lgx, lgy))
            self._card_anim.append((("feat", i), moving, CARD_LIFT if hov else 0))
            self._game_zones.append((x, FEAT_TOP, x + FEAT_W, FEAT_TOP + FEAT_H, i))

        # ── colonne droite : carte info, pseudo, JOUER, progression
        cw = 280
        cx = W - cw - 34

        # carte info (verre)
        # Le projet, rien que le projet : le Discord et le compteur de membres
        # sont IDENTIQUES pour tous les projets, ils sont passés dans le menu
        # profil où ils ne se répètent plus.
        cy = H - 306
        card = self._flat("card2", cw, 92, (14, 20, 24, 216), radius=16)
        c.create_image(cx + cw // 2, cy + 46, image=card)
        mini = self._load(g["logo"], size=(112, 52))
        c.create_image(cx + 68, cy + 46, image=mini)
        lbl, lcol = self._online_label(g)
        self._dot_item = c.create_oval(cx + 136, cy + 24, cx + 144, cy + 32, fill=lcol, width=0)
        self._online_item = c.create_text(cx + 152, cy + 28, anchor="w", text=lbl,
                                          fill=lcol, font=self.F(10, True))
        # pas de troncature : Tk coupe aux mots avec `width`, alors qu'un [:44]
        # tranchait en plein milieu (« survis, navigue, pil »).
        c.create_text(cx + 136, cy + 42, anchor="nw", text=GT(g, "tagline", self.lang),
                      fill="#9AB0A4", font=self.F(8), width=138)

        # (compteur de membres Discord : maintenant dans le menu profil)

        # pseudo (pilule verre, champ dessiné à la main)
        # Le champ ne disait pas qu'il était cliquable : le focus ne changeait
        # aucune couleur. Survol = fond plus clair + liseré, focus = liseré
        # accent plein, et un crayon en permanence.
        iy = H - 164
        self._input_zone = (cx, iy - 19, cx + cw, iy + 19)
        phov = self.hover == "pseudo"
        if self.pseudo_focus or phov:
            c.create_image(cx + cw // 2, iy,
                           image=self._flat(
                               "inring" + g["id"] + ("f" if self.pseudo_focus else "h"),
                               cw + 4, 42,
                               self._hex(accent) + (255 if self.pseudo_focus else 140,),
                               radius=14))
        light = phov and not self.pseudo_focus
        c.create_image(cx + cw // 2, iy,
                       image=self._flat("input" + ("_h" if light else ""), cw, 38,
                                        (21, 29, 33, 255) if light else (12, 18, 21, 255),
                                        radius=12))
        self._input_text = c.create_text(cx + cw // 2 - 12, iy, text=self.pseudo_text,
                                         fill="#EAF6EF", font=self.F(12, True))
        self._input_cursor = c.create_rectangle(0, 0, 0, 0, fill=accent, width=0)
        c.create_text(cx + cw - 22, iy, text="✎",
                      fill=accent if (phov or self.pseudo_focus) else "#5E7268",
                      font=(self.FONT, 12))
        c.create_text(cx + cw // 2, iy - 30, text=self.T("pseudo"),
                      fill=accent if (phov or self.pseudo_focus) else "#7A948A",
                      font=self.F(8, True))

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

        # progression + statut
        bw3, bh3 = cw, 5
        by3 = H - 39
        self._bar_geom = (cx, by3, bw3, bh3)
        c.create_image(cx + cw // 2, by3 + bh3 // 2,
                       image=self._flat("track", bw3, bh3, (255, 255, 255, 26), radius=bh3 // 2))
        self._bar_fill = c.create_rectangle(cx, by3, cx, by3 + bh3, fill=accent, width=0)
        self._status_item = c.create_text(cx + cw // 2, by3 - 14, text=self.status.get(),
                                          fill="#C8D8CC", font=self.F(8), width=cw)

    # ── cartes : visuel recadré, coins arrondis, dégradé bas ───────────
    def _round_mask(self, w, h, radius):
        ck = ("rmask", w, h, radius)
        if ck not in self._img_cache:
            S = 4
            m = Image.new("L", (w * S, h * S), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, w * S - 1, h * S - 1),
                                                radius=radius * S, fill=255)
            self._img_cache[ck] = m.resize((w, h), Image.LANCZOS)
        return self._img_cache[ck]

    def _cover(self, game, w, h, dim=1.0, radius=12):
        """visuel de carte : `card_url` du catalogue sinon recadrage du key-art."""
        src = game.get("card") or game["bg"]
        ck = ("cover", src, w, h, dim, radius)
        if ck in self._img_cache:
            return self._img_cache[ck]
        try:
            im = Image.open(self._asset_path(src)).convert("RGB")
        except Exception:
            im = Image.new("RGB", (w, h), (18, 24, 26))
        r = max(w / im.width, h / im.height)
        im = im.resize((max(w, int(im.width * r) + 1), max(h, int(im.height * r) + 1)),
                       Image.LANCZOS)
        x0, y0 = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((x0, y0, x0 + w, y0 + h))
        if dim < 1.0:
            im = ImageEnhance.Brightness(im).enhance(dim)
        # dégradé sombre en pied de carte, pour que le logo reste lisible
        sh = Image.new("L", (1, h), 0)
        sd = ImageDraw.Draw(sh)
        for y in range(h):
            t = max(0.0, (y - h * 0.42) / (h * 0.58))
            sd.point((0, y), fill=int(225 * t * t))
        im = Image.composite(Image.new("RGB", (w, h), (5, 8, 9)), im, sh.resize((w, h)))
        im = im.convert("RGBA")
        im.putalpha(self._round_mask(w, h, radius))
        self._img_cache[ck] = ImageTk.PhotoImage(im)
        return self._img_cache[ck]

    # ── page Bibliothèque : la grille qui absorbe 20 projets ───────────
    def _lib_matches(self):
        q = self.lib_query.strip().lower()
        out = []
        for i, g in enumerate(GAMES):
            if q and q not in (g["name"] + " "
                               + str(GT(g, "tagline", self.lang, ""))).lower():
                continue
            if self.lib_filter == "installed" \
                    and not self._state().get("mod_" + g["base"].rsplit("/", 1)[1]):
                continue
            if self.lib_filter == "online" and not isinstance(
                    self._online.get(g["id"]), int):
                continue
            out.append(i)
        return out

    def _draw_filters(self, c, y, accent):
        """Tous / Installés / En ligne — indispensable passé quelques projets."""
        self._filter_zones = []
        x = SIDEBAR + 34
        for key in LIB_FILTERS:
            label = self.T("f_" + key)
            fw = 26 + tkfont.Font(family=self.FONT, size=8, weight="bold").measure(label)
            on = self.lib_filter == key
            hov = self.hover == ("filter", key)
            c.create_image(x + fw // 2, y + 13,
                           image=self._flat("flt%s%d%d" % (fw, on, hov), fw, 26,
                                            self._hex(accent) + (255,) if on
                                            else ((24, 33, 31, 235) if hov else (15, 21, 24, 215)),
                                            radius=13))
            c.create_text(x + fw // 2, y + 13, text=label,
                          fill="#06140C" if on else ("#EAF6EF" if hov else "#8AA49A"),
                          font=self.F(8, True))
            self._filter_zones.append((x, y, x + fw, y + 26, key))
            x += fw + 8

    def _band(self, top=104):
        """bande de contenu défilable, commune aux pages en liste."""
        return SIDEBAR + 34, top, W - 34, H - 30

    def _draw_library(self, c, accent):
        x0, top, x1, bottom = self._band(136)
        matches = self._lib_matches()

        rows = max(1, (len(matches) + CARD_COLS - 1) // CARD_COLS)
        span = max(0, rows * CARD_PITCH - (bottom - top))
        off = self.scroll["library"] = max(0, min(self.scroll["library"], span))

        for k, i in enumerate(matches):
            game = GAMES[i]
            cx = x0 + (k % CARD_COLS) * (CARD_W + CARD_GAP)
            cy = top + (k // CARD_COLS) * CARD_PITCH - off
            if cy > bottom or cy + CARD_PITCH < top:
                continue      # hors bande : rien à dessiner
            sel = i == self.selected
            hov = self.hover == ("game", i)
            moving = []
            if sel or hov:
                moving.append((c.create_image(
                    cx + CARD_W // 2, cy + CARD_H // 2,
                    image=self._flat("cardsel" + game["id"] + ("s" if sel else "h"),
                                     CARD_W + 6, CARD_H + 6,
                                     self._hex(accent if sel else "#5E7A70") + (255,),
                                     radius=15)), cx + CARD_W // 2, cy + CARD_H // 2))
            moving.append((c.create_image(cx + CARD_W // 2, cy + CARD_H // 2,
                                          image=self._cover(game, CARD_W, CARD_H,
                                                            dim=1.0 if (sel or hov) else 0.7)),
                           cx + CARD_W // 2, cy + CARD_H // 2))
            moving.append((c.create_image(cx + CARD_W // 2, cy + CARD_H - 32,
                                          image=self._load(game["logo"], size=(134, 46),
                                                           dim=1.0 if (sel or hov) else 0.9)),
                           cx + CARD_W // 2, cy + CARD_H - 32))
            self._card_anim.append((("lib", i), moving, CARD_LIFT if hov else 0))

            c.create_text(cx, cy + CARD_H + 16, anchor="w", text=game["name"],
                          fill="#EAF6EF" if (sel or hov) else "#C8D8CC", font=self.F(9, True))
            ver = self._mod_version(game)
            known = ver != self.T("log_unknown")
            n = self._online.get(game["id"])
            if self._has_update(game):
                badge, bcol = "↑ " + self.T("update_avail"), accent
            elif isinstance(n, int):
                badge, bcol = f"● {n} {self.T('players')}", "#5AE68C"
            elif known:
                badge, bcol = f"{self.T('installed')} · {ver}", "#7A948A"
            else:
                badge, bcol = self.T("not_installed"), "#5E7268"
            c.create_text(cx, cy + CARD_H + 32, anchor="w", text=badge[:22],
                          fill=bcol, font=self.F(8))
            self._game_zones.append((cx, max(top, cy), cx + CARD_W,
                                     min(bottom, cy + CARD_H), i))

        if not matches:
            c.create_text((x0 + x1) // 2, top + 120, text=self.T("no_results"),
                          fill="#6A7E74", font=self.F(11))
        self._scrollbar(c, x1 + 8, top, bottom, span, off, accent)

        # en-tête dessiné après la grille : il recouvre le débord du défilement
        c.create_image(0, 0, anchor="nw", image=self._header_band(128))
        c.create_text(x0, 44, anchor="w", text=self.T("nav_library"),
                      fill="#EAF6EF", font=self.F(17, True))
        c.create_text(x0, 70, anchor="w", text=self.T("lib_sub", n=len(GAMES)),
                      fill="#7A948A", font=self.F(9))
        self._draw_filters(c, 92, accent)
        self._draw_search(c, accent)

    def _header_band(self, h=96):
        """bandeau opaque du haut de page (masque la grille qui défile dessous)."""
        key = ("hband", h)
        if key not in self._img_cache:
            im = Image.new("RGBA", (W, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            for y in range(h):
                a = 255 if y < h - 18 else int(255 * (1 - (y - (h - 18)) / 18.0))
                d.line((0, y, W, y), fill=(9, 12, 14, a))
            self._img_cache[key] = ImageTk.PhotoImage(im)
        return self._img_cache[key]

    def _draw_search(self, c, accent):
        sw, sh = 240, 34
        sx, sy = W - sw - 270, 28   # à gauche du chip joueur et de la langue
        self._search_zone = (sx, sy, sx + sw, sy + sh)
        c.create_image(sx + sw // 2, sy + sh // 2,
                       image=self._flat("search" + ("_f" if self.lib_focus else ""), sw, sh,
                                        (18, 26, 29, 245) if self.lib_focus else (13, 19, 22, 225),
                                        radius=12))
        c.create_text(sx + 18, sy + sh // 2, text="⌕",
                      fill=accent if self.lib_focus else "#6A7E74", font=(self.FONT, 13))
        self._search_item = c.create_text(
            sx + 34, sy + sh // 2, anchor="w",
            text=self.lib_query or self.T("search"),
            fill="#EAF6EF" if self.lib_query else "#5E7268", font=self.F(9))

    def _scrollbar(self, c, x, top, bottom, span, off, accent):
        if span <= 0:
            return
        c.create_rectangle(x, top, x + 4, bottom, fill="#131B1D", width=0)
        h = bottom - top
        th = max(30, int(h * h / (h + span)))
        ty = top + int((h - th) * (off / span))
        c.create_rectangle(x, ty, x + 4, ty + th, fill=accent, width=0)

    # ── page Nouveautés : les news de tous les projets d'un coup ────────
    def _draw_news(self, c, accent):
        x0, top, x1, bottom = self._band()
        rowsp, y = [], 0
        for i, g in enumerate(GAMES):
            lines = (GT(g, "news", self.lang, []) or [])[:4]
            rowsp.append((i, g, lines, 44 + 20 * len(lines)))
            y += 44 + 20 * len(lines) + 14
        span = max(0, y - 14 - (bottom - top))
        off = self.scroll["news"] = max(0, min(self.scroll["news"], span))

        rw = x1 - x0
        cy = top - off
        for i, g, lines, rh in rowsp:
            if cy + rh >= top and cy <= bottom:
                hov = self.hover == ("game", i)
                c.create_image(x0 + rw // 2, cy + rh // 2,
                               image=self._flat("nrow%d%d" % (rh, hov), rw, rh,
                                                (16, 23, 26, 240) if hov else (12, 17, 20, 225),
                                                radius=14))
                c.create_image(x0 + 82, cy + 26, image=self._load(g["logo"], size=(122, 40)))
                c.create_rectangle(x0 + 20, cy + 14, x0 + 23, cy + 38,
                                   fill=g["accent"], width=0)
                for k, line in enumerate(lines):
                    c.create_text(x0 + 152, cy + 26 + k * 20, anchor="w", text="•  " + line,
                                  fill="#C8DCD0", font=self.F(9))
                if not lines:
                    c.create_text(x0 + 152, cy + 26, anchor="w", text="—",
                                  fill="#5E7268", font=self.F(9))
                self._game_zones.append((x0, max(top, cy), x0 + rw,
                                         min(bottom, cy + rh), i))
            cy += rh + 14

        self._scrollbar(c, x1 + 8, top, bottom, span, off, accent)
        c.create_image(0, 0, anchor="nw", image=self._header_band())
        c.create_text(x0, 44, anchor="w", text=self.T("nav_news"),
                      fill="#EAF6EF", font=self.F(17, True))
        c.create_text(x0, 70, anchor="w", text=self.T("news_sub"),
                      fill="#7A948A", font=self.F(9))

    # ── page Téléchargements : le job en cours + l'état des installs ────
    def _draw_downloads(self, c, accent):
        x0, top, x1, bottom = self._band()
        rw = x1 - x0
        g = GAMES[self.selected]

        # la liste d'abord : la carte du job en cours est peinte par-dessus et
        # masque le débord, comme le bandeau d'en-tête des autres pages.
        list_top = top + 112
        span = max(0, len(GAMES) * 56 - 14 - (bottom - list_top))
        off = self.scroll["downloads"] = max(0, min(self.scroll["downloads"], span))
        y = list_top - off
        for i, game in enumerate(GAMES):
            if y + 48 >= top and y <= bottom:
                hov = self.hover == ("game", i)
                c.create_image(x0 + rw // 2, y + 24,
                               image=self._flat("dlrow%d" % hov, rw, 48,
                                                (16, 23, 26, 235) if hov else (11, 16, 19, 215),
                                                radius=12))
                c.create_image(x0 + 66, y + 24, image=self._load(game["logo"], size=(100, 34)))
                ver = self._mod_version(game)
                known = ver != self.T("log_unknown")
                c.create_text(x0 + 128, y + 24, anchor="w",
                              text=(self.T("installed") + " · " + ver) if known
                              else self.T("not_installed"),
                              fill="#C8DCD0" if known else "#5E7268", font=self.F(9))
                c.create_text(x1 - 24, y + 24, anchor="e", text=game["dir"],
                              fill="#4E6058", font=self.F(8))
                self._game_zones.append((x0, max(list_top, y), x0 + rw,
                                         min(bottom, y + 48), i))
            y += 56
        self._scrollbar(c, x1 + 8, list_top, bottom, span, off, accent)

        c.create_image(x0 + rw // 2, top + 44,
                       image=self._flat("dlcur", rw, 88, (13, 19, 22, 252), radius=14))
        if self.busy:
            c.create_image(x0 + 66, top + 34, image=self._load(g["logo"], size=(92, 30)))
            c.create_text(x0 + 132, top + 26, anchor="w", text=self.T("dl_current"),
                          fill=accent, font=self.F(9, True))
            c.create_text(x0 + 132, top + 44, anchor="w", text=self.status.get(),
                          fill="#C8DCD0", font=self.F(9), width=rw - 200)
            bw, bh = rw - 48, 5
            bx, by = x0 + 24, top + 68
            c.create_image(bx + bw // 2, by + bh // 2,
                           image=self._flat("dltrack", bw, bh, (255, 255, 255, 26), radius=2))
            self._bar_geom = (bx, by, bw, bh)
            self._bar_fill = c.create_rectangle(bx, by, bx, by + bh, fill=accent, width=0)
            self._status_item = c.create_text(x1 - 24, top + 26, anchor="e", text="",
                                              fill="#7A948A", font=self.F(8))
        else:
            c.create_text(x0 + rw // 2, top + 44, text=self.T("dl_empty"),
                          fill="#6A7E74", font=self.F(10))

        c.create_image(0, 0, anchor="nw", image=self._header_band())
        c.create_text(x0, 44, anchor="w", text=self.T("nav_dl"),
                      fill="#EAF6EF", font=self.F(17, True))
        c.create_text(x0, 70, anchor="w", text=self.T("dl_sub"),
                      fill="#7A948A", font=self.F(9))

    # ── UI de chargement : ce que le joueur voit au lieu d'un terminal ──
    def _mix(self, hexcol, a):
        """couleur accent fondue vers le fond, pour un battement doux."""
        r, g, b = self._hex(hexcol)
        return "#%02x%02x%02x" % (int(r * a + 12 * (1 - a)),
                                  int(g * a + 18 * (1 - a)),
                                  int(b * a + 16 * (1 - a)))

    def _draw_installing(self, c, g):
        acc = g["accent"]
        pw, ph = 520, 176
        px, py = SIDEBAR + (W - SIDEBAR) // 2 - pw // 2, H // 2 - ph // 2
        c.create_image(0, 0, anchor="nw", image=self._dim_overlay())
        c.create_image(px + pw // 2, py + ph // 2,
                       image=self._flat("instpanel", pw, ph, (13, 18, 21, 251), radius=18))
        c.create_image(px + 24 + 66, py + 26 + 44, image=self._cover(g, 132, 88, radius=12))

        tx = px + 24 + 132 + 22
        c.create_text(tx, py + 30, anchor="w",
                      text=self.T("updating" if self.autoupdating else "installing"),
                      fill=acc, font=self.F(8, True))
        c.create_text(tx, py + 52, anchor="w", text=g["name"],
                      fill="#EAF6EF", font=self.F(14, True))
        self._inst_pct = c.create_text(px + pw - 26, py + 46, anchor="e", text="",
                                       fill=acc, font=self.F(15, True))
        self._inst_status = c.create_text(tx, py + 78, anchor="w", text=self.status.get(),
                                          fill="#9AB0A4", font=self.F(9), width=pw - 210)

        # trois points qui battent : la seule preuve visuelle « ça travaille »
        self._inst_dots = [c.create_oval(tx + k * 12 - 3, py + 102 - 3,
                                         tx + k * 12 + 3, py + 102 + 3,
                                         fill=acc, width=0) for k in range(3)]

        bw, bh = pw - 48, 6
        bx, by = px + 24, py + ph - 62
        c.create_image(bx + bw // 2, by + bh // 2,
                       image=self._flat("insttrack", bw, bh, (255, 255, 255, 28), radius=3))
        self._inst_geom = (bx, by, bw, bh)
        self._inst_bar = c.create_rectangle(bx, by, bx, by + bh, fill=acc, width=0)

        cw2, ch2 = 132, 32
        cx2, cy2 = px + pw - 24 - cw2, py + ph - 44
        self._instcancel_zone = (cx2, cy2, cx2 + cw2, cy2 + ch2)
        hov = self.hover == "instcancel"
        c.create_image(cx2 + cw2 // 2, cy2 + ch2 // 2,
                       image=self._flat("instcancel" + ("_h" if hov else ""), cw2, ch2,
                                        (52, 28, 30, 255) if hov else (26, 33, 31, 238), radius=10))
        c.create_text(cx2 + cw2 // 2, cy2 + ch2 // 2, text=self.T("cancel"),
                      fill="#F2CACA" if hov else "#B8C8BE", font=self.F(9, True))

    # ── options par jeu ───────────────────────────────────────────────
    def _opts(self, g):
        return self._state().get("opt_" + g["id"],
                                {"ram": int(conf("ram.default", 3)), "close": False})

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
        tx, ty = 20, self._studio_zone[3] + 10   # le logo est en haut du rail
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
        """molette : console du Journal si ouverte, sinon défilement de la page."""
        if getattr(e, "num", None) == 4:
            step = 3
        elif getattr(e, "num", None) == 5:
            step = -3
        else:
            step = 3 if e.delta > 0 else -3
        if self.log_open:
            self._log_scroll_by(step)
        elif self.page in self.scroll:
            before = self.scroll[self.page]
            self.scroll[self.page] = max(0, before - step * 22)
            if self.scroll[self.page] != before:
                self._draw()

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
        if (e.state & 0x0004) and e.keysym.lower() == "f":   # Ctrl+F : rechercher
            if self.page != "library":
                self._goto("library")
            self.lib_focus = True
            self._draw()
            return
        if self.lib_focus:   # recherche de la Bibliothèque
            if e.keysym == "BackSpace":
                self.lib_query = self.lib_query[:-1]
            elif e.keysym == "Escape":
                self.lib_focus, self.lib_query = False, ""
            elif e.keysym == "Return":
                self.lib_focus = False
            elif e.char and e.char.isprintable() and len(self.lib_query) < 24:
                self.lib_query += e.char
            else:
                return
            self.scroll["library"] = 0
            self._draw()
            return
        if e.keysym == "Escape" and self.page != "home" \
                and not (self.options_open or self.skin_open):
            self._goto("home")
            return
        if not self.pseudo_focus and not (self.options_open or self.skin_open) \
                and e.keysym in ("Left", "Right") and len(GAMES) > 1:
            step = -1 if e.keysym == "Left" else 1
            self._pick_game((self.selected + step) % len(GAMES))
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
        if self.busy:   # UI de chargement : modale, seul ANNULER répond
            if self._hit(self._instcancel_zone, e.x, e.y):
                self._cancel = True
            return
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
        if self.prof_open:   # menu profil : modal, il capte tout
            hit = None
            for (x0, y0, x1, y1, key) in self._prof_zones:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    hit = key
                    break
            if hit == "pseudo":
                self.prof_open = False
                self.page = "home"
                self.pseudo_focus = True
            elif hit == "skin":
                self.prof_open = False
                self.skin_open = True
                self.skin_status = ""
            elif hit == "lang":
                self.lang_open = True
            elif hit == "discord":
                self.prof_open = False
                webbrowser.open(GAMES[self.selected].get("discord",
                                                         "https://playechelon.net"))
            elif hit == "site":
                self.prof_open = False
                webbrowser.open(conf("site_url", "https://studioechelon.fr"))
            elif not self._hit(self._chip_zone, e.x, e.y):
                self.prof_open = False   # clic ailleurs : on referme
            self._draw()
            return
        if self._hit(self._chip_zone, e.x, e.y):
            self.prof_open = True
            self.lib_focus = False
            self._draw()
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
                self._set_opt(g, ram=max(int(conf("ram.min", 2)),
                                         self._opts(g).get("ram", 3) - 1))
            elif self._hit(self._ram_plus, e.x, e.y):
                self._set_opt(g, ram=min(int(conf("ram.max", 8)),
                                         self._opts(g).get("ram", 3) + 1))
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
        for (x0, y0, x1, y1, key) in self._nav_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                if key == "log":
                    self._log_show()
                else:
                    self._goto(key)
                return
        for (x0, y0, x1, y1, key) in self._filter_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self.lib_filter = key
                self.scroll["library"] = 0
                self._draw()
                return
        for (x0, y0, x1, y1, i) in self._game_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._pick_game(i)
                return
        if self._hit(self._search_zone, e.x, e.y):
            self.lib_focus = True
            self.pseudo_focus = False
            self._draw()
            return
        if self.lib_focus:
            self.lib_focus = False
            self._draw()
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
        elif hasattr(self, "_site_zone") and self.hover == "studio_site" \
                and self._hit(self._site_zone, e.x, e.y):
            webbrowser.open(conf("site_url", "https://studioechelon.fr"))

    def _zone_hover(self, e):
        """zones listées : filtres, sections du rail, cartes de jeu."""
        for (x0, y0, x1, y1, key) in self._filter_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return ("filter", key)
        for (x0, y0, x1, y1, key) in self._nav_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return ("nav", key)
        for (x0, y0, x1, y1, i) in self._game_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return ("game", i)
        return None

    def _motion(self, e):
        prev = self.hover
        self.hover = None
        if self.busy:   # pendant l'install, seul ANNULER est survolable
            if self._hit(self._instcancel_zone, e.x, e.y):
                self.hover = "instcancel"
            self.configure(cursor="hand2" if self.hover else "")
            if prev != self.hover:
                self._draw()
            return
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
            self.configure(cursor="hand2" if self.hover else "")
            if prev != self.hover:
                self._draw()
            return
        if self.prof_open:   # menu profil : hover des lignes
            for (x0, y0, x1, y1, key) in self._prof_zones:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    self.hover = ("prof", key)
                    break
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
        elif self._hit(self._input_zone, e.x, e.y):
            self.hover = "pseudo"
        elif self._hit(self._search_zone, e.x, e.y):
            self.hover = "search"
        elif self._hit(self._chip_zone, e.x, e.y):
            self.hover = "chip"
        elif self._hit(self._studio_zone, e.x, e.y) \
                or (isinstance(prev, str) and prev.startswith("studio")
                    and self._site_zone != NOZONE
                    and self._hit((self._studio_zone[0], self._studio_zone[1],
                                   self._site_zone[2], self._site_zone[3] + 12), e.x, e.y)):
            self.hover = "studio"
        else:
            self.hover = self._zone_hover(e)
        self.configure(cursor="hand2" if self.hover else "")
        # les logos + discord + studio changent d'état par redraw
        if prev != self.hover and self._fading is None \
                and (isinstance(prev, tuple) or isinstance(self.hover, tuple)
                     or (isinstance(prev, str) and prev.startswith("studio"))
                     or (isinstance(self.hover, str) and self.hover.startswith("studio"))
                     or "discord" in (prev, self.hover) or "gear" in (prev, self.hover)
                     or "lang" in (prev, self.hover) or "search" in (prev, self.hover)
                     or "chip" in (prev, self.hover)
                     or "pseudo" in (prev, self.hover)):
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

            mcv = mc_version(g)
            self.status.set(self.T("installing_mc", v=mcv))
            mll.fabric.install_fabric(mcv, g["dir"], callback=self._callbacks())
            self._check_cancel()
            fabric_version = None
            for v in mll.utils.get_installed_versions(g["dir"]):
                if "fabric" in v["id"] and mcv in v["id"]:
                    fabric_version = v["id"]
            if not fabric_version:
                raise RuntimeError("Fabric introuvable après installation")

            # Java PARTAGÉ entre les jeux : téléchargé une seule fois
            java = None
            try:
                jroot = game_root("StudioEchelon")
                jrt = java_runtime(g)
                java = mll.runtime.get_executable_path(jrt, jroot)
                if java is None:
                    self.status.set(self.T("installing_java"))
                    mll.runtime.install_jvm_runtime(jrt, jroot, callback=self._callbacks())
                    java = mll.runtime.get_executable_path(jrt, jroot)
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
                   + "/version?game_versions=[%22" + mc_version(g) + "%22]&loaders=[%22fabric%22]")
            req = urllib.request.Request(api, headers={"User-Agent": "echelon-client"})
            versions = json.load(urllib.request.urlopen(req))
            f0 = versions[0]["files"][0]
            self._download(f0["url"], os.path.join(mods, f0["filename"]), label=project)


if __name__ == "__main__":
    setup_log()
    Hub().mainloop()
