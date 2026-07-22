#!/usr/bin/env python3
"""
DON SHOT LAUNCHER — lance Don Shot sans passer par le launcher Minecraft.
Key-art plein écran, boutons du client Echelon, bootstrap auto-update.
Windows + macOS.
"""
import os, sys, math, random, shutil, threading, subprocess, uuid, json, platform
import tkinter as tk

try:
    import minecraft_launcher_lib as mll
except ImportError:
    print("pip install minecraft-launcher-lib")
    sys.exit(1)
try:
    from PIL import Image, ImageTk, ImageEnhance, ImageDraw, ImageFilter
except ImportError:
    print("pip install pillow")
    sys.exit(1)

MC_VERSION = "1.21.1"
JAVA_RUNTIME = "java-runtime-delta"
LAUNCHER_VERSION = "1.4"
UPDATE_BASE = "https://github.com/StudioEchelon/echelon-launchers/releases/download/donshot"

W, H = 640, 620
FPS_MS = 40
ACCENT, ACCENT_D = "#54E63C", "#2FA84C"
TEXT, MUTED = "#EAFFE8", "#7FA894"
INPUT_BG = "#0A160C"
CARD_C1, CARD_C2 = "#0E1A10", "#091108"

if platform.system() == "Windows":
    GAME_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "DonShot")
else:
    GAME_DIR = os.path.expanduser("~/DonShot")


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


MOD_SOURCES = [
    resource("donshot.jar"),
    os.path.expanduser("~/test/donshot/build/libs/donshot-1.0.0.jar"),   # dev mac
]

NEWS = [
    "• 35 héros uniques, armes 3D et ultis",
    "• Duels contre bots, ligues et trophées",
    "• Coffres, cartes à collectionner, Route du Don",
    "• Matchmaking instantané, zéro attente",
]


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DON SHOT")
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.status = tk.StringVar(value="Prêt au combat.")
        self.progress_val = tk.DoubleVar(value=0)
        self.busy = False
        self.hover = None
        self.t = 0.0
        self._cache = {}
        self.particles = [[random.uniform(0, W), random.uniform(0, H),
                           random.uniform(0.2, 0.7), random.randint(1, 3)] for _ in range(20)]

        self.canvas = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg="#06180A")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)

        # champ SANS chrome système : la pilule est dessinée sur le canvas,
        # l'Entry n'est qu'un texte transparent posé dedans
        self.pseudo = tk.Entry(self, font=("Arial", 13, "bold"), fg=TEXT, bg=INPUT_BG,
                               insertbackground=ACCENT, relief="flat", bd=0,
                               justify="center", highlightthickness=0)
        self.pseudo.insert(0, self._load_pseudo())

        self._draw()
        self.after(FPS_MS, self._tick)

    # ── images ────────────────────────────────────────────────────────
    @staticmethod
    def _hex(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

    def _img(self, path, size=None, dim=1.0):
        key = (path, size, dim)
        if key not in self._cache:
            im = Image.open(resource(path)).convert("RGBA")
            if size:
                im.thumbnail(size, Image.LANCZOS)
            if dim < 1.0:
                im = ImageEnhance.Brightness(im).enhance(dim)
            self._cache[key] = ImageTk.PhotoImage(im)
        return self._cache[key]

    def _bg(self):
        if "bg" not in self._cache:
            im = Image.open(resource("assets/bg.png")).convert("RGB")
            ratio = max(W / im.width, H / im.height)
            im = im.resize((int(im.width * ratio) + 1, int(im.height * ratio) + 1), Image.LANCZOS)
            x0, y0 = (im.width - W) // 2, (im.height - H) // 2
            im = im.crop((x0, y0, x0 + W, y0 + H))
            im = ImageEnhance.Brightness(im).enhance(0.85)
            # voile sombre en bas pour le contenu
            grad = Image.new("L", (1, H), 0)
            gd = ImageDraw.Draw(grad)
            for y in range(H):
                t = max(0.0, (y - H * 0.28) / (H * 0.55))
                gd.point((0, y), fill=int(200 * min(1, t)))
            grad = grad.resize((W, H))
            dark = Image.new("RGB", (W, H), (5, 14, 8))
            self._cache["bg"] = ImageTk.PhotoImage(Image.composite(dark, im, grad))
        return self._cache["bg"]

    def _flat(self, key, w, h, rgba, radius, shadow=False, top_light=False):
        """panneau/pilule FLAT moderne : coins très arrondis AA, alpha (verre),
        ombre ambiante douce optionnelle — zéro gloss, zéro bordure dure."""
        ck = ("f", key, w, h)
        if ck in self._cache:
            return self._cache[ck]
        S, pad = 4, 14
        ws, hs, ps, rs = w * S, h * S, pad * S, radius * S
        im = Image.new("RGBA", ((w + pad * 2) * S, (h + pad * 2) * S), (0, 0, 0, 0))
        if shadow:
            sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle((ps, ps + 4 * S, ps + ws, ps + hs + 5 * S),
                                                 radius=rs, fill=(0, 0, 0, 70))
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(6 * S)))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((ps, ps, ps + ws - 1, ps + hs - 1), radius=rs, fill=rgba)
        if top_light:   # micro-relief 1px en haut, à peine visible
            d.rounded_rectangle((ps + S, ps + S, ps + ws - S, ps + int(hs * 0.5)),
                                radius=rs - S, outline=(255, 255, 255, 16), width=S)
        im = im.resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
        self._cache[ck] = ImageTk.PhotoImage(im)
        return self._cache[ck]

    def _btn_frames(self, key, w, h, color, radius, n=8):
        """n images du bouton, du repos au survol : le hover FOND au lieu de sauter."""
        ck = ("bf", key, w, h)
        if ck in self._cache:
            return self._cache[ck]
        r, g, b = self._hex(color)
        frames = []
        for i in range(n):
            f = i / (n - 1)
            col = (min(255, int(r + 34 * f)), min(255, int(g + 26 * f)),
                   min(255, int(b + 34 * f)), 255)
            frames.append(self._flat(f"{key}#{i}", w, h, col, radius, top_light=True))
        self._cache[ck] = frames
        return frames

    # ── dessin ────────────────────────────────────────────────────────
    def _draw(self):
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._bg())

        self._particle_items = [
            c.create_oval(p[0], p[1], p[0] + p[3], p[1] + p[3], fill="#CFF0C8", width=0)
            for p in self.particles
        ]

        # logo du jeu
        self._logo_item = c.create_image(W // 2, 104, image=self._img("assets/logo.png", size=(330, 165)))
        self._logo_y = 104
        c.create_text(W // 2, 190, text="HERO SHOOTER",
                      fill=TEXT, font=("Arial", 11, "bold"))
        c.create_text(W // 2, 208, text="par Studio Echelon",
                      fill=MUTED, font=("Arial", 9))

        # nouveautés : verre sombre translucide, sans bordure
        card = self._flat("news", 500, 112, (14, 22, 18, 216), radius=20)
        c.create_image(W // 2, 288, image=card)
        c.create_text(W // 2 - 226, 246, anchor="w", text="NOUVEAUTÉS",
                      fill="#FFD060", font=("Helvetica", 9, "bold"))
        c.create_text(W // 2 + 226, 246, anchor="e", text="v1.0",
                      fill=MUTED, font=("Helvetica", 9))
        for i, line in enumerate(NEWS):
            c.create_text(W // 2 - 226, 268 + i * 18, anchor="w", text=line,
                          fill="#C8DCD0", font=("Helvetica", 10))

        # pseudo : pilule verre + Entry nu dedans
        iw, ih = 280, 40
        c.create_image(W // 2, 376, image=self._flat("input", iw, ih,
                                                     self._hex(INPUT_BG) + (235,), radius=ih // 2))
        c.create_window(W // 2, 376, window=self.pseudo, width=iw - 60, height=20)
        c.create_text(W // 2, 349, text="PSEUDO", fill=MUTED, font=("Helvetica", 8, "bold"))

        # bouton JOUER : flat pilule, hover en fondu (animé dans _tick)
        pw, ph = 300, 54
        px0, py0 = W // 2 - pw // 2, 414
        self._play_zone = (px0, py0, px0 + pw, py0 + ph)
        self._play_frames = self._btn_frames("play", pw, ph, ACCENT, ph // 2)
        self._play_item = c.create_image(W // 2, py0 + ph // 2, image=self._play_frames[0])
        label = "TÉLÉCHARGEMENT…" if self.busy else "▶   JOUER"
        size = 13 if self.busy else 16
        self._play_text = c.create_text(W // 2, py0 + ph // 2, text=label,
                                        fill="#06140C", font=("Helvetica", size, "bold"))

        # barre de progression : piste fine + remplissage arrondi
        bw, bh = 480, 6
        bx0, by0 = W // 2 - bw // 2, 492
        self._bar_geom = (bx0, by0, bw, bh)
        c.create_image(W // 2, by0 + bh // 2, image=self._flat("track", bw, bh,
                                                               (255, 255, 255, 26), radius=bh // 2))
        self._bar_fill = c.create_rectangle(bx0, by0, bx0, by0 + bh, fill=ACCENT, width=0)
        self._status_item = c.create_text(W // 2, 512, text=self.status.get(),
                                          fill=MUTED, font=("Arial", 10), width=W - 80)

        # pied
        c.create_text(W // 2, H - 44, width=W - 60,
                      text="🔒 Fichiers téléchargés uniquement depuis les serveurs officiels "
                           "Mojang, FabricMC et Modrinth.",
                      fill="#5A7A6A", font=("Arial", 8), justify="center")
        install = "%APPDATA%\\DonShot" if platform.system() == "Windows" else "~/DonShot"
        c.create_text(W // 2, H - 20, text=f"Minecraft {MC_VERSION} · Fabric · {install} · v{LAUNCHER_VERSION}",
                      fill="#3E5A66", font=("Arial", 8))

    # ── animation ─────────────────────────────────────────────────────
    def _tick(self):
        self.t += FPS_MS / 1000.0
        c = self.canvas

        c.coords(self._logo_item, W // 2, self._logo_y + math.sin(self.t * 1.6) * 4)

        # hover du bouton JOUER : fondu progressif (lerp), pas de saut
        target = 1.0 if (self.hover == "play" and not self.busy) else 0.0
        self._play_anim = getattr(self, "_play_anim", 0.0)
        self._play_anim += (target - self._play_anim) * 0.28
        idx = round(self._play_anim * (len(self._play_frames) - 1))
        c.itemconfig(self._play_item, image=self._play_frames[idx])

        for i, p in enumerate(self.particles):
            p[1] -= p[2]
            p[0] += math.sin(self.t * 0.7 + i) * 0.15
            if p[1] < -4:
                p[0], p[1] = random.uniform(0, W), H + 4
            it = self._particle_items[i]
            c.coords(it, p[0], p[1], p[0] + p[3], p[1] + p[3])

        bx0, by0, bw, bh = self._bar_geom
        frac = max(0.0, min(1.0, self.progress_val.get() / 100.0))
        c.coords(self._bar_fill, bx0, by0, bx0 + bw * frac, by0 + bh)
        c.itemconfig(self._status_item, text=self.status.get())

        self.after(FPS_MS, self._tick)

    # ── interactions ──────────────────────────────────────────────────
    def _click(self, e):
        if self._hit(self._play_zone, e.x, e.y):
            self.launch()

    def _motion(self, e):
        self.hover = "play" if self._hit(self._play_zone, e.x, e.y) else None
        self.configure(cursor="hand2" if self.hover and not self.busy else "")

    @staticmethod
    def _hit(zone, x, y):
        return zone[0] <= x <= zone[2] and zone[1] <= y <= zone[3]

    # ── persistance ───────────────────────────────────────────────────
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

    # ── bootstrap ─────────────────────────────────────────────────────
    def _fetch_manifest(self):
        import urllib.request
        try:
            req = urllib.request.Request(UPDATE_BASE + "/manifest.json",
                                         headers={"User-Agent": "donshot-launcher"})
            return json.load(urllib.request.urlopen(req, timeout=8))
        except Exception:
            return None

    def _sync_mod(self, mods, manifest):
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
        if not os.path.exists(target):
            src = next((s for s in MOD_SOURCES if os.path.exists(s)), None)
            if not src:
                raise RuntimeError("harbor.jar introuvable et pas de connexion.")
            shutil.copy(src, target)

    def _self_update(self, manifest):
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


    # ── mods communs Echelon (EchelonSkin…) : mêmes canaux que le hub ──
    EXTRAS = [("echelonskin", "echelonskin.jar")]

    def _sync_extras(self, mods):
        import urllib.request, hashlib
        root = UPDATE_BASE.rsplit("/", 1)[0]
        for channel, fname in self.EXTRAS:
            target = os.path.join(mods, fname)
            try:
                req = urllib.request.Request(root + "/" + channel + "/manifest.json",
                                             headers={"User-Agent": "echelon-launcher"})
                m = json.load(urllib.request.urlopen(req, timeout=8))
            except Exception:
                continue
            want = m.get("mod_version", "")
            have = self._state().get("mod_" + channel, "")
            if want == have and os.path.exists(target):
                continue
            self.status.set(f"Téléchargement de {channel}…")
            tmp = target + ".new"
            req = urllib.request.Request(root + "/" + channel + "/" + m.get("mod_file", fname),
                                         headers={"User-Agent": "echelon-launcher"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            sha = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
            if m.get("mod_sha256") and sha != m["mod_sha256"]:
                os.remove(tmp)
                continue
            shutil.move(tmp, target)
            self._save_state(**{"mod_" + channel: want})

    # ── lancement ─────────────────────────────────────────────────────
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
        self._draw()
        threading.Thread(target=self._launch_thread, daemon=True).start()

    def _launch_thread(self):
        try:
            pseudo = (self.pseudo.get().strip() or "Joueur")[:16]
            self._save_pseudo(pseudo)
            os.makedirs(GAME_DIR, exist_ok=True)

            self.status.set(f"Installation de Minecraft {MC_VERSION} + Fabric…")
            mll.fabric.install_fabric(MC_VERSION, GAME_DIR, callback=self._callbacks())
            fabric_version = None
            for v in mll.utils.get_installed_versions(GAME_DIR):
                if "fabric" in v["id"] and MC_VERSION in v["id"]:
                    fabric_version = v["id"]
            if not fabric_version:
                raise RuntimeError("Fabric introuvable après installation")

            java = None
            try:
                java = mll.runtime.get_executable_path(JAVA_RUNTIME, GAME_DIR)
                if java is None:
                    self.status.set("Installation de Java 21 (Mojang)…")
                    mll.runtime.install_jvm_runtime(JAVA_RUNTIME, GAME_DIR, callback=self._callbacks())
                    java = mll.runtime.get_executable_path(JAVA_RUNTIME, GAME_DIR)
            except Exception:
                java = None

            manifest = self._fetch_manifest()
            if self._self_update(manifest):
                return
            mods = os.path.join(GAME_DIR, "mods")
            os.makedirs(mods, exist_ok=True)
            self._sync_mod(mods, manifest)
            self._ensure_deps(mods)
            self._sync_extras(mods)

            self.status.set("Chargement du champ de bataille…")
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
            self.status.set("Bon frag ! (tu peux fermer le launcher)")
            subprocess.Popen(cmd, cwd=GAME_DIR)
        except Exception as e:
            self.status.set(f"Erreur : {e}")
        finally:
            self.busy = False
            self.after(0, self._draw)

    def _ensure_deps(self, mods):
        import urllib.request
        for f in os.listdir(mods):
            if f.startswith("firstperson"):   # retiré à distance
                os.remove(os.path.join(mods, f))
        deps = {"fabric-api": "fabric-api", "geckolib": "geckolib", "sodium": "sodium",
                "lithium": "lithium", "notenoughanimations": "not-enough-animations",
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
