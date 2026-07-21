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
        if hasattr(self, "_play_glow") and hasattr(self, "_glow_frames"):
            amp = 0.5 + 0.5 * math.sin(self.t * 3.0)
            idx = min(2, int(amp * 2 + (1 if self.hover == "play" else 0)))
            c.itemconfig(self._play_glow, image=self._glow_frames[idx])

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

        # signature studio : petite porte + wordmark à côté, sur une ligne
        c.create_image(30, H - 30, image=self._load("assets/studio_icon.png", size=(26, 26)))
        c.create_image(30 + 14 + 31, H - 30, image=self._load("assets/studio_wordmark.png",
                                                              size=(100, 20), dim=0.8))

        # ── carte info (arrondie, bord accent)
        cx, cy = W - 306, H - 216
        cw, chh = 266, 122
        card = self._rounded_img("card:" + g["id"], cw, chh, "#12181C", "#0C1013",
                                 radius=14, border=g["accent_dim"])
        c.create_image(cx + cw // 2, cy + chh // 2, image=card)
        mini = self._load(g["logo"], size=(86, 56))
        c.create_image(cx + 56, cy + 34, image=mini)
        self._dot_item = c.create_oval(cx + 118, cy + 18, cx + 126, cy + 26, fill="#5AE68C", width=0)
        c.create_text(cx + 134, cy + 22, anchor="w", text="En ligne",
                      fill="#5AE68C", font=("Arial", 11, "bold"))
        c.create_text(cx + 118, cy + 46, anchor="w", text=g["tagline"][:36],
                      fill="#9AB0A4", font=("Arial", 9), width=140)

        # bouton Discord : pilule bleurple + vrai logo
        bw, bh = cw - 24, 34
        bx0, by0 = cx + 12, cy + chh - bh - 12
        self._discord_zone = (bx0, by0, bx0 + bw, by0 + bh)
        hov_d = self.hover == "discord"
        dbtn = self._rounded_img("discord" + ("_h" if hov_d else ""), bw, bh,
                                 "#6B77FF" if hov_d else "#5F6BF5",
                                 "#4A56E0" if hov_d else "#4650C8", radius=bh // 2)
        c.create_image(bx0 + bw // 2, by0 + bh // 2, image=dbtn)
        c.create_image(bx0 + 24, by0 + bh // 2, image=self._load("assets/discord_mark.png", size=(22, 17)))
        c.create_text(bx0 + bw // 2 + 10, by0 + bh // 2, text="Rejoindre le Discord",
                      fill="white", font=("Arial", 11, "bold"))

        # ── bouton JOUER (gros, arrondi, dégradé accent + halo animé)
        pw, ph2 = 266, 58
        px0, py0 = W - 306, H - 78
        self._play_zone = (px0, py0, px0 + pw, py0 + ph2)
        hov_p = self.hover == "play"
        self._glow_frames = [self._glow_img("play:" + g["id"], pw, ph2, accent, 16, a)
                             for a in (70, 120, 180)]
        self._play_glow = c.create_image(px0 + pw // 2, py0 + ph2 // 2,
                                         image=self._glow_frames[0])
        pbtn = self._rounded_img("play:" + g["id"] + ("_h" if hov_p else ""), pw, ph2,
                                 self._brighter(accent) if hov_p else accent,
                                 g["accent_dim"], radius=16)
        c.create_image(px0 + pw // 2, py0 + ph2 // 2, image=pbtn)
        c.create_text(px0 + pw // 2 + 1, py0 + ph2 // 2 + 1, text="⛵  JOUER",
                      fill="#0A2A18", font=("Arial Black", 21, "bold"))
        c.create_text(px0 + pw // 2, py0 + ph2 // 2, text="⛵  JOUER",
                      fill="#08120C", font=("Arial Black", 21, "bold"))

        c.create_text(px0 + pw // 2, py0 - 16, text=self.status.get(),
                      fill="#C8D8CC", font=("Arial", 10))

    @staticmethod
    def _brighter(hexcol):
        r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
        return f"#{min(255, r + 30):02x}{min(255, g + 25):02x}{min(255, b + 30):02x}"

    # ── boutons/cartes pré-rendus PIL (arrondis, dégradé, ombre) ──────
    @staticmethod
    def _hex(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

    def _rounded_img(self, key, w, h, c_top, c_bottom, radius=12, border=None,
                     shadow=True, highlight=True):
        """bouton arrondi ANTIALIASÉ : rendu ×4 puis réduction LANCZOS."""
        ck = ("btn", key, w, h)
        if ck in self._img_cache:
            return self._img_cache[ck]
        S = 4
        pad = 8
        Wp, Hp = (w + pad * 2) * S, (h + pad * 2) * S
        ws, hs, ps, rs = w * S, h * S, pad * S, radius * S
        im = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if shadow:   # ombre portée douce
            sh = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle(
                (ps + S, ps + 3 * S, ps + ws + S, ps + hs + 4 * S),
                radius=rs + S, fill=(0, 0, 0, 90))
            from PIL import ImageFilter
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(3 * S)))
            d = ImageDraw.Draw(im)
        # dégradé vertical
        t, b = self._hex(c_top), self._hex(c_bottom)
        grad = Image.new("RGBA", (ws, hs), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for yy in range(hs):
            f = yy / max(1, hs - 1)
            gd.line((0, yy, ws, yy), fill=(int(t[0] + (b[0] - t[0]) * f),
                                           int(t[1] + (b[1] - t[1]) * f),
                                           int(t[2] + (b[2] - t[2]) * f), 255))
        mask = Image.new("L", (ws, hs), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, ws - 1, hs - 1), radius=rs, fill=255)
        im.paste(grad, (ps, ps), mask)
        if highlight:   # reflet haut
            hi = Image.new("RGBA", (ws, hs), (0, 0, 0, 0))
            ImageDraw.Draw(hi).rounded_rectangle((2 * S, 2 * S, ws - 3 * S, hs // 2),
                                                 radius=rs - 2 * S, fill=(255, 255, 255, 34))
            im.paste(hi, (ps, ps), hi)
        if border:
            d.rounded_rectangle((ps, ps, ps + ws - 1, ps + hs - 1), radius=rs,
                                outline=self._hex(border) + (255,), width=S)
        im = im.resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
        ph = ImageTk.PhotoImage(im)
        self._img_cache[ck] = ph
        return ph

    def _glow_img(self, key, w, h, color, radius, alpha):
        """halo flouté autour d'un bouton (préréglé, animé par échange d'images)."""
        ck = ("glow", key, w, h, alpha)
        if ck in self._img_cache:
            return self._img_cache[ck]
        from PIL import ImageFilter
        S = 2
        pad = 18
        im = Image.new("RGBA", ((w + pad * 2) * S, (h + pad * 2) * S), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle(
            (pad * S, pad * S, (pad + w) * S, (pad + h) * S),
            radius=radius * S, outline=self._hex(color) + (alpha,), width=3 * S)
        im = im.filter(ImageFilter.GaussianBlur(4 * S)).resize(
            (w + pad * 2, h + pad * 2), Image.LANCZOS)
        ph = ImageTk.PhotoImage(im)
        self._img_cache[ck] = ph
        return ph

    def _discord_icon(self, size=22):
        ck = ("dicon", size)
        if ck in self._img_cache:
            return self._img_cache[ck]
        s = size * 4
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        # silhouette manette-fantôme du logo Discord (approx propre)
        d.rounded_rectangle((s * 0.08, s * 0.18, s * 0.92, s * 0.74), radius=int(s * 0.28),
                            fill=(255, 255, 255, 255))
        d.polygon([(s * 0.16, s * 0.66), (s * 0.30, s * 0.88), (s * 0.38, s * 0.70)],
                  fill=(255, 255, 255, 255))
        d.polygon([(s * 0.84, s * 0.66), (s * 0.70, s * 0.88), (s * 0.62, s * 0.70)],
                  fill=(255, 255, 255, 255))
        d.ellipse((s * 0.28, s * 0.38, s * 0.44, s * 0.58), fill=(88, 101, 242, 255))
        d.ellipse((s * 0.56, s * 0.38, s * 0.72, s * 0.58), fill=(88, 101, 242, 255))
        im = im.resize((size, size), Image.LANCZOS)
        ph = ImageTk.PhotoImage(im)
        self._img_cache[ck] = ph
        return ph

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
