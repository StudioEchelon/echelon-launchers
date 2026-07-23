#!/usr/bin/env python3
"""
HARBOR LAUNCHER — lance Harbor sans passer par le launcher Minecraft.
Key-art plein écran, boutons du client Echelon, bootstrap auto-update.
Windows + macOS.
"""
import os, sys, math, random, shutil, threading, subprocess, uuid, json, platform
import collections
import tkinter as tk

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
UPDATE_BASE = "https://github.com/StudioEchelon/echelon-launchers/releases/download/harbor"

W, H = 640, 620
FPS_MS = 40
ACCENT, ACCENT_D = "#5AE68C", "#2E7B4C"
TEXT, MUTED = "#EAF6EF", "#9AC8B0"
INPUT_BG = "#0C161C"
CARD_C1, CARD_C2 = "#10191F", "#0B1218"

if platform.system() == "Windows":
    GAME_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "Harbor")
else:
    GAME_DIR = os.path.expanduser("~/Harbor")


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


MOD_SOURCES = [
    resource("harbor.jar"),
    os.path.expanduser("~/test/harbor-mod/build/libs/donshot-1.0.0.jar"),   # dev mac
]

NEWS = [
    "• Ton raft navigue au vent — océan vivant, houle réelle",
    "• 10 donjons pirates, Kraken, Capitaine Sans-Tête",
    "• Cartes au trésor, canons, armure Zircon à 4 modes",
    "• Voix de proximité, emotes, clans et HarborOS",
]


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HARBOR")
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.status = tk.StringVar(value="Prêt à lever l'ancre.")
        self.progress_val = tk.DoubleVar(value=0)
        self.busy = False
        self.hover = None
        # page Journal : sortie du jeu (GAME_LOG), scroll + auto-suivi
        self.log_open = False
        self.log_off = 0          # nb de lignes remontées depuis le bas (0 = suit)
        self.log_status = ""
        self._log_job = None
        self._log_items = []
        self._log_drag_y = None
        self._java_path = None
        self.t = 0.0
        self._cache = {}
        self.particles = [[random.uniform(0, W), random.uniform(0, H),
                           random.uniform(0.2, 0.7), random.randint(1, 3)] for _ in range(20)]

        self.canvas = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg="#06121A")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)
        # molette + glissement : uniquement utiles à la page Journal
        self.canvas.bind("<MouseWheel>", self._log_wheel)          # Windows / macOS
        self.canvas.bind("<Button-4>", self._log_wheel)            # Linux
        self.canvas.bind("<Button-5>", self._log_wheel)
        self.canvas.bind("<B1-Motion>", self._log_drag)
        self.canvas.bind("<ButtonRelease-1>", self._log_drag_end)
        self.bind("<MouseWheel>", self._log_wheel)
        self.bind("<Escape>", self._log_hide)

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
            dark = Image.new("RGB", (W, H), (5, 12, 16))
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
            c.create_oval(p[0], p[1], p[0] + p[3], p[1] + p[3], fill="#C8E8D4", width=0)
            for p in self.particles
        ]

        # logo du jeu
        self._logo_item = c.create_image(W // 2, 104, image=self._img("assets/logo.png", size=(330, 165)))
        self._logo_y = 104
        c.create_text(W // 2, 190, text="RAFT  ×  SEA OF THIEVES",
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
        if not self.log_open:   # sinon l'Entry natif flotte au-dessus du Journal
            c.create_window(W // 2, 376, window=self.pseudo, width=iw - 60, height=20)
        c.create_text(W // 2, 349, text="PSEUDO", fill=MUTED, font=("Helvetica", 8, "bold"))

        # bouton JOUER : flat pilule, hover en fondu (animé dans _tick)
        pw, ph = 300, 54
        px0, py0 = W // 2 - pw // 2, 414
        self._play_zone = (px0, py0, px0 + pw, py0 + ph)
        self._play_frames = self._btn_frames("play", pw, ph, ACCENT, ph // 2)
        self._play_item = c.create_image(W // 2, py0 + ph // 2, image=self._play_frames[0])
        label = "TÉLÉCHARGEMENT…" if self.busy else "⛵   LEVER L'ANCRE"
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

        # bouton Journal (discret, coin haut-droit)
        jw, jh = 92, 26
        jx, jy = W - jw - 16, 16
        self._log_btn_zone = (jx, jy, jx + jw, jy + jh)
        c.create_image(jx + jw // 2, jy + jh // 2,
                       image=self._flat("logbtn", jw, jh, (12, 20, 23, 205), radius=13))
        c.create_text(jx + jw // 2, jy + jh // 2, text="▤  JOURNAL",
                      fill=MUTED, font=("Helvetica", 8, "bold"))

        if self.log_open:
            self._draw_log(c)

        # pied
        c.create_text(W // 2, H - 44, width=W - 60,
                      text="🔒 Fichiers téléchargés uniquement depuis les serveurs officiels "
                           "Mojang, FabricMC et Modrinth.",
                      fill="#5A7A6A", font=("Arial", 8), justify="center")
        install = "%APPDATA%\\Harbor" if platform.system() == "Windows" else "~/Harbor"
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

    # ── page Journal (sortie du jeu) ──────────────────────────────────
    LOG_LH = 14
    LOG_MAXC = 88

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

    def _log_dir(self):
        return os.path.join(GAME_DIR, "logs")

    def _dim(self):
        if "dim" not in self._cache:
            self._cache["dim"] = ImageTk.PhotoImage(Image.new("RGBA", (W, H), (4, 7, 8, 170)))
        return self._cache["dim"]

    def _open_path(self, path):
        """ouvre un dossier (sans rouvrir de console Windows)."""
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

    def _draw_log(self, c):
        """console du jeu : en-tête diagnostic + lignes colorées + actions."""
        pw, ph = W - 48, H - 96
        px, py = 24, 48
        c.create_image(0, 0, anchor="nw", image=self._dim())
        c.create_image(px + pw // 2, py + ph // 2,
                       image=self._flat("logpanel", pw, ph, (13, 18, 21, 248), radius=16))

        c.create_text(px + 22, py + 26, anchor="w", text="JOURNAL",
                      fill=TEXT, font=("Helvetica", 12, "bold"))
        c.create_text(px + 22, py + 44, anchor="w",
                      text="sortie du jeu — utile pour signaler un bug",
                      fill=MUTED, font=("Helvetica", 8))

        java = self._java_path or "inconnu"
        if len(java) > 60:
            java = "…" + java[-59:]
        folder = GAME_DIR
        if len(folder) > 60:
            folder = "…" + folder[-59:]
        infos = ["Mod : " + (self._state().get("mod_version") or "inconnu")
                 + "   ·   Launcher v" + LAUNCHER_VERSION + "   ·   MC " + MC_VERSION,
                 "Dossier : " + folder,
                 "Java : " + java]
        for i, line in enumerate(infos):
            c.create_text(px + 22, py + 68 + i * 14, anchor="w", text=line,
                          fill="#6A7E74", font=("Helvetica", 8))

        lx, ly = px + 18, py + 116
        lw, lh = pw - 36, ph - 116 - 62
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
            c.create_text(lx + lw // 2, ly + lh // 2 - 10,
                          text="Aucun journal — lance le jeu d'abord.",
                          fill=MUTED, font=("Helvetica", 10, "bold"))
            if os.path.exists(os.path.join(self._log_dir(), "launcher-game.log")):
                c.create_text(lx + lw // 2, ly + lh // 2 + 14,
                              text="Un fichier de la session précédente existe : "
                                   "logs/launcher-game.log",
                              fill="#5A6E64", font=("Helvetica", 8), width=lw - 60,
                              justify="center")

        by = py + ph - 46
        self._logcopy_zone = (px + 18, by, px + 18 + 110, by + 30)
        c.create_image(px + 18 + 55, by + 15,
                       image=self._flat("logcopy", 110, 30, (32, 42, 38, 255), radius=10))
        c.create_text(px + 18 + 55, by + 15, text="COPIER", fill=TEXT,
                      font=("Helvetica", 9, "bold"))

        self._logfolder_zone = (px + 140, by, px + 140 + 170, by + 30)
        c.create_image(px + 140 + 85, by + 15,
                       image=self._flat("logfolder", 170, 30, (32, 42, 38, 255), radius=10))
        c.create_text(px + 140 + 85, by + 15, text="OUVRIR LE DOSSIER", fill=TEXT,
                      font=("Helvetica", 9, "bold"))

        if self.log_status:
            c.create_text(px + 322, by + 15, anchor="w", text=self.log_status,
                          fill=ACCENT, font=("Helvetica", 9))

        self._logclose_zone = (px + pw - 138, by, px + pw - 18, by + 30)
        c.create_image(px + pw - 78, by + 15,
                       image=self._flat("logclose", 120, 30, self._hex(ACCENT) + (255,), radius=10))
        c.create_text(px + pw - 78, by + 15, text="FERMER", fill="#06140C",
                      font=("Helvetica", 10, "bold"))

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
                c.itemconfig(item, text=chunk[i][:self.LOG_MAXC], fill=self._log_color(chunk[i]))
            else:
                c.itemconfig(item, text="")
        lx, ly, lw, lh = self._log_area
        if total > vis:
            th = max(24, int((lh - 16) * vis / total))
            pos = start / max(1, total - vis)
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

    def _log_hide(self, *_):
        if not self.log_open:
            return
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
        if not self.log_open:
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
            self.log_status = "Journal copié !"
        except Exception:
            self.log_status = ""

    # ── interactions ──────────────────────────────────────────────────
    def _click(self, e):
        if self.log_open:   # modal : la page Journal capte tout
            if self._hit(self._logcopy_zone, e.x, e.y):
                self._log_copy()
                self._draw()
            elif self._hit(self._logfolder_zone, e.x, e.y):
                self._open_path(self._log_dir())
            elif self._hit(self._logclose_zone, e.x, e.y):
                self._log_hide()
            return
        if self._hit(self._log_btn_zone, e.x, e.y):
            self._log_show()
        elif self._hit(self._play_zone, e.x, e.y):
            self.launch()

    def _motion(self, e):
        if self.log_open:
            over = any(self._hit(z, e.x, e.y) for z in
                       (self._logcopy_zone, self._logfolder_zone, self._logclose_zone))
            self.configure(cursor="hand2" if over else "")
            return
        self.hover = "play" if self._hit(self._play_zone, e.x, e.y) else None
        if self._hit(self._log_btn_zone, e.x, e.y):
            self.configure(cursor="hand2")
            return
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
        return self._state().get("pseudo", "Marin")

    def _save_pseudo(self, p):
        self._save_state(pseudo=p)

    # ── bootstrap ─────────────────────────────────────────────────────
    def _fetch_manifest(self):
        import urllib.request
        try:
            req = urllib.request.Request(UPDATE_BASE + "/manifest.json",
                                         headers={"User-Agent": "harbor-launcher"})
            return json.load(urllib.request.urlopen(req, timeout=8))
        except Exception:
            return None

    def _sync_mod(self, mods, manifest):
        import urllib.request, hashlib
        target = os.path.join(mods, "harbor.jar")
        if manifest:
            want = manifest.get("mod_version", "")
            have = self._state().get("mod_version", "")
            # re-télécharge si version différente, jar absent, OU jar présent mais
            # SHA != manifeste (débloque un état coincé : version notée à jour mais
            # jar réellement ancien/corrompu — la cause des "maj pas prise").
            wantSha = manifest.get("mod_sha256", "")
            haveSha = ""
            if os.path.exists(target):
                try:
                    haveSha = hashlib.sha256(open(target, "rb").read()).hexdigest()
                except Exception:
                    haveSha = ""
            if want != have or not os.path.exists(target) or (wantSha and haveSha != wantSha):
                self.status.set(f"Mise à jour du mod Harbor ({want})…")
                tmp = target + ".new"
                req = urllib.request.Request(UPDATE_BASE + "/" + manifest.get("mod_file", "harbor.jar"),
                                             headers={"User-Agent": "harbor-launcher"})
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
                                         headers={"User-Agent": "harbor-launcher"})
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
            pseudo = (self.pseudo.get().strip() or "Marin")[:16]
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
            self._java_path = java or "system PATH"

            manifest = self._fetch_manifest()
            if self._self_update(manifest):
                return
            mods = os.path.join(GAME_DIR, "mods")
            os.makedirs(mods, exist_ok=True)
            self._sync_mod(mods, manifest)
            self._ensure_deps(mods)
            self._sync_extras(mods)

            self.status.set("Largage des amarres…")
            options = {
                "username": pseudo,
                "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, "harbor:" + pseudo)),
                "token": "0",
                "jvmArguments": ["-Xmx3G"],
            }
            if java:
                options["executablePath"] = java
            cmd = mll.command.get_minecraft_command(fabric_version, GAME_DIR, options)
            self.progress_val.set(100)
            self.status.set("Bon vent, marin ! (tu peux fermer le launcher)")
            launch_game(cmd, GAME_DIR)
        except Exception as e:
            self.status.set(f"Erreur : {e}")
        finally:
            self.busy = False
            self.after(0, self._draw)

    def _ensure_deps(self, mods):
        import urllib.request
        deps = {"fabric-api": "fabric-api", "sodium": "sodium", "lithium": "lithium"}
        for prefix, project in deps.items():
            if any(f.startswith(prefix) for f in os.listdir(mods)):
                continue
            self.status.set(f"Téléchargement de {project}…")
            api = ("https://api.modrinth.com/v2/project/" + project
                   + "/version?game_versions=[%22" + MC_VERSION + "%22]&loaders=[%22fabric%22]")
            req = urllib.request.Request(api, headers={"User-Agent": "harbor-launcher"})
            versions = json.load(urllib.request.urlopen(req))
            f0 = versions[0]["files"][0]
            urllib.request.urlretrieve(f0["url"], os.path.join(mods, f0["filename"]))


if __name__ == "__main__":
    Launcher().mainloop()
