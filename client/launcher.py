#!/usr/bin/env python3
"""
STUDIO ECHELON CLIENT — LE launcher des jeux Echelon : tout est intégré.
Sidebar de logos, key-art plein écran, pseudo, JOUER → installe MC + Fabric +
Java + le mod (bootstrap GitHub) et lance le jeu. Pas de launcher tiers.
Police Zalando Sans Expanded embarquée.
"""
import os, sys, math, random, json, shutil, platform, subprocess, threading, uuid, webbrowser
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
CLIENT_VERSION = "1.0"
CLIENT_BASE = RELEASES + "/client"   # manifest.json + StudioEchelonClient.exe


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def game_root(name):
    if platform.system() == "Windows":
        return os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), name)
    return os.path.expanduser("~/" + name)


GAMES = [
    {
        "id": "harbor",
        "name": "HARBOR",
        "tagline": "Raft × Sea of Thieves — survis, navigue, pille.",
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
        "play": "JOUER",
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
        "dir": game_root("DonShot"),
        "base": RELEASES + "/donshot",
        "mod_file": "donshot.jar",
        "seed": "donshot:",
        "deps": {"fabric-api": "fabric-api", "geckolib": "geckolib", "sodium": "sodium",
                 "lithium": "lithium", "notenoughanimations": "not-enough-animations",
                 "PresenceFootsteps": "presence-footsteps"},
        "purge": ["firstperson"],
        "play": "JOUER",
        "discord": "https://playechelon.net",
    },
]


class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        # auto-update du hub AVANT toute UI : si un nouvel exe est publié,
        # on le télécharge, on se remplace et on redémarre.
        if self._self_update():
            self.destroy()
            return
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
        self.options_open = False
        self.status = tk.StringVar(value="")
        self.progress_val = tk.DoubleVar(value=0)
        self.busy = False
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

        # champ pseudo 100 % canvas : aucun widget natif, aucun chrome
        self.pseudo_text = self._load_pseudo()
        self.pseudo_focus = False
        self.bind("<Key>", self._key)

        self._draw()
        self.after(FPS_MS, self._tick)

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

    # ── images ────────────────────────────────────────────────────────
    @staticmethod
    def _hex(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

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
            bright = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.t * 4.5))
            g = int(0x5A + (0xFF - 0x5A) * bright * 0.4)
            c.itemconfig(self._dot_item, fill=f"#{int(0x2A * bright):02x}{g:02x}{int(0x55 + 0x30 * bright):02x}")

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

        c.create_image(30, H - 30, image=self._load("assets/studio_icon.png", size=(26, 26)))
        c.create_image(30 + 14 + 31, H - 30, image=self._load("assets/studio_wordmark.png",
                                                              size=(100, 20), dim=0.8))

        # ── colonne droite : carte info, pseudo, JOUER, progression
        cw = 280
        cx = W - cw - 34

        # carte info (verre)
        cy = H - 330
        card = self._flat("card", cw, 116, (14, 20, 24, 216), radius=16)
        c.create_image(cx + cw // 2, cy + 58, image=card)
        mini = self._load(g["logo"], size=(82, 54))
        c.create_image(cx + 52, cy + 34, image=mini)
        self._dot_item = c.create_oval(cx + 112, cy + 20, cx + 120, cy + 28, fill="#5AE68C", width=0)
        c.create_text(cx + 128, cy + 24, anchor="w", text="En ligne",
                      fill="#5AE68C", font=self.F(10, True))
        c.create_text(cx + 112, cy + 48, anchor="w", text=g["tagline"][:38],
                      fill="#9AB0A4", font=self.F(8), width=156)
        bw2, bh2 = cw - 24, 32
        bx0, by0 = cx + 12, cy + 116 - bh2 - 12
        self._discord_zone = (bx0, by0, bx0 + bw2, by0 + bh2)
        self._discord_frames = self._btn_frames("discord", bw2, bh2, "#5865F2", 12)
        hovd = 1.0 if self.hover == "discord" else 0.0
        c.create_image(bx0 + bw2 // 2, by0 + bh2 // 2,
                       image=self._discord_frames[round(hovd * 7)])
        c.create_image(bx0 + 24, by0 + bh2 // 2, image=self._load("assets/discord_mark.png", size=(20, 15)))
        c.create_text(bx0 + bw2 // 2 + 8, by0 + bh2 // 2, text="Rejoindre le Discord",
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
        c.create_text(cx + cw // 2, iy - 30, text="PSEUDO", fill="#7A948A", font=self.F(8, True))

        # JOUER + ⚙ options (séparées par jeu)
        ph2 = 54
        py0 = H - 129
        pw2 = cw - 62
        self._play_zone = (cx, py0, cx + pw2, py0 + ph2)
        self._play_frames = self._btn_frames("play:" + g["id"], pw2, ph2, accent, 12)
        self._play_item = c.create_image(cx + pw2 // 2, py0 + ph2 // 2, image=self._play_frames[0])
        label = "INSTALLATION…" if self.busy else g["play"]
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
        c.create_text(px + 82, py + 32, anchor="w", text="OPTIONS",
                      fill="#EAF6EF", font=self.F(14, True))
        c.create_text(px + 82, py + 52, anchor="w", text=f"réglages propres à {g['name']}",
                      fill="#7A948A", font=self.F(8))

        rows_y = py + 92
        row_h = 52
        lx = px + 28
        rx = px + pw - 28

        def sep(y):
            c.create_rectangle(lx, y, rx, y + 1, fill="#1C2622", width=0)

        # ── RAM
        y0 = rows_y
        c.create_text(lx, y0 + 14, anchor="w", text="Mémoire allouée",
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y0 + 30, anchor="w", text="RAM réservée au jeu",
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
        c.create_text(lx, y1 + 14, anchor="w", text="Discord Rich Presence",
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y1 + 30, anchor="w", text="affiche ta partie sur ton profil Discord",
                      fill="#6A7E74", font=self.F(8), width=pw - 140)
        self._rpc_zone = (rx - 50, y1 + 9, rx, y1 + 35)
        self._toggle(c, self._rpc_zone, o.get("rpc", True), acc)
        sep(y1 + row_h - 6)

        # ── fermeture auto
        y2 = rows_y + row_h * 2
        c.create_text(lx, y2 + 14, anchor="w", text="Fermer au lancement",
                      fill="#DCE8E0", font=self.F(10, True))
        c.create_text(lx, y2 + 30, anchor="w", text="le launcher se ferme quand le jeu démarre",
                      fill="#6A7E74", font=self.F(8), width=pw - 140)
        self._close_zone = (rx - 50, y2 + 9, rx, y2 + 35)
        self._toggle(c, self._close_zone, o.get("close", False), acc)
        sep(y2 + row_h - 6)

        # ── dossier du jeu
        y3 = rows_y + row_h * 3
        c.create_text(lx, y3 + 14, anchor="w", text="Dossier du jeu",
                      fill="#DCE8E0", font=self.F(10, True))
        path = g["dir"]
        if len(path) > 34:
            path = "…" + path[-33:]
        c.create_text(lx, y3 + 30, anchor="w", text=path,
                      fill="#6A7E74", font=self.F(7), width=pw - 160)
        self._folder_zone = (rx - 92, y3 + 8, rx, y3 + 36)
        c.create_image((rx - 92 + rx) // 2, y3 + 22,
                       image=self._flat("folder", 92, 28, (32, 42, 38, 255), radius=10))
        c.create_text((rx - 92 + rx) // 2, y3 + 22, text="OUVRIR",
                      fill="#DCE8E0", font=self.F(9, True))

        # ── fermer (accent)
        self._optclose_zone = (px + pw // 2 - 74, py + ph - 58, px + pw // 2 + 74, py + ph - 24)
        c.create_image(px + pw // 2, py + ph - 41,
                       image=self._flat("optclose" + g["id"], 148, 34,
                                        self._hex(acc) + (255,), radius=12))
        c.create_text(px + pw // 2, py + ph - 41, text="TERMINÉ",
                      fill="#06140C", font=self.F(10, True))

    # ── interactions ──────────────────────────────────────────────────
    def _hit(self, zone, x, y):
        return zone[0] <= x <= zone[2] and zone[1] <= y <= zone[3]

    def _key(self, e):
        """saisie du pseudo, gérée à la main (champ canvas)."""
        if not self.pseudo_focus:
            return
        if e.keysym == "BackSpace":
            self.pseudo_text = self.pseudo_text[:-1]
        elif e.keysym in ("Return", "Escape", "Tab"):
            self.pseudo_focus = False
        elif e.char and e.char.isprintable() and len(self.pseudo_text) < 16:
            self.pseudo_text += e.char
        self.canvas.itemconfig(self._input_text, text=self.pseudo_text)

    def _click(self, e):
        g = GAMES[self.selected]
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
            self._play()
        elif self._hit(self._gear_zone, e.x, e.y):
            self.options_open = True
            self._draw()
        elif self._hit(self._discord_zone, e.x, e.y):
            webbrowser.open(GAMES[self.selected]["discord"])

    def _motion(self, e):
        prev = self.hover
        self.hover = None
        if self._hit(self._play_zone, e.x, e.y):
            self.hover = "play"
        elif self._hit(self._gear_zone, e.x, e.y):
            self.hover = "gear"
        elif self._hit(self._discord_zone, e.x, e.y):
            self.hover = "discord"
        else:
            for (x0, y0, x1, y1, i) in self._logo_zones:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    self.hover = ("logo", i)
                    break
        self.configure(cursor="hand2" if self.hover else "")
        # les logos + discord changent d'état par redraw (pas d'anim continue dessus)
        if prev != self.hover and self._fading is None \
                and (isinstance(prev, tuple) or isinstance(self.hover, tuple)
                     or "discord" in (prev, self.hover) or "gear" in (prev, self.hover)):
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
            pseudo = (self.pseudo_text.strip() or "Joueur")[:16]
            self._save_state(pseudo=pseudo)
            os.makedirs(g["dir"], exist_ok=True)

            self.status.set(f"Installation de Minecraft {MC_VERSION} + Fabric…")
            mll.fabric.install_fabric(MC_VERSION, g["dir"], callback=self._callbacks())
            fabric_version = None
            for v in mll.utils.get_installed_versions(g["dir"]):
                if "fabric" in v["id"] and MC_VERSION in v["id"]:
                    fabric_version = v["id"]
            if not fabric_version:
                raise RuntimeError("Fabric introuvable après installation")

            java = None
            try:
                java = mll.runtime.get_executable_path(JAVA_RUNTIME, g["dir"])
                if java is None:
                    self.status.set("Installation de Java 21 (Mojang)…")
                    mll.runtime.install_jvm_runtime(JAVA_RUNTIME, g["dir"], callback=self._callbacks())
                    java = mll.runtime.get_executable_path(JAVA_RUNTIME, g["dir"])
            except Exception:
                java = None

            mods = os.path.join(g["dir"], "mods")
            os.makedirs(mods, exist_ok=True)
            self._sync_mod(g, mods)
            self._ensure_deps(g, mods)

            # options lues par le mod en jeu (Rich Presence…)
            cfg_dir = os.path.join(g["dir"], "config")
            os.makedirs(cfg_dir, exist_ok=True)
            json.dump({"rich_presence": self._opts(g).get("rpc", True)},
                      open(os.path.join(cfg_dir, "echelon-launcher.json"), "w"))

            self.status.set("Lancement de " + g["name"] + "…")
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
            self.status.set("Bon jeu ! (tu peux fermer le launcher)")
            subprocess.Popen(cmd, cwd=g["dir"])
            if o.get("close", False):
                self.after(1500, self.destroy)
        except Exception as e:
            self.status.set(f"Erreur : {e}")
        finally:
            self.busy = False
            self.after(0, self._draw)

    def _sync_mod(self, g, mods):
        """bootstrap : jar du mod depuis le canal GitHub (sha256 vérifié)."""
        import urllib.request, hashlib
        target = os.path.join(mods, g["mod_file"])
        manifest = None
        try:
            req = urllib.request.Request(g["base"] + "/manifest.json",
                                         headers={"User-Agent": "echelon-client"})
            manifest = json.load(urllib.request.urlopen(req, timeout=8))
        except Exception:
            pass
        if manifest:
            want = manifest.get("mod_version", "")
            have = self._state().get("mod_" + g["id"], "")
            if want != have or not os.path.exists(target):
                self.status.set(f"Mise à jour de {g['name']} ({want})…")
                tmp = target + ".new"
                req = urllib.request.Request(g["base"] + "/" + manifest.get("mod_file", g["mod_file"]),
                                             headers={"User-Agent": "echelon-client"})
                with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                    shutil.copyfileobj(r, f)
                sha = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
                if manifest.get("mod_sha256") and sha != manifest["mod_sha256"]:
                    os.remove(tmp)
                    raise RuntimeError("Mod corrompu (sha256) — réessaie.")
                shutil.move(tmp, target)
                self._save_state(**{"mod_" + g["id"]: want})
        elif not os.path.exists(target):
            raise RuntimeError("Pas de connexion pour télécharger le jeu.")

    def _ensure_deps(self, g, mods):
        import urllib.request
        for f in os.listdir(mods):
            if any(f.startswith(p) for p in g["purge"]):
                os.remove(os.path.join(mods, f))
        for prefix, project in g["deps"].items():
            if any(f.startswith(prefix) for f in os.listdir(mods)):
                continue
            self.status.set(f"Téléchargement de {project}…")
            api = ("https://api.modrinth.com/v2/project/" + project
                   + "/version?game_versions=[%22" + MC_VERSION + "%22]&loaders=[%22fabric%22]")
            req = urllib.request.Request(api, headers={"User-Agent": "echelon-client"})
            versions = json.load(urllib.request.urlopen(req))
            f0 = versions[0]["files"][0]
            urllib.request.urlretrieve(f0["url"], os.path.join(mods, f0["filename"]))


if __name__ == "__main__":
    Hub().mainloop()
