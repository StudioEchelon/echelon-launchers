#!/usr/bin/env python3
"""
DON SHOT LAUNCHER — lance Don Shot sans passer par le launcher Minecraft.
Télécharge MC 1.21.1 + Fabric depuis les serveurs officiels Mojang/Fabric,
installe le mod, et lance le jeu direct avec ton pseudo.
"""
import os, sys, shutil, threading, subprocess, uuid, json, platform
import tkinter as tk
from tkinter import ttk

try:
    import minecraft_launcher_lib as mll
except ImportError:
    print("pip3 install minecraft-launcher-lib")
    sys.exit(1)

MC_VERSION = "1.21.1"
JAVA_RUNTIME = "java-runtime-delta"   # Java 21 officiel Mojang (MC 1.21)
LAUNCHER_VERSION = "1.1"
# bootstrap : manifest + jar publiés sur GitHub Releases (tag roulant "donshot")
UPDATE_BASE = "https://github.com/StudioEchelon/echelon-launchers/releases/download/donshot"

if platform.system() == "Windows":
    GAME_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "DonShot")
else:
    GAME_DIR = os.path.expanduser("~/DonShot")


def resource(name):
    """fichier embarqué (PyInstaller) ou à côté du script."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


MOD_SOURCES = [
    resource("donshot.jar"),
    os.path.expanduser("~/test/donshot/build/libs/donshot-1.0.0.jar"),
]
FABRIC_API_URL = None   # auto via modrinth si besoin

# ── palette Don Shot
BG = "#06180A"; PANEL = "#0E1216"; GREEN = "#54E63C"; GREEN_D = "#2FA84C"
TEXT = "#EAFFE8"; MUTED = "#7FA894"; GOLD = "#E6B23C"


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DON SHOT")
        self.geometry("520x420")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.status = tk.StringVar(value="Prêt.")
        self.progress_val = tk.DoubleVar(value=0)
        self.busy = False
        self._build_ui()

    def _build_ui(self):
        self.geometry("560x560")

        # ── header : logo + titre
        header = tk.Frame(self, bg=BG)
        header.pack(pady=(22, 0))
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            try:
                img = tk.PhotoImage(file=logo_path)
                k = max(1, img.width() // 96)
                self._logo = img.subsample(k, k)
                tk.Label(header, image=self._logo, bg=BG).pack()
            except Exception:
                pass
        tk.Label(header, text="DON SHOT", font=("Arial Black", 30, "bold"), fg=GREEN, bg=BG).pack()
        tk.Label(header, text="HERO SHOOTER — par Studio Echelon", font=("Arial", 10), fg=MUTED, bg=BG).pack()

        # ── nouveautés
        news = tk.Frame(self, bg=PANEL, padx=16, pady=10)
        news.pack(pady=(16, 0), padx=34, fill="x")
        tk.Label(news, text="◆ NOUVEAUTÉS  v1.0", font=("Arial", 9, "bold"), fg=GREEN, bg=PANEL).pack(anchor="w")
        for line in ("• 10 héros uniques, armes 3D et ultis",
                     "• Duels contre bots, ligues et trophées",
                     "• Coffres, cartes à collectionner, Route du Don"):
            tk.Label(news, text=line, font=("Arial", 10), fg=TEXT, bg=PANEL,
                     justify="left").pack(anchor="w", pady=1)

        # ── carte de lancement
        frame = tk.Frame(self, bg=PANEL, padx=24, pady=18,
                         highlightbackground=GREEN_D, highlightthickness=1)
        frame.pack(pady=14, padx=34, fill="x")

        tk.Label(frame, text="PSEUDO", font=("Arial", 10, "bold"), fg=MUTED, bg=PANEL).pack(anchor="w")
        self.pseudo = tk.Entry(frame, font=("Arial", 15), fg=TEXT, bg=BG,
                               insertbackground=GREEN, relief="flat", justify="center",
                               highlightbackground=GREEN_D, highlightthickness=1)
        self.pseudo.insert(0, self._load_pseudo())
        self.pseudo.pack(fill="x", ipady=7, pady=(4, 14))

        self.play = tk.Button(frame, text="▶   JOUER", font=("Arial Black", 17, "bold"),
                              fg=BG, bg=GREEN, activebackground=GREEN_D, relief="flat",
                              cursor="hand2", command=self.launch)
        self.play.pack(fill="x", ipady=9)
        self.play.bind("<Enter>", lambda e: self.play.configure(bg=GREEN_D))
        self.play.bind("<Leave>", lambda e: self.play.configure(bg=GREEN))

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
            style.configure("green.Horizontal.TProgressbar", troughcolor=BG,
                            background=GREEN, bordercolor=PANEL, lightcolor=GREEN, darkcolor=GREEN)
            self.bar = ttk.Progressbar(frame, variable=self.progress_val, maximum=100,
                                       style="green.Horizontal.TProgressbar")
        except Exception:
            self.bar = ttk.Progressbar(frame, variable=self.progress_val, maximum=100)
        self.bar.pack(fill="x", pady=(14, 4))
        tk.Label(frame, textvariable=self.status, font=("Arial", 10),
                 fg=MUTED, bg=PANEL, wraplength=440).pack(anchor="w")

        # ── pied : réassurance
        foot = tk.Frame(self, bg=BG)
        foot.pack(side="bottom", pady=10)
        tk.Label(foot, text="🔒 Fichiers du jeu téléchargés uniquement depuis les serveurs officiels "
                            "Mojang, FabricMC et Modrinth.",
                 font=("Arial", 9), fg=MUTED, bg=BG, wraplength=480).pack()
        tk.Label(foot, text=f"Minecraft {MC_VERSION} · Fabric · installé dans ~/DonShot · v1.0",
                 font=("Arial", 9), fg="#4A6456", bg=BG).pack()

    # ── persistance pseudo
    def _cfg(self): return os.path.join(GAME_DIR, "launcher.json")

    def _state(self):
        try:
            return json.load(open(self._cfg()))
        except Exception:
            return {}

    def _save_state(self, **kv):
        os.makedirs(GAME_DIR, exist_ok=True)
        st = self._state()
        st.update(kv)
        json.dump(st, open(self._cfg(), "w"))

    def _load_pseudo(self):
        return self._state().get("pseudo", "Joueur")

    def _save_pseudo(self, p):
        self._save_state(pseudo=p)

    # ── bootstrap : manifest distant, MàJ du mod et du launcher ───────
    def _fetch_manifest(self):
        import urllib.request
        try:
            req = urllib.request.Request(UPDATE_BASE + "/manifest.json",
                                         headers={"User-Agent": "donshot-launcher"})
            return json.load(urllib.request.urlopen(req, timeout=8))
        except Exception:
            return None   # hors-ligne : on joue avec ce qu'on a

    def _sync_mod(self, mods, manifest):
        """télécharge/valide le jar du mod selon le manifest (sha256 vérifié)."""
        import urllib.request, hashlib
        target = os.path.join(mods, "donshot.jar")
        if manifest:
            want = manifest.get("mod_version", "")
            have = self._state().get("mod_version", "")
            if want != have or not os.path.exists(target):
                self.status.set(f"Mise à jour de Don Shot ({want})…")
                tmp = target + ".new"
                req = urllib.request.Request(UPDATE_BASE + "/" + manifest.get("mod_file", "donshot.jar"),
                                             headers={"User-Agent": "donshot-launcher"})
                with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                    shutil.copyfileobj(r, f)
                sha = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
                if manifest.get("mod_sha256") and sha != manifest["mod_sha256"]:
                    os.remove(tmp)
                    raise RuntimeError("Mod corrompu (sha256) — réessaie.")
                shutil.move(tmp, target)
                self._save_state(mod_version=want)
                return
        if not os.path.exists(target):   # premier lancement hors-ligne : jar embarqué
            src = next((s for s in MOD_SOURCES if os.path.exists(s)), None)
            if not src:
                raise RuntimeError("donshot.jar introuvable et pas de connexion.")
            shutil.copy(src, target)

    def _self_update(self, manifest):
        """le launcher se remplace lui-même si une version plus récente est publiée."""
        if not manifest or not getattr(sys, "frozen", False):
            return False
        try:
            def v(s): return tuple(int(x) for x in str(s).split("."))
            if v(manifest.get("launcher_version", "0")) <= v(LAUNCHER_VERSION):
                return False
            import urllib.request
            exe = sys.executable
            new = exe + ".new"
            self.status.set("Mise à jour du launcher…")
            req = urllib.request.Request(manifest["launcher_url_win"],
                                         headers={"User-Agent": "donshot-launcher"})
            with urllib.request.urlopen(req, timeout=120) as r, open(new, "wb") as f:
                shutil.copyfileobj(r, f)
            bat = os.path.join(GAME_DIR, "update.bat")
            with open(bat, "w") as f:
                f.write(f'''@echo off
timeout /t 2 /nobreak >nul
move /y "{new}" "{exe}" >nul
start "" "{exe}"
del "%~f0"
''')
            subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
            self.after(200, self.destroy)
            return True
        except Exception:
            return False

    # ── progression mll
    def _callbacks(self):
        state = {"max": 100}
        return {
            "setStatus": lambda s: self.status.set(s),
            "setProgress": lambda v: self.progress_val.set(v / max(1, state["max"]) * 100),
            "setMax": lambda m: state.update(max=m),
        }

    def launch(self):
        if self.busy:
            return
        self.busy = True
        self.play.configure(state="disabled", text="TÉLÉCHARGEMENT…", font=("Arial Black", 13, "bold"))
        threading.Thread(target=self._launch_thread, daemon=True).start()

    def _launch_thread(self):
        try:
            pseudo = (self.pseudo.get().strip() or "Joueur")[:16]
            self._save_pseudo(pseudo)
            os.makedirs(GAME_DIR, exist_ok=True)

            # 1) Fabric + Minecraft (téléchargés depuis les serveurs officiels)
            self.status.set(f"Installation de Minecraft {MC_VERSION} + Fabric…")
            mll.fabric.install_fabric(MC_VERSION, GAME_DIR, callback=self._callbacks())
            fabric_version = None
            for v in mll.utils.get_installed_versions(GAME_DIR):
                if "fabric" in v["id"] and MC_VERSION in v["id"]:
                    fabric_version = v["id"]
            if not fabric_version:
                raise RuntimeError("Fabric introuvable après installation")

            # 1 bis) Java 21 officiel Mojang (pas besoin de Java installé — Windows friendly)
            java = None
            try:
                java = mll.runtime.get_executable_path(JAVA_RUNTIME, GAME_DIR)
                if java is None:
                    self.status.set("Installation de Java 21 (Mojang)…")
                    mll.runtime.install_jvm_runtime(JAVA_RUNTIME, GAME_DIR, callback=self._callbacks())
                    java = mll.runtime.get_executable_path(JAVA_RUNTIME, GAME_DIR)
            except Exception:
                java = None   # repli : Java du système

            # 2) bootstrap : manifest distant → MàJ launcher / mod, puis dépendances
            manifest = self._fetch_manifest()
            if self._self_update(manifest):
                return   # le nouveau launcher redémarre tout seul
            mods = os.path.join(GAME_DIR, "mods")
            os.makedirs(mods, exist_ok=True)
            self._sync_mod(mods, manifest)
            self._ensure_fabric_api(mods)

            # 3) lancement (session locale)
            self.status.set("Lancement de Don Shot…")
            options = {
                "username": pseudo,
                "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, "donshot:" + pseudo)),
                "token": "0",
                "jvmArguments": ["-Xmx3G"],
            }
            if java:
                options["executablePath"] = java
            cmd = mll.command.get_minecraft_command(fabric_version, GAME_DIR, options)
            self.progress_val.set(100)
            self.status.set("Bon jeu ! (tu peux fermer le launcher)")
            subprocess.Popen(cmd, cwd=GAME_DIR)
        except Exception as e:
            self.status.set(f"Erreur : {e}")
        finally:
            self.busy = False
            self.play.configure(state="normal", text="▶   JOUER", font=("Arial Black", 17, "bold"))

    def _ensure_fabric_api(self, mods):
        """Télécharge les dépendances (Fabric API, GeckoLib) depuis Modrinth si absentes."""
        import urllib.request
        deps = {"fabric-api": "fabric-api", "geckolib": "geckolib", "sodium": "sodium", "lithium": "lithium",
                "notenoughanimations": "not-enough-animations", "firstperson": "first-person-model",
                "PresenceFootsteps": "presence-footsteps"}
        for prefix, project in deps.items():
            if any(f.startswith(prefix) for f in os.listdir(mods)):
                continue
            self.status.set(f"Téléchargement de {project}…")
            api = ("https://api.modrinth.com/v2/project/" + project
                   + "/version?game_versions=[%22" + MC_VERSION + "%22]&loaders=[%22fabric%22]")
            req = urllib.request.Request(api, headers={"User-Agent": "donshot-launcher"})
            versions = json.load(urllib.request.urlopen(req))
            f0 = versions[0]["files"][0]
            urllib.request.urlretrieve(f0["url"], os.path.join(mods, f0["filename"]))


if __name__ == "__main__":
    Launcher().mainloop()
