#!/usr/bin/env python3
"""
STUDIO ECHELON CLIENT — le hub des jeux Echelon, façon SKGames :
sidebar de logos, key-art plein écran par jeu, animations (crossfade,
particules, respiration du logo), carte Discord, gros JOUER.
JOUER télécharge (1re fois) puis lance le launcher du jeu — chaque
launcher gère ensuite ses propres mises à jour (bootstrap).
"""
import os, sys, math, random, json, platform, subprocess, threading, webbrowser
import tkinter as tk

try:
    from PIL import Image, ImageTk, ImageEnhance, ImageDraw
except ImportError:
    print("pip install pillow")
    sys.exit(1)

W, H = 1180, 700
SIDEBAR = 210
FPS_MS = 40          # ~25 fps

if platform.system() == "Windows":
    HUB_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "StudioEchelon")
else:
    HUB_DIR = os.path.expanduser("~/StudioEchelon")

RELEASES = "https://github.com/StudioEchelon/echelon-launchers/releases/download"


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


GAMES = [
    {
        "id": "harbor",
        "name": "HARBOR",
        "tagline": "Raft × Sea of Thieves — survis, navigue, pille.",
        "accent": "#5AE68C",
        "accent_dim": "#2E7B4C",
        "logo": "assets/harbor_logo.png",
        "bg": "assets/harbor_bg.png",
        "exe": "HarborLauncher.exe",
        "exe_url": RELEASES + "/harbor/HarborLauncher.exe",
        "dev_launcher": os.path.expanduser("~/test/harbor-launcher/launcher.py"),
        "discord": "https://playechelon.net",
    },
    {
        "id": "donshot",
        "name": "DON SHOT",
        "tagline": "Hero shooter — 35 héros, duels, ligues.",
        "accent": "#54E63C",
        "accent_dim": "#2FA84C",
        "logo": "assets/donshot_logo.png",
        "bg": "assets/donshot_bg.png",
        "exe": "DonShotLauncher.exe",
        "exe_url": RELEASES + "/donshot/DonShotLauncher.exe",
        "dev_launcher": os.path.expanduser("~/test/donshot-launcher/launcher.py"),
        "discord": "https://playechelon.net",
    },
]

BG = "#0A0C0E"
FADE_STEPS = 7


class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Studio Echelon")
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.selected = 0
        self.status = tk.StringVar(value="")
        self._img_cache = {}
        self._fade_cache = {}
        self._fading = None          # (frames, idx)
        self.hover = None            # "play" | "discord" | ("logo", i)
        self.t = 0.0
        self.particles = [[random.uniform(SIDEBAR, W), random.uniform(0, H),
                           random.uniform(0.25, 0.9), random.randint(1, 3)] for _ in range(26)]
        self.canvas = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg=BG)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)
        self._draw()
        self.after(FPS_MS, self._tick)

    # ── images ────────────────────────────────────────────────────────
    def _load(self, path, size=None, dim=1.0):
        key = (path, size, dim)
        if key not in self._img_cache:
            im = Image.open(resource(path)).convert("RGBA")
            if size:
                im.thumbnail(size, Image.LANCZOS)
            if dim < 1.0:
                im = ImageEnhance.Brightness(im).enhance(dim)
            self._img_cache[key] = ImageTk.PhotoImage(im)
        return self._img_cache[key]

    def _bg_pil(self, game):
        key = ("bgpil", game["id"])
        if key not in self._img_cache:
            im = Image.open(resource(game["bg"])).convert("RGB")
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
        """images intermédiaires entre deux key-arts (cache par paire)."""
        key = (a["id"], b["id"])
        if key not in self._fade_cache:
            pa, pb = self._bg_pil(a), self._bg_pil(b)
            self._fade_cache[key] = [
                ImageTk.PhotoImage(Image.blend(pa, pb, (i + 1) / (FADE_STEPS + 1)))
                for i in range(FADE_STEPS)
            ]
        return self._fade_cache[key]

    # ── boucle d'animation ────────────────────────────────────────────
    def _tick(self):
        self.t += FPS_MS / 1000.0
        c = self.canvas

        # crossfade de fond en cours
        if self._fading:
            frames, idx = self._fading
            if idx < len(frames):
                c.itemconfig(self._bg_item, image=frames[idx])
                self._fading = (frames, idx + 1)
            else:
                self._fading = None
                c.itemconfig(self._bg_item, image=self._bg_composed(GAMES[self.selected]))

        # respiration du logo sélectionné
        if hasattr(self, "_sel_logo_item"):
            base_y = self._sel_logo_y + math.sin(self.t * 2.2) * 4
            c.coords(self._sel_logo_item, SIDEBAR // 2 + 6, base_y)

        # pulsation du point "En ligne"
        if hasattr(self, "_dot_item"):
            bright = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.t * 4.5))
            g = int(0x5A + (0xFF - 0x5A) * bright * 0.4)
            c.itemconfig(self._dot_item, fill=f"#{int(0x2A * bright):02x}{g:02x}{int(0x55 + 0x30 * bright):02x}")

        # halo du bouton JOUER (pulse doux, plus fort au survol)
        if hasattr(self, "_play_glow"):
            amp = 0.5 + 0.5 * math.sin(self.t * 3.0)
            wpx = 2 + int(amp * 2) + (2 if self.hover == "play" else 0)
            c.itemconfig(self._play_glow, width=wpx)

        # particules qui montent (poussière lumineuse)
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

    # ── dessin ────────────────────────────────────────────────────────
    def _select(self, idx):
        if idx == self.selected:
            return
        prev = GAMES[self.selected]
        self.selected = idx
        self._draw(fade_from=prev)

    def _draw(self, fade_from=None):
        c = self.canvas
        c.delete("all")
        g = GAMES[self.selected]
        accent = g["accent"]

        # key-art (avec crossfade si on vient d'un autre jeu)
        self._bg_item = c.create_image(0, 0, anchor="nw", image=self._bg_composed(g))
        if fade_from is not None:
            self._fading = (self._fade_frames(fade_from, g), 0)
            c.itemconfig(self._bg_item, image=self._bg_composed(fade_from))

        # particules
        self._particle_items = [
            c.create_oval(p[0], p[1], p[0] + p[3], p[1] + p[3], fill="#C8D8CC", width=0)
            for p in self.particles
        ]

        # sidebar : logos
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

        c.create_text(SIDEBAR // 2 + 4, H - 26, text="STUDIO ECHELON",
                      fill="#5A6A62", font=("Arial", 9, "bold"))

        # ── carte info
        cx, cy = W - 300, H - 210
        c.create_rectangle(cx, cy, W - 40, cy + 118, fill="#101418", outline="#1E2A24", width=1)
        mini = self._load(g["logo"], size=(90, 60))
        c.create_image(cx + 60, cy + 34, image=mini)
        self._dot_item = c.create_oval(cx + 126, cy + 18, cx + 134, cy + 26, fill="#5AE68C", width=0)
        c.create_text(cx + 142, cy + 22, anchor="w", text="En ligne",
                      fill="#5AE68C", font=("Arial", 11, "bold"))
        c.create_text(cx + 126, cy + 44, anchor="w", text=g["tagline"][:34],
                      fill="#9AB0A4", font=("Arial", 9), width=150)
        self._discord_zone = (cx + 12, cy + 74, W - 52, cy + 106)
        dcol = "#6B77FF" if self.hover == "discord" else "#5865F2"
        c.create_rectangle(*self._discord_zone, fill=dcol, outline="", width=0)
        c.create_text((cx + 12 + W - 52) // 2, cy + 90, text=f"Rejoindre {g['name']}",
                      fill="white", font=("Arial", 11, "bold"))

        # ── bouton JOUER (halo animé)
        self._play_zone = (W - 300, H - 74, W - 40, H - 18)
        self._play_glow = c.create_rectangle(W - 304, H - 78, W - 36, H - 14,
                                             outline=g["accent_dim"], width=2)
        pcol = self._brighter(accent) if self.hover == "play" else accent
        c.create_rectangle(*self._play_zone, fill=pcol, outline="", width=0)
        c.create_text((W - 300 + W - 40) // 2, H - 46, text="JOUER",
                      fill="#08120C", font=("Arial Black", 22, "bold"))

        c.create_text(W - 170, H - 88, text=self.status.get(),
                      fill="#C8D8CC", font=("Arial", 10))

    @staticmethod
    def _brighter(hexcol):
        r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
        return f"#{min(255, r + 30):02x}{min(255, g + 25):02x}{min(255, b + 30):02x}"

    # ── interactions ──────────────────────────────────────────────────
    def _hit(self, zone, x, y):
        return zone[0] <= x <= zone[2] and zone[1] <= y <= zone[3]

    def _click(self, e):
        for (x0, y0, x1, y1, i) in self._logo_zones:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._select(i)
                return
        if self._hit(self._play_zone, e.x, e.y):
            self._play()
        elif self._hit(self._discord_zone, e.x, e.y):
            webbrowser.open(GAMES[self.selected]["discord"])

    def _motion(self, e):
        prev = self.hover
        self.hover = None
        if self._hit(self._play_zone, e.x, e.y):
            self.hover = "play"
        elif self._hit(self._discord_zone, e.x, e.y):
            self.hover = "discord"
        else:
            for (x0, y0, x1, y1, i) in self._logo_zones:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    self.hover = ("logo", i)
                    break
        self.configure(cursor="hand2" if self.hover else "")
        if prev != self.hover and self._fading is None:
            self._draw()

    # ── lancement ─────────────────────────────────────────────────────
    def _play(self):
        threading.Thread(target=self._play_thread, args=(GAMES[self.selected],), daemon=True).start()

    def _play_thread(self, g):
        try:
            if platform.system() != "Windows":     # dev mac : lance le launcher python
                if os.path.exists(g["dev_launcher"]):
                    subprocess.Popen([sys.executable, g["dev_launcher"]])
                    return
            os.makedirs(HUB_DIR, exist_ok=True)
            exe = os.path.join(HUB_DIR, g["exe"])
            if not os.path.exists(exe):
                self.status.set(f"Téléchargement de {g['name']}…")
                self.after(0, self._draw)
                import urllib.request
                req = urllib.request.Request(g["exe_url"], headers={"User-Agent": "echelon-client"})
                tmp = exe + ".part"
                with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                os.replace(tmp, exe)
            self.status.set("")
            self.after(0, self._draw)
            subprocess.Popen([exe], cwd=HUB_DIR)
        except Exception as ex:
            self.status.set(f"Erreur : {ex}")
            self.after(0, self._draw)


if __name__ == "__main__":
    Hub().mainloop()
