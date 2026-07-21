#!/usr/bin/env python3
"""
STUDIO ECHELON CLIENT — le hub des jeux Echelon, façon SKGames :
sidebar de logos, key-art plein écran par jeu, carte Discord, gros JOUER.
Le bouton JOUER télécharge (1re fois) puis lance le launcher du jeu choisi —
chaque launcher gère ensuite ses propres mises à jour (bootstrap).
"""
import os, sys, json, platform, subprocess, threading, webbrowser
import tkinter as tk

try:
    from PIL import Image, ImageTk, ImageEnhance, ImageDraw
except ImportError:
    print("pip install pillow")
    sys.exit(1)

W, H = 1180, 700
SIDEBAR = 210

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
        "logo": "assets/donshot_logo.png",
        "bg": "assets/donshot_bg.png",
        "exe": "DonShotLauncher.exe",
        "exe_url": RELEASES + "/donshot/DonShotLauncher.exe",
        "dev_launcher": os.path.expanduser("~/test/donshot-launcher/launcher.py"),
        "discord": "https://playechelon.net",
    },
]

BG = "#0A0C0E"


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
        self._build()
        self._select(0)

    # ── UI ────────────────────────────────────────────────────────────
    def _build(self):
        self.canvas = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg=BG)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._motion)

    def _load(self, path, size=None, dim=1.0):
        key = (path, size, dim)
        if key in self._img_cache:
            return self._img_cache[key]
        im = Image.open(resource(path)).convert("RGBA")
        if size:
            im.thumbnail(size, Image.LANCZOS)
        if dim < 1.0:
            im = ImageEnhance.Brightness(im).enhance(dim)
        ph = ImageTk.PhotoImage(im)
        self._img_cache[key] = ph
        return ph

    def _bg_composed(self, game):
        """key-art recadrée cover + dégradé sombre côté sidebar."""
        key = ("bg", game["id"])
        if key in self._img_cache:
            return self._img_cache[key]
        im = Image.open(resource(game["bg"])).convert("RGB")
        # cover crop
        ratio = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * ratio) + 1, int(im.height * ratio) + 1), Image.LANCZOS)
        x0 = (im.width - W) // 2
        y0 = (im.height - H) // 2
        im = im.crop((x0, y0, x0 + W, y0 + H))
        im = ImageEnhance.Brightness(im).enhance(0.82)
        # dégradé gauche (sidebar fondue dans l'art)
        grad = Image.new("L", (W, 1), 0)
        gd = ImageDraw.Draw(grad)
        for x in range(W):
            t = min(1.0, max(0.0, (x - SIDEBAR * 0.4) / (SIDEBAR * 2.2)))
            gd.point((x, 0), fill=int(255 * t))
        grad = grad.resize((W, H))
        dark = Image.new("RGB", (W, H), (8, 9, 11))
        im = Image.composite(im, dark, grad)
        ph = ImageTk.PhotoImage(im)
        self._img_cache[key] = ph
        return ph

    def _select(self, idx):
        self.selected = idx
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("all")
        g = GAMES[self.selected]
        accent = g["accent"]

        # key-art
        c.create_image(0, 0, anchor="nw", image=self._bg_composed(g))

        # sidebar : logos
        y = 60
        self._logo_zones = []
        for i, game in enumerate(GAMES):
            sel = i == self.selected
            logo = self._load(game["logo"], size=(170, 120), dim=1.0 if sel else 0.42)
            c.create_image(SIDEBAR // 2 + 6, y + 60, image=logo)
            if sel:
                c.create_rectangle(6, y + 10, 9, y + 110, fill=accent, width=0)
            self._logo_zones.append((10, y, SIDEBAR, y + 120, i))
            y += 190

        # wordmark studio en bas de sidebar
        c.create_text(SIDEBAR // 2 + 4, H - 26, text="STUDIO ECHELON",
                      fill="#5A6A62", font=("Arial", 9, "bold"))

        # ── carte info en bas à droite
        cx, cy = W - 300, H - 210
        c.create_rectangle(cx, cy, W - 40, cy + 118, fill="#101418", outline="#1E2A24", width=1)
        mini = self._load(g["logo"], size=(90, 60))
        c.create_image(cx + 60, cy + 34, image=mini)
        c.create_text(cx + 130, cy + 24, anchor="w", text="● En ligne",
                      fill="#5AE68C", font=("Arial", 11, "bold"))
        c.create_text(cx + 130, cy + 44, anchor="w", text=g["tagline"][:34],
                      fill="#9AB0A4", font=("Arial", 9), width=140)
        # bouton discord
        self._discord_zone = (cx + 12, cy + 74, W - 52, cy + 106)
        c.create_rectangle(*self._discord_zone, fill="#5865F2", outline="", width=0)
        c.create_text((cx + 12 + W - 52) // 2, cy + 90, text=f"Rejoindre {g['name']}",
                      fill="white", font=("Arial", 11, "bold"))

        # ── bouton JOUER
        self._play_zone = (W - 300, H - 74, W - 40, H - 18)
        c.create_rectangle(*self._play_zone, fill=accent, outline="", width=0)
        c.create_text((W - 300 + W - 40) // 2, H - 46, text="JOUER",
                      fill="#08120C", font=("Arial Black", 22, "bold"))

        # statut (téléchargement…)
        c.create_text(W - 170, H - 88, text=self.status.get(),
                      fill="#C8D8CC", font=("Arial", 10))

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
        over = self._hit(self._play_zone, e.x, e.y) or self._hit(self._discord_zone, e.x, e.y) \
            or any(x0 <= e.x <= x1 and y0 <= e.y <= y1 for (x0, y0, x1, y1, _) in self._logo_zones)
        self.configure(cursor="hand2" if over else "")

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
