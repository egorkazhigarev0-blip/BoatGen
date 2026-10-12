"""BoatGen engine: parametric generator of Brick Rigs boats.

generate(kind, size, detail, color, seed) -> Result with .kit (bricks), .info (stats), .name

kind:   "motor" (open motor boat), "cutter" (simple cabin boat), "military" (armed patrol boat)
size:   "S", "M", "L"
detail: "low" (200-250 bricks), "med" (500-600), "high" (900-1100)
color:  "dark", "greyblue", "light"

Rules learned from the user's working builds (pickup, PU1, SEVER-4 fixes, vebr examples):
  * input-channel sources and OwningSeat are 1-based brick indices
  * a thruster pushes one way only -> reverse thrust and stabilisers use +/- pairs
  * stabiliser: angle sensor + angular-speed sensor -> summing switch -> thruster pairs
    (sensor ranges and signs as corrected by the user in SEVER-4)
  * doors: actuator in Seeking mode driven by a toggle switch; moving leaves have
    ConnectorSpacing = 0 so they do not snap to the walls
  * turret aim actuators and the fire switch take their input from the gunner seat,
    the sight camera has OwningSeat = gunner seat
  * the hull is welded in irregular chunks (not one block) so it breaks realistically;
    chunks hold to each other by contact through frames, floats and keel
"""
import copy
import math
import os
import random
from datetime import datetime, timezone

from .kit import Kit, add, sub, mul, unit, norm, cross, dot, mid, frame, mat_to_rot, rotm
from .brv import Vehicle
from .brm import Meta

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ----------------------------------------------------------------------------- catalogue
KINDS = {
    #            hull length (cm) S / M / L     L/B    depth/L  deadrise
    "motor":    dict(L=(420, 500, 600), B=(170, 205, 240), ratio=2.55, depth=0.160, dr0=16, outboards=1),
    "cutter":   dict(L=(650, 800, 950), B=(265, 285, 315), ratio=2.95, depth=0.150, dr0=18, outboards=2),
    "military": dict(L=(900, 1100, 1300), B=(320, 345, 390), ratio=3.25, depth=0.142, dr0=20, outboards=2),
}
DETAIL = {"low": (300, 350), "med": (650, 800), "high": (1100, 1300)}
EQUIP = {"low": 0, "med": 1, "high": 2}
# (stations, bottom strakes, side strakes, deck strips)
RES = [(7, 1, 2, 1), (8, 2, 2, 2), (9, 2, 2, 2), (10, 2, 3, 2), (11, 2, 3, 3), (12, 3, 3, 3),
       (13, 3, 3, 3), (14, 3, 4, 3), (15, 3, 4, 4), (16, 3, 4, 4), (17, 4, 4, 4), (18, 4, 5, 4),
       (19, 4, 5, 5), (20, 4, 5, 5), (22, 4, 6, 5), (24, 5, 6, 5), (26, 5, 6, 6), (28, 5, 7, 6),
       (30, 6, 7, 6), (33, 6, 7, 7), (36, 6, 8, 7), (40, 7, 8, 8), (44, 7, 9, 8), (48, 8, 9, 9),
       (52, 8, 10, 9), (56, 9, 10, 10)]

PALETTES = {
    "dark": dict(bottom=(40, 42, 45), boot=(24, 25, 27), hull_low=(70, 74, 78), band=(32, 33, 35),
                 hull=(58, 62, 66), collar=(26, 26, 27), deck_a=(60, 63, 66), deck_b=(52, 55, 58),
                 cabin=(86, 90, 94), cabin_d=(62, 66, 70), frame=(26, 27, 29), engine=(30, 31, 33),
                 text=(214, 216, 218)),
    "greyblue": dict(bottom=(44, 52, 64), boot=(28, 32, 40), hull_low=(112, 124, 138), band=(52, 62, 78),
                     hull=(92, 106, 122), collar=(34, 38, 46), deck_a=(78, 86, 96), deck_b=(70, 78, 88),
                     cabin=(128, 140, 152), cabin_d=(92, 104, 118), frame=(30, 34, 40), engine=(36, 40, 48),
                     text=(226, 232, 238)),
    "light": dict(bottom=(70, 74, 80), boot=(40, 44, 50), hull_low=(196, 200, 204), band=(120, 126, 134),
                  hull=(176, 180, 186), collar=(60, 64, 70), deck_a=(150, 154, 158), deck_b=(138, 142, 146),
                  cabin=(214, 216, 218), cabin_d=(168, 172, 176), frame=(40, 44, 50), engine=(206, 208, 212),
                  text=(40, 44, 50)),
}
GLASS = (22, 28, 34, 130)
CHROME = (190, 192, 196)
STEEL = (56, 58, 62)
PROP = (182, 142, 64)
WHITE = (208, 210, 212)
HIDDEN = (60, 60, 60)


def src(i):
    return i + 1          # input-channel / OwningSeat references are 1-based


def rgba(c):
    return tuple(c) + ((255,) if len(c) == 3 else ())


# ----------------------------------------------------------------------------- hull lines
class Lines:
    def __init__(self, L, hw, D, dr0, rng):
        self.L, self.hw, self.D = L, hw, D
        self.X0 = -0.478 * L
        self.X1 = self.X0 + L
        self.xk = self.X0 + 0.574 * L
        self.xct = self.X0 + 0.478 * L
        self.Hk = 0.785 * D
        self.c0 = 0.875 * hw
        self.dr0 = dr0
        self.rise = D * rng.uniform(0.12, 0.42)
        self.flare = 5.0 * hw / 160.0

    def keel_z(self, x):
        if x <= self.xk:
            return 0.0
        return self.Hk * ((x - self.xk) / (self.X1 - 5 - self.xk)) ** 2

    def chine_hw(self, x):
        if x <= self.xct:
            return self.c0
        end = self.X1 - 0.024 * self.L
        return self.c0 * math.sqrt(max(0.0, 1 - ((x - self.xct) / (end - self.xct)) ** 2))

    def deadrise(self, x):
        t = (x - self.xct) / (self.X0 + 0.909 * self.L - self.xct)
        return math.radians(self.dr0 + (50 - self.dr0) * min(1.0, max(0.0, t)))

    def chine_z(self, x):
        return self.keel_z(x) + self.chine_hw(x) * math.tan(self.deadrise(x))

    def sheer_hw(self, x):
        if x <= self.xct:
            return self.hw
        return self.hw * math.sqrt(max(0.0, 1 - ((x - self.xct) / (self.X1 - self.xct)) ** 2))

    def sheer_z(self, x):
        if x <= self.xk:
            return self.D
        return self.D + self.rise * ((x - self.xk) / (self.X1 - self.xk)) ** 2

    def section(self, x, s, NB, NS):
        k, c, zc, sh, zs = self.keel_z(x), self.chine_hw(x), self.chine_z(x), self.sheer_hw(x), self.sheer_z(x)
        zc = min(zc, zs - 0.06 * self.D)
        pts = [(x, s * c * j / NB, k + (zc - k) * j / NB) for j in range(NB + 1)]
        for j in range(1, NS + 1):
            t = j / NS
            y = c + (sh - c) * t + self.flare * math.sin(math.pi * t) * (sh > 1)
            pts.append((x, s * y, zc + (zs - zc) * t))
        return pts

    def hull_hw(self, x, z):
        pts = self.section(x, 1, 2, 3)
        if z <= pts[0][2]:
            return 0.0
        for a, b in zip(pts, pts[1:]):
            if a[2] <= z <= b[2] and b[2] > a[2]:
                return a[1] + (b[1] - a[1]) * (z - a[2]) / (b[2] - a[2])
        return pts[-1][1]


# ----------------------------------------------------------------------------- builder
class Builder:
    def __init__(self, kind, size, detail, color, seed, res, faction=None):
        self.kind, self.size, self.detail, self.color, self.seed = kind, size, detail, color, seed
        self.faction = faction if kind == "military" else None
        self.rng = random.Random("%s-%d" % (kind, seed))
        rng = self.rng
        spec = KINDS[kind]
        L = spec["L"]["SML".index(size)] * rng.uniform(0.96, 1.04)
        B = spec["B"]["SML".index(size)] * rng.uniform(0.97, 1.03)
        D = L * spec["depth"] * rng.uniform(0.97, 1.05)
        if kind == "motor":
            D = max(D, 74.0)
        self.L, self.B, self.D = L, B, D
        self.ln = Lines(L, B / 2, D, spec["dr0"] + rng.uniform(-2, 2), rng)
        self.P = {k: rgba(v) for k, v in PALETTES[color].items()}
        self.sty = make_style(kind, size, color, seed)
        sty, P = self.sty, self.P
        if sty["stripe"]:
            P["band"] = rgba(sty["stripe"])
        if sty["bottom_red"]:
            P["bottom"] = rgba((112, 40, 36))
        t = sty["cab_tint"]
        for k in ("cabin", "cabin_d"):
            P[k] = tuple(max(0, min(255, int(c + t))) for c in P[k][:3]) + (255,)
        P["roof"] = rgba((222, 224, 226)) if sty["two_tone"] else P["cabin_d"]
        if self.faction == "south":
            # "Southern State": worn, a bit improvised - dull olive-brown cast, rusty bottom
            def dull(c, k=0.18, to=(88, 82, 62)):
                return tuple(int(c[i] * (1 - k) + to[i] * k) for i in range(3)) + (255,)
            for k_ in ("hull", "hull_low", "cabin", "cabin_d", "deck_a", "deck_b", "roof", "band"):
                P[k_] = dull(P[k_])
            P["bottom"] = rgba((86, 52, 40))
        h = sty["hull_tint"]
        for k in ("hull", "hull_low"):
            P[k] = tuple(max(0, min(255, int(c + h))) for c in P[k][:3]) + (255,)
        self.res = RES[res]
        self.eq = EQUIP[detail]
        self.hm = "Aluminium" if kind == "military" else "Plastic"     # GRP hulls for civil boats
        self.K = Kit()
        self.scale = L / 1045.0
        self.notes = []

    # ------------------------------------------------------------------ stations & chunks
    def stations(self):
        ln, n = self.ln, self.res[0]
        xs = [ln.X0 + ln.L * (1 - (1 - t / (n - 2)) ** 1.35) for t in range(n - 1)]
        xs = [x for x in xs if x < ln.X1 - 0.03 * ln.L]
        xs += [ln.X1 - 0.03 * ln.L, ln.X1 - 0.012 * ln.L, ln.X1]
        return sorted(set(round(x, 1) for x in xs))

    def make_chunks(self, st):
        """Irregular weld chunks: 1-3 sections each, the bow tip in one piece."""
        rng, ln, K = self.rng, self.ln, self.K
        nsec = len(st) - 1
        chunk_of, i = {}, 0
        bow_from = ln.X0 + 0.80 * ln.L
        while i < nsec:
            if st[i] >= bow_from:
                w = K.new_weld()
                for j in range(i, nsec):
                    chunk_of[j] = w
                break
            n = rng.choice((1, 1, 2)) if self.eq else rng.choice((1, 2, 2))
            w = K.new_weld()
            for j in range(i, min(nsec, i + n)):
                chunk_of[j] = w
            i += n
        return chunk_of

    def jag_chunk(self, i, band, side):
        """Break lines are not straight: each strake / deck strip shifts the chunk boundary by up
        to one section (a smooth random walk across the strakes), so a hit tears out a ragged piece."""
        if not hasattr(self, "_jag"):
            self._jag = {}
        key = (band if band < 50 else 50 + band % 7, side)
        if key not in self._jag:
            r = random.Random("jag-%d-%d-%d" % (self.seed, key[0], side))
            prev = self._jag.get((key[0] - 1, side), 0)
            self._jag[key] = max(-1, min(1, prev + r.choice((-1, 0, 0, 1))))
        o = self._jag[key]
        if random.Random("jg-%d-%d-%d-%d" % (self.seed, i, band, side)).random() < 0.15:
            o = max(-1, min(1, o + random.Random("jh-%d-%d" % (i, band)).choice((-1, 1))))
        j = max(0, min(len(self.chunk_of) - 1, i + o))
        return self.chunk_of[j]

    def skin_chunk(self, chunk_of, i, band):
        """Skin bands sometimes belong to the neighbouring chunk -> ragged break lines."""
        r = random.Random(self.seed * 131 + i * 17 + band)
        if r.random() < 0.3:
            j = min(max(0, i + r.choice((-1, 1))), len(chunk_of) - 1)
            return chunk_of[j]
        return chunk_of[i]

    # ------------------------------------------------------------------ hull
    def hull(self):
        K, ln, P = self.K, self.ln, self.P
        NB, NS, NSTRIP = self.res[1], self.res[2], self.res[3]
        st = self.stations()
        self.st = st
        chunk_of = self.make_chunks(st)
        self.chunk_of = chunk_of
        strake_col = [P["bottom"]] * NB + [P["boot"]] + [P["hull_low"]] * max(0, NS - 3) + [P["band"], P["hull"]]
        strake_col = strake_col[:NB + NS]
        collar = self.kind == "military"
        open_boat = self.kind == "motor"
        floor_z = ln.D * 0.46 if open_boat else None
        self.floor_z = floor_z
        x_fd = ln.X0 + 0.70 * ln.L if open_boat else None
        self.x_fd = x_fd
        last_float = ln.X1 - 0.06 * ln.L
        for i in range(len(st) - 1):
            xa, xb = st[i], st[i + 1]
            xm = (xa + xb) / 2
            centre = (xm, 0.0, (ln.keel_z(xm) + ln.sheer_z(xm)) / 2 - 0.14 * ln.D)
            for s in (1, -1):
                A, B = ln.section(xa, s, NB, NS), ln.section(xb, s, NB, NS)
                for j in range(NB + NS):
                    K.weld = self.jag_chunk(i, j, s)
                    p0, p1, q0, q1 = A[j], A[j + 1], B[j], B[j + 1]
                    if (norm(sub(p1, p0)) + norm(sub(q1, q0))) / 2 < 1.0:
                        continue
                    K.plate(p0, p1, q0, q1, sub(mid(p0, p1, q0, q1), centre), 1.2, strake_col[j], self.hm,
                            overlap=2.0 if NB + NS >= 10 else 3.0)
                K.weld = chunk_of[i]
                if xb <= ln.X1 - 0.07 * ln.L and self.eq >= 1:            # spray chine
                    c0, c1 = A[NB], B[NB]
                    d0 = (0, s * 7 * self.scale, -1.5)
                    K.plate(c0, add(c0, d0), c1, add(c1, d0), (0, s * 0.2, -1), 2.0, P["bottom"], self.hm,
                            overlap=2.0)
                xr = st[min(i + 2, len(st) - 1)] if self.eq == 0 else xb      # coarse rubrail on low detail
                if xa < ln.X1 - 0.01 * ln.L and not (self.eq == 0 and i % 2):
                    off = 10 * self.scale if collar else 3
                    pa = (xa, s * (ln.sheer_hw(xa) + off), ln.sheer_z(xa) - (6 if collar else 4))
                    pb = ((xr, s * (ln.sheer_hw(xr) + off), ln.sheer_z(xr) - (6 if collar else 4))
                          if xr < ln.X1 else (ln.X1 + 6, 0.0, ln.sheer_z(ln.X1) - 6))
                    if collar:
                        K.rod(pa, pb, 30 * self.scale, P["collar"], "Foam", extend=6)
                    else:
                        K.rod(pa, pb, 8, P["collar"], "Rubber", extend=3)
                if self.eq >= 2 and xb <= ln.X0 + 0.80 * ln.L:            # lifting strakes
                    for t in (0.35, 0.7):
                        def lp(x, t=t, s=s):
                            k, c = ln.keel_z(x), ln.chine_hw(x)
                            zc = min(ln.chine_z(x), ln.sheer_z(x) - 8)
                            return (x, s * (c * t + 1.5), k + (zc - k) * t - 1.0)
                        K.rod(lp(xa), lp(xb), 4, P["bottom"], self.hm, extend=1)
            K.weld = chunk_of[i]
            if i > 0 and chunk_of[i - 1] != chunk_of[i] and random.Random(self.seed * 37 + i).random() < 0.5:
                K.weld = chunk_of[i - 1]          # keel tongue: the previous chunk reaches into this one
            if xb <= ln.X1 - 0.008 * ln.L:                                  # keel bar
                a, b = (xa, 0.0, ln.keel_z(xa)), (xb, 0.0, ln.keel_z(xb))
                K.obox(sub(mid(a, b), (0, 0, 3)), sub(b, a), (0, 0, 1), (norm(sub(b, a)) + 2, 10, 8),
                       P["bottom"], self.hm)
            K.weld = chunk_of[i]
            # deck
            if xa < ln.X1 - 0.008 * ln.L:
                wa, wb = ln.sheer_hw(xa) - 1, ln.sheer_hw(xb) - 1
                za, zb = ln.sheer_z(xa), ln.sheer_z(xb)
                if open_boat and xb <= x_fd + 1:
                    # open cockpit: floor + gunwale caps
                    fa, fb = ln.hull_hw(xa, floor_z) - 2, ln.hull_hw(xb, floor_z) - 2
                    for k in range(max(1, NSTRIP - 1)):
                        t0, t1 = -1 + 2 * k / max(1, NSTRIP - 1), -1 + 2 * (k + 1) / max(1, NSTRIP - 1)
                        K.plate((xa, fa * t0, floor_z), (xa, fa * t1, floor_z), (xb, fb * t0, floor_z),
                                (xb, fb * t1, floor_z), (0, 0, 1), 1.2, P["deck_a"] if (i + k) % 2 else P["deck_b"],
                                self.hm, overlap=1.0)
                    for s in (1, -1):
                        cw = 0.16 * ln.hw
                        K.plate((xa, s * (wa - cw), za), (xa, s * wa, za), (xb, s * (wb - cw), zb), (xb, s * wb, zb),
                                (0, 0, 1), 2.0, P["hull"], self.hm, overlap=1.0)
                else:
                    for k in range(NSTRIP):
                        t0, t1 = -1 + 2 * k / NSTRIP, -1 + 2 * (k + 1) / NSTRIP
                        K.weld = self.jag_chunk(i, 50 + k, 0)
                        K.plate((xa, wa * t0, za), (xa, wa * t1, za), (xb, wb * t0, zb), (xb, wb * t1, zb),
                                (0, 0, 1), 1.2, P["deck_a"] if (i + k) % 2 else P["deck_b"], self.hm, overlap=1.0)
                    K.weld = chunk_of[i]
            # frame (axis aligned web) and floats - they carry the contacts between chunks
            if xa <= last_float:
                self._frame_and_floats(i, xa, xb, last_float)
        # transom, stem
        K.weld = chunk_of[0]
        X0 = ln.X0
        c0, zc0, s0, zs0 = ln.chine_hw(X0), ln.chine_z(X0), ln.sheer_hw(X0), ln.sheer_z(X0)
        for s in (1, -1):
            y0, y1 = sorted((0, s * c0))
            K.ramp(X0 - 3, X0, y0, y1, 0, zc0, back=(0, -s, 0), bottom=(0, 0, 1), color=P["bottom"],
                   material=self.hm)
            y0, y1 = sorted((s * c0, s * (s0 + ln.flare)))
            K.ramp(X0 - 3, X0, y0, y1, zc0, zs0, back=(0, -s, 0), bottom=(0, 0, 1), color=P["hull"],
                   material=self.hm)
            if collar:
                K.rod((X0, s * (s0 + 10 * self.scale), zs0 - 6), (X0 - 18, s * (s0 - 32 * self.scale), zs0 - 6),
                      30 * self.scale, P["collar"], "Foam", extend=4)
        K.box(X0 - 3, X0, -c0, c0, zc0, zs0, P["hull"], self.hm)
        if self.eq:
            K.box(X0 - 3.5, X0 - 3, -c0 + 4, c0 - 4, zc0 + 2, zc0 + 12, P["boot"], self.hm)
        K.weld = chunk_of[len(st) - 2]
        sa = (ln.X1 - 5, 0.0, ln.keel_z(ln.X1 - 5))
        sb = (ln.X1 + 3, 0.0, ln.sheer_z(ln.X1) + 2)
        K.obox(mid(sa, sb), sub(sb, sa), (1, 0, 0.3), (norm(sub(sb, sa)) + 4, 9, 7), STEEL, self.hm)
        if open_boat:      # bulkhead closing the foredeck
            i = self.sec_of(x_fd)
            K.weld = chunk_of[i]
            hwb = ln.hull_hw(x_fd, floor_z) - 2
            K.box(x_fd - 1.5, x_fd + 1.5, -hwb, hwb, floor_z, ln.sheer_z(x_fd) - 1, P["hull"], self.hm)

    def sec_of(self, x):
        st = self.st
        for i in range(len(st) - 1):
            if st[i] <= x < st[i + 1]:
                return i
        return len(st) - 2

    def _slices(self, xa, xb, top=None):
        ln = self.ln
        zlo = max(ln.keel_z(xa), ln.keel_z(xb)) + 6
        ztop = (min(ln.sheer_z(xa), ln.sheer_z(xb)) - 5) if top is None else top
        h = ztop - zlo
        # thinner slices low in the V bottom, so the float cells follow the hull shape
        fr = (0, 0.15, 0.34, 0.6, 1.0) if h > 75 else (0, 0.25, 0.55, 1.0) if h > 35 else (0, 0.5, 1.0)
        return [(zlo + h * a, zlo + h * b) for a, b in zip(fr, fr[1:])]

    def _frame_and_floats(self, i, xa, xb, last_float):
        K, ln = self.K, self.ln
        K.weld = self.chunk_of[i]
        K.hidden = True
        top = None
        if self.kind == "motor" and xb <= self.x_fd + 1:
            top = self.floor_z - 7
        sl = self._slices(xa, xb, top)
        if not sl or sl[-1][1] - sl[0][0] < 8:
            K.hidden = False
            return
        fhw = 40.0 * self.scale
        fsl = sl if self.eq or len(sl) < 3 else [(sl[0][0], sl[1][1]), (sl[2][0], sl[-1][1])]
        for z0, z1 in fsl:
            hw = min(ln.hull_hw(xa, z0) - 3, fhw)
            if hw > 5:
                K.box(xa - 1, xa + 1, -hw, hw, z0, z1, HIDDEN, "Plastic", connectors=4095)
        if xb <= last_float + 1:
            self.float_cells.append((i, xa, xb, sl))
            for k, (z0, z1) in enumerate(sl):
                hw = min(ln.hull_hw(xa, z0), ln.hull_hw(xb, z0)) - 5
                if hw < 6 or z1 - z0 < 5:
                    continue
                if (i, k) in self.reserved:
                    continue
                if k >= len(sl) - 2 and hw > 30:
                    # upper cells split port / starboard: buoyancy shifts to the low side when heeling
                    for y0, y1 in ((-hw, 0.0), (0.0, hw)):
                        K.box(xa + 1, xb - 1, y0, y1, z0, z1, HIDDEN, "Float", "Float", connectors=4095)
                else:
                    K.box(xa + 1, xb - 1, -hw, hw, z0, z1, HIDDEN, "Float", "Float", connectors=4095)
        K.hidden = False

    # ------------------------------------------------------------------ open boat buoyancy
    def lockers(self):
        """Open motor boat: buoyant side lockers, stern seat box (real boats are foam-filled here)."""
        if self.kind != "motor":
            return
        K, ln, P = self.K, self.ln, self.P
        fz, st = self.floor_z, self.st
        w = 0.30 * ln.hw
        for i in range(len(st) - 1):
            xa, xb = st[i], st[i + 1]
            if xa < ln.X0 + 0.11 * ln.L - 1 or xb > self.x_fd + 1:
                continue
            K.weld = self.skin_chunk(self.chunk_of, i, 7)
            yo = min(ln.hull_hw(xa, fz + 2), ln.hull_hw(xb, fz + 2)) - 3
            zt = min(ln.sheer_z(xa), ln.sheer_z(xb)) - 2.5
            for s in (1, -1):
                y0, y1 = sorted((s * (yo - w), s * yo))
                K.box(xa + 0.5, xb - 0.5, y0, y1, fz + 1.5, zt, P["cabin_d"], "Float", "Float", connectors=4095)
                if self.eq >= 1:
                    yi = s * (yo - w)
                    y0, y1 = sorted((yi, yi - s * 1.5))
                    K.box(xa + 0.5, xb - 0.5, y0, y1, fz + 1.5, zt - 4, P["hull"], self.hm)
        K.weld = self.chunk_of[0]
        x0, x1 = ln.X0 + 3, ln.X0 + 0.11 * ln.L - 1
        yb = ln.hull_hw(x1, fz + 2) - 3
        K.box(x0, x1, -yb, yb, fz + 1.5, fz + 40, P["cabin_d"], "Float", "Float", connectors=4095)
        if self.eq >= 1:
            K.box(x0 + 1, x1 - 2, -yb + 4, yb - 4, fz + 40, fz + 47, (40, 40, 42, 255), "Rubber")
            K.box(x0, x0 + 8, -yb + 4, yb - 4, fz + 47, fz + 72, (40, 40, 42, 255), "Rubber")

    # ------------------------------------------------------------------ trim
    def balance(self):
        """Trim by thinning hidden float cells from below: aft cells when bow heavy, forward cells when
        stern heavy (removing buoyancy at one end moves the centre of buoyancy to the other)."""
        K = self.K
        pos = {it[0]: n for n, it in enumerate(K.items)}
        info = analyse(self)
        for _ in range(120):
            t = info["pitch"]
            if -1.5 <= t <= 0.6 or info["reserve"] < 1.35:
                break
            aft = t > 0
            cand = [it for it in K.items if it[4] and K.v.bricks[it[0]].type == "Float"
                    and K.v.bricks[it[0]].get("BrickSize")[2] > 6 and (it[1][0] < -0.1 * self.L if aft
                                                                       else it[1][0] > 0.1 * self.L)]
            if not cand:
                break
            idx, c, d, vol, hid = (min if aft else max)(cand, key=lambda it: round(it[1][0]))
            br = K.v.bricks[idx]
            sx, sy, sz = br.get("BrickSize")
            cut = min(sz - 5.0, max(4.0, 0.3 * sz))
            nz = sz - cut
            nc = (c[0], c[1], c[2] + cut / 2)
            br.set("BrickSize", (sx, sy, nz))
            br.pos = nc
            K.items[pos[idx]] = (idx, nc, d, sx * sy * nz, hid)
            info = analyse(self)
        return info

    # ------------------------------------------------------------------ stabilisers
    def plan_stabilisers(self):
        """Reserve float cells for the stabiliser thrusters before the hull is built."""
        self.reserved = set()
        self.stab = None
        ln = self.ln
        if self.kind == "motor":
            self.floor_z = ln.D * 0.46
            self.x_fd = ln.X0 + 0.70 * ln.L
        st = self.stations()
        last_float = ln.X1 - 0.06 * ln.L
        cand = [i for i in range(len(st) - 1) if st[i + 1] <= last_float + 1 and st[i + 1] - st[i] > 40]

        def near(f):
            return min(cand, key=lambda i: abs((st[i] + st[i + 1]) / 2 - (ln.X0 + f * ln.L)))
        if len(cand) >= 2:
            im, ifw = near(0.37), near(0.74)
            if im == ifw:
                ifw = max(cand)
            if im != ifw:
                self.stab = (im, ifw)
                for i in (im, ifw):
                    top = None
                    if self.kind == "motor" and st[i + 1] <= self.x_fd + 1:
                        top = self.floor_z - 7
                    sl = self._slices(st[i], st[i + 1], top)
                    self.reserved.add((i, len(sl) - 1))

    def stabilisers(self):
        if not self.stab:
            return
        K, ln = self.K, self.ln
        im, ifw = self.stab
        cells = {c[0]: c for c in self.float_cells}
        sc = 6.0                              # re-scaled by mass and size in tune()
        self.stab_thr = []
        roll_sw = pitch_sw = None
        for which, i in (("roll", im), ("pitch", ifw)):
            if i not in cells:
                continue
            _, xa, xb, sl = cells[i]
            z0, z1 = sl[-1]
            hw = min(ln.hull_hw(xa, z0), ln.hull_hw(xb, z0)) - 5
            x0, x1 = xa + 1, xb - 1
            cell = 18.0
            K.weld = self.chunk_of[i]
            K.hidden = True
            if which == "roll":
                K.box(x0, x1, -hw + cell, hw - cell, z0, z1, HIDDEN, "Float", "Float", connectors=4095)
                fx, fz = (x0 + x1) / 2, z1
                ox = min(30.0, (x1 - x0) / 2 - 4)

                def logic(typ, y, X, Zh, extra):
                    return K.obox((fx - ox, y, fz + 2), X, Zh, (4, 4, 4), (240, 140, 40, 255), "Plastic", typ,
                                  extra=extra)
                ra = logic("SensorBrick", -20, (1, 0, 0), (0, 0, 1),
                           {"SensorType": "Roll", "OutputChannel.MinIn": -15.0, "OutputChannel.MaxIn": 15.0,
                            "OutputChannel.MinOut": -10.0, "OutputChannel.MaxOut": 10.0})
                rr = logic("SensorBrick", -10, (0, 0, -1), (1, 0, 0),
                           {"SensorType": "NormalAngularSpeed", "OutputChannel.MinIn": -60.0,
                            "OutputChannel.MaxIn": 60.0})
                roll_sw = logic("SwitchBrick", 0, (1, 0, 0), (0, 0, 1),
                                {"InputChannel.InputAxis": "Custom", "InputChannel.SourceBricks": [src(ra), src(rr)]})
                pa = logic("SensorBrick", 10, (1, 0, 0), (0, 0, 1),
                           {"SensorType": "Pitch", "OutputChannel.MinIn": -12.0, "OutputChannel.MaxIn": 12.0,
                            "OutputChannel.MinOut": -10.0, "OutputChannel.MaxOut": 10.0})
                pr = logic("SensorBrick", 20, (1, 0, 0), (0, 1, 0),
                           {"SensorType": "NormalAngularSpeed", "OutputChannel.MinIn": -40.0,
                            "OutputChannel.MaxIn": 40.0})
                pitch_sw = logic("SwitchBrick", 30, (1, 0, 0), (0, 0, 1),
                                 {"InputChannel.InputAxis": "Custom", "InputChannel.SourceBricks": [src(pa), src(pr)]})
                for s in (1, -1):
                    c = ((x0 + x1) / 2, s * (hw - cell / 2), (z0 + z1) / 2)
                    for up, k in (((0, 0, 1), s), ((0, 0, -1), -s)):
                        t = K.obox(c, (1, 0, 0), up, (15, cell, 20), (40, 40, 42, 255), "Plastic", "ThrusterBrick",
                                   extra={"InputChannel.InputAxis": "Custom",
                                          "InputChannel.SourceBricks": [src(roll_sw)], "InputScale": k * sc})
                        self.stab_thr.append((t, "roll", k))
            else:
                for s in (1, -1):
                    y0, y1 = sorted((s * cell / 2, s * hw))
                    if abs(y1 - y0) > 4:
                        K.box(x0, x1, y0, y1, z0, z1, HIDDEN, "Float", "Float", connectors=4095)
                c = ((x0 + x1) / 2, 0.0, (z0 + z1) / 2)
                for up, k in (((0, 0, 1), -1), ((0, 0, -1), 1)):
                    t = K.obox(c, (1, 0, 0), up, (15, 15, 15), (40, 40, 42, 255), "Plastic", "ThrusterBrick",
                               extra={"InputChannel.InputAxis": "Custom",
                                      "InputChannel.SourceBricks": [src(pitch_sw)] if pitch_sw is not None else [],
                                      "InputScale": k * sc})
                    self.stab_thr.append((t, "pitch", k))
            K.hidden = False

    # ------------------------------------------------------------------ outboards
    def outboards(self):
        K, ln, P = self.K, self.ln, self.P
        n = self.sty.get("outboards") or KINDS[self.kind]["outboards"]
        if self.eq == 0:
            n = min(n, 2)
        k = max(0.55, min(1.15, self.scale))
        ys = {1: [0.0], 2: [0.45 * ln.hw, -0.45 * ln.hw], 3: [0.55 * ln.hw, 0.0, -0.55 * ln.hw]}[n]
        if n == 3:
            k = min(k, 0.9)
        fwd, rev = 10.0, -5.0                 # re-scaled by mass in tune()
        self.main_thr = []
        X0, zb = ln.X0, ln.D - 8
        eng = rgba(P["engine"])
        for yc in ys:
            K.weld = self.chunk_of[0]
            XA = X0 - 22
            K.box(X0 - 32, X0 - 3, yc - 16 * k, yc + 16 * k, zb - 34 * k, zb, STEEL, "Aluminium")
            K.fixed("Actuator_1sx1sx1s_Bottom", (XA, yc, zb), color=STEEL, material="Aluminium",
                    extra={"ActuatorMode": "Seeking", "InputChannel.InputAxis": "Steering",
                           "MinLimit": -30.0, "MaxLimit": 30.0})
            self.protect.add(K.new_weld())
            K.fixed("Actuator_1sx1sx1s_Top", (XA, yc, zb + 5), color=STEEL, material="Aluminium")
            z = zb + 10
            K.box(XA - 26 * k, XA + 12 * k, yc - 14 * k, yc + 14 * k, z, z + 4, STEEL, "Aluminium", connectors=0)
            K.box(XA - 34 * k, XA - 26 * k, yc - 10 * k, yc + 10 * k, z, z + 30 * k, eng, "Aluminium", connectors=0)
            cx1, cx0 = XA - 34 * k, XA - 88 * k
            cz0 = z + 8 * k
            K.box(cx0, cx1, yc - 26 * k, yc + 26 * k, cz0, cz0 + 22 * k, eng, "Plastic", connectors=0)
            K.box(cx0, cx1, yc - 24 * k, yc + 24 * k, cz0 + 22 * k, cz0 + 46 * k, eng, "Fuel", "TankBrick",
                  extra={"FuelType": "RocketFuel"}, connectors=0)
            K.ramp(cx0 - 10 * k, cx0, yc - 26 * k, yc + 26 * k, cz0, cz0 + 22 * k, back=(1, 0, 0), bottom=(0, 0, -1),
                   color=eng, typ="ScalableRampRounded", connectors=0)
            K.ramp(cx0, cx1, yc - 26 * k, yc + 26 * k, cz0 + 46 * k, cz0 + 60 * k, back=(1, 0, 0),
                   bottom=(0, 0, -1), color=eng, typ="ScalableRampRounded", connectors=0)
            if self.eq >= 1:
                K.box(cx0 + 2 * k, cx1 - 6 * k, yc - 26.5 * k, yc + 26.5 * k, cz0 + 32 * k, cz0 + 36 * k,
                      (150, 28, 28, 255), "Plastic", connectors=0)
            # thrusters (welded with the outboard so they turn with it)
            t1 = K.obox((cx0 - 15 * k, yc, cz0 + 34 * k), (0, 0, -1), (1, 0, 0), (24 * k, 24 * k, 30 * k),
                        (44, 44, 46, 255), "Plastic", "ThrusterBrick", extra={"InputScale": fwd}, connectors=0)
            t2 = K.obox((cx1 + 15 * k, yc, cz0 + 30 * k), (0, 0, 1), (-1, 0, 0), (16 * k, 16 * k, 30 * k),
                        (44, 44, 46, 255), "Plastic", "ThrusterBrick", extra={"InputScale": rev}, connectors=0)
            self.main_thr += [(t1, "out"), (t2, "rev")]
            # leg, plate, gearcase, skeg, propeller
            zg = max(10.0, 0.19 * ln.D)
            lx0, lx1 = cx0 + 8 * k, cx0 + 34 * k
            K.box(lx0, lx1, yc - 8 * k, yc + 8 * k, zg + 14 * k, cz0, eng, "Aluminium", connectors=0)
            if self.eq >= 1:
                K.box(cx0 - 8 * k, cx1 - 6 * k, yc - 19 * k, yc + 19 * k, zg + 10 * k, zg + 14 * k, eng,
                      "Aluminium", connectors=0)
            K.rod((cx0 - 16 * k, yc, zg), (cx1 - 10 * k, yc, zg), 18 * k, eng, "Aluminium", connectors=0)
            if self.eq >= 1:
                K.box(lx0 + 2 * k, lx0 + 14 * k, yc - 1.5, yc + 1.5, zg - 26 * k, zg - 8 * k, eng, "Aluminium",
                      connectors=0)
            hub0, hub1 = cx0 - 30 * k, cx0 - 16 * k
            K.rod((hub0, yc, zg), (hub1, yc, zg), 12 * k, PROP, "Copper", connectors=0)
            for j in range(3):
                ang = math.radians(90 + 120 * j)
                r = (0, math.cos(ang), math.sin(ang))
                chord = unit(add((1, 0, 0), mul(cross((1, 0, 0), r), 0.45)))
                K.obox(add(((hub0 + hub1) / 2, yc, zg), mul(r, 14 * k)), chord, cross(chord, r),
                       (11 * k, 18 * k, 1.6), PROP, "Copper", connectors=0)
            if self.eq >= 1:
                K.obox((hub0 - 5 * k, yc, zg), (0, 0, -1), (-1, 0, 0), (8 * k, 8 * k, 10 * k), PROP, "Copper",
                       "ScalableConeFlat", connectors=0)
        self.n_out = n
        K.weld = self.chunk_of[0]
        zj = max(0.30 * ln.D, ln.chine_z(X0) * 0.5 + 12)
        for s in (1, -1):
            yj = s * 0.25 * ln.hw
            d = 4 if self.eq else 0
            if d:
                K.box(X0 - 4, X0, yj - 12, yj + 12, zj - 12, zj + 12, STEEL, "Aluminium")
            t = K.obox((X0 - d - 11.25, yj, zj), (0, 0, -1), (1, 0, 0), (18, 18, 22.5), (44, 44, 46, 255), "Plastic",
                       "ThrusterBrick", extra={"InputScale": 15.0})
            self.main_thr.append((t, "jet"))

    # ------------------------------------------------------------------ cabin
    def cabin(self):
        K, ln, P = self.K, self.ln, self.P
        if self.kind == "motor":
            return self.console()
        mil = self.kind == "military"
        sty = self.sty
        mid, length = (0.5675, 0.295) if mil else (0.52, 0.24)
        length = max(260.0 if mil else 210.0, length * ln.L * sty["cab_len"])
        cmid = ln.X0 + (mid + sty["cab_shift"]) * ln.L
        cx0, cx1 = cmid - length / 2, cmid + length / 2
        cx1 = min(cx1, ln.X0 + 0.74 * ln.L)
        cx0 = max(min(cx0, cx1 - length), ln.X0 + 0.30 * ln.L)
        cy = sty["cab_w"] * ln.hw
        cyt = cy - 8
        D = ln.D
        floor = D + 5
        zs, zr = floor + sty["zs"], floor + sty["zr"]
        wx = cx1 - sty["rake"]
        self.cab = dict(cx0=cx0, cx1=cx1, cy=cy, floor=floor, zr=zr, wx=wx, zs=zs, D=D, dx1=cx0 + 76)
        cab_w = K.new_weld()
        self.cab_w = cab_w
        cabin, cabd, fr = P["cabin"], P["cabin_d"], P["frame"]
        side_doors = mil
        dx0, dx1 = cx0 + 14, cx0 + 76
        K.box(cx0 + 2, cx1 - 2, -cy + 2, cy - 2, floor - 2, floor, P["deck_b"], "Aluminium")
        if self.eq:
            for x in [cx0 + 20 + j * 60 for j in range(int((cx1 - cx0 - 40) / 60) + 1)]:
                K.box(x - 3, x + 3, -cy + 2, cy - 2, D, floor - 2, fr, "Aluminium")
        else:
            K.box(cx0 + 10, cx1 - 10, -cy + 10, cy - 10, D, floor - 2, fr, "Plastic")
        n_win = max(1, int((wx - 8 - (dx1 + 11 if side_doors else cx0 + 12)) / self.sty["win_w"])) if self.eq else 1
        armoured = {}
        for s in (1, -1):
            y0, y1 = sorted((s * (cy - 2), s * cy))
            if side_doors:
                K.box(cx0, dx0 - 1, y0, y1, D, zs, cabin, "Aluminium")
                K.box(dx1 + 1, cx1, y0, y1, D, zs, cabin, "Aluminium")
                K.box(dx0 - 1, dx1 + 1, y0, y1, D, floor, cabin, "Aluminium")
            else:
                K.box(cx0, cx1, y0, y1, D, zs, cabin, "Aluminium")
            up = unit((0, -s * (cy - cyt), zr - zs))
            outn = unit((0, s * (zr - zs), (cy - cyt)))
            band_h = norm((0, cy - cyt, zr - zs))
            segs = [(cx0, (dx0 - 1) if side_doors else cx0 + 12, "p")]
            start = (dx1 + 1) if side_doors else cx0 + 12
            if side_doors and self.eq:
                segs.append((dx1 + 1, dx1 + 11, "p"))
                start = dx1 + 11
            span = (wx - 8 - start) / n_win
            for w in range(n_win):
                a = start + w * span
                segs.append((a, a + span - 8, "g"))
                if w < n_win - 1:
                    segs.append((a + span - 8, a + span, "p"))
            segs.append((wx - 8, wx, "p"))
            for a, b, kind in segs:
                if b - a < 1:
                    continue
                cpt = add((0, s * cy, zs), mul(up, band_h / 2))
                cpt = sub(((a + b) / 2, cpt[1], cpt[2]), mul(outn, 1.0))
                if kind == "p":
                    K.obox(cpt, (1, 0, 0), outn, (b - a, band_h + 2, 3.0), fr, "Aluminium")
                else:
                    K.obox(cpt, (1, 0, 0), outn, (b - a + 1, band_h, 1.5), GLASS, "Glass")
                    if self.faction == "south" and not armoured.get(s) and b - a > 30:
                        armoured[s] = True        # improvised steel shield bolted over a window
                        K.obox(add(cpt, mul(outn, 2.2)), (1, 0, 0), outn, ((b - a) * 0.55, band_h * 0.7, 2.0),
                               (64, 66, 60, 255), "Steel")
            if side_doors:
                cpt = sub(add(((dx0 + dx1) / 2, s * cy, zs), mul(up, band_h * 0.92)), mul(outn, 1.0))
                K.obox(cpt, (1, 0, 0), outn, (dx1 - dx0 + 2, band_h * 0.17, 3.0), cabin, "Aluminium")
            X, Y, Z = frame((1, 0, 0), up)
            tri_c = sub(add((wx + (cx1 - wx) / 2, s * cy, zs), mul(up, band_h / 2)), mul(outn, 1.0))
            K.brick("ScalableRamp", tri_c, X, Y, Z, (cx1 - wx, 2.0, band_h), GLASS, "Glass", vf=0.5)
            if self.eq >= 1:
                K.rod((cx0 + 90, s * (cy + 6), D + 40), (cx1 - 60, s * (cy + 6), D + 40), 3.5, CHROME)
                for x in (cx0 + 90, cx1 - 60):
                    K.rod((x, s * cy, D + 40), (x, s * (cy + 6), D + 40), 3, CHROME)
        # front wall, windscreen, roof
        K.box(cx1 - 2, cx1, -cy, cy, D, zs, cabin, "Aluminium")
        for s in (1, -1):
            K.plate((cx1, s * 3, zs), (cx1, s * (cy - 2), zs), (wx, s * 3, zr), (wx, s * (cyt - 2), zr),
                    (1, 0, 0.8), 1.5, GLASS, "Glass", overlap=1.0)
            K.plate((cx1, s * (cy - 4), zs), (cx1, s * cy, zs), (wx, s * (cyt - 4), zr), (wx, s * cyt, zr),
                    (1, 0, 0.8), 3.0, fr, "Aluminium", overlap=1.0)
            if self.eq >= 2:
                K.rod((cx1 - 6, s * 0.5 * cy, zs + 6), (cx1 - 26, s * 0.3 * cy, zs + 33), 1.6, fr, "Steel")
        if self.eq:
            K.plate((cx1, -3, zs), (cx1, 3, zs), (wx, -3, zr), (wx, 3, zr), (1, 0, 0.8), 3.0, fr, "Aluminium",
                    overlap=1.0)
        K.box(cx0 - 2, wx + 4, -cyt + 4, cyt - 4, zr, zr + 3, P["roof"], "Aluminium")
        for s in (1, -1):
            y0, y1 = sorted((s * (cyt - 4), s * (cyt + 4)))
            K.ramp(cx0 - 2, wx + 4, y0, y1, zr, zr + 6, back=(0, -s, 0), bottom=(0, 0, -1), color=cabd,
                   material="Aluminium", typ="ScalableRampRounded")
        K.ramp(wx + 4, wx + 12, -cyt + 4, cyt - 4, zr, zr + 6, back=(-1, 0, 0), bottom=(0, 0, -1), color=cabd,
               material="Aluminium", typ="ScalableRampRounded")
        rt = zr + 3
        self.cab["rt"] = rt
        # aft wall and door opening
        for s in (1, -1):
            y0, y1 = sorted((s * 35, s * cy))
            K.box(cx0, cx0 + 2, y0, y1, D, zs, cabin, "Aluminium")
            K.box(cx0, cx0 + 2, y0, y1, zs + 50, zr, cabin, "Aluminium")
            if cy > 70 and self.eq >= 1:
                g0, g1 = sorted((s * 42, s * (cy - 15)))
                K.box(cx0 - 0.5, cx0 + 1, g0, g1, zs, zs + 50, GLASS, "Glass")
                for a, b in ((35, 42), (cy - 15, cy)):
                    y0, y1 = sorted((s * a, s * b))
                    K.box(cx0, cx0 + 2, y0, y1, zs, zs + 50, fr, "Aluminium")
            else:
                K.box(cx0, cx0 + 2, y0, y1, zs, zs + 50, cabin, "Aluminium")
        K.box(cx0, cx0 + 2, -35, 35, floor + 118, zr, cabin, "Aluminium")
        # interior
        dash_x = cx1 - 46
        K.box(dash_x, dash_x + 2, -cy + 3, cy - 3, floor, floor + 60, cabd, "Plastic")
        K.box(dash_x, cx1 - 2, -cy + 3, cy - 3, floor + 58, floor + 60, cabd, "Plastic")
        K.box(dash_x + 3, cx1 - 3, -cy + 5, cy - 5, floor + 1, floor + 57, HIDDEN, "Float", "Float")
        helm_x = dash_x - 65
        seats = [(helm_x, 0.47 * cy), (helm_x, -0.47 * cy)]
        if cx1 - cx0 > 280 and self.eq >= 1:
            seats += [(helm_x - 85, 0.47 * cy), (helm_x - 85, -0.47 * cy)]
        self.seats = []
        ped_h = 16.0 if (self.eq >= 1 and sty["pedestal"]) else 0.0
        for n, (x, y) in enumerate(seats):
            h = ped_h if n < 2 else 0.0
            if h:                                    # helm chairs on a post with a round base
                K.rod((x, y, floor), (x, y, floor + 2), 34, fr, "Steel")
                K.rod((x, y, floor + 2), (x, y, floor + h), 9, CHROME)
            self.seats.append(K.fixed("Seat_2x2x7s", (x, y, floor + h - 1), color=(38, 38, 40, 255),
                                      material="Rubber"))
        if self.eq >= 1:
            wy = 0.47 * cy
            # console face with screens and gauges, wheel on a column, throttle, compass, footrest
            K.ramp(dash_x - 14, dash_x, -cy + 3, cy - 3, floor + 46, floor + 60, back=(1, 0, 0), bottom=(0, 0, -1),
                   color=cabd, material="Plastic")
            for j in range(sty["screens"]):
                yy = -0.2 * cy - j * 0.22 * cy
                K.obox((dash_x - 7.5, yy, floor + 53.5), (0, -1, 0), unit((-1, 0, 1)), (0.18 * cy, 11, 1.0),
                       (8, 10, 12, 255), "Plastic", "TextBrick",
                       extra={"Text": ("GPS", "SONAR", "RADAR")[j], "TextColor": (60, 200, 230, 255)})
            for y in (0.28 * cy, 0.66 * cy):
                K.obox((dash_x - 0.5, y, floor + 30), (0, 1, 0), (-1, 0, 0), (12, 12, 1.0), (24, 24, 24, 255),
                       "Plastic", "ImageCylinder", extra={"Image": "Gauge"})
            K.rod((dash_x, wy, floor + 25), (dash_x - 14, wy, floor + 34), 5, fr, "Steel")
            K.obox((dash_x - 16, wy, floor + 35), (0, 1, 0), unit((-1, 0, 0.6)), (40, 40, 3), (28, 28, 28, 255),
                   "Rubber", "ScalableZylinder", vf=0.785)
            K.obox((dash_x - 16, wy, floor + 35), (0, 1, 0), unit((-1, 0, 0.6)), (8, 8, 6), CHROME, "Chrome",
                   "ScalableZylinder", vf=0.785)
            K.box(dash_x - 12, dash_x, wy - 30, wy - 18, floor + 40, floor + 46, (30, 30, 32, 255), "Plastic")
            K.rod((dash_x - 6, wy - 24, floor + 46), (dash_x - 14, wy - 24, floor + 60), 2.2, CHROME)
            K.box(dash_x - 18, dash_x - 12, wy - 27, wy - 21, floor + 59, floor + 64, (180, 30, 30, 255), "Plastic")
            K.box(dash_x - 12, dash_x - 2, 0.05 * cy - 6, 0.05 * cy + 6, floor + 60, floor + 62, cabd, "Plastic")
            K.box(dash_x - 12, dash_x - 2, 0.05 * cy - 6, 0.05 * cy + 6, floor + 62, floor + 70, (20, 20, 22, 255),
                  "Plastic", typ="ScalableHemisphere")
            K.rod((dash_x - 20, wy - 15, floor + 8), (dash_x - 20, wy + 15, floor + 8), 2.5, CHROME)
        if self.eq >= 2:
            K.obox((dash_x - 0.5, -0.47 * cy, floor + 15), (0, -1, 0), (-1, 0, 0), (36, 18, 1.0), (10, 14, 12, 255),
                   "Plastic", "TextBrick", extra={"Text": "RADAR 6nm", "TextColor": (60, 220, 90, 255)})
            K.box(dash_x - 40, dash_x - 10, -14, 14, floor, floor + 45, cabd, "Plastic")
        # doors
        self.doors(side_doors, dx0, dx1)
        # roof equipment
        K.weld = cab_w
        if mil:
            self.tower_and_turret()
        dome_x = wx - 0.25 * (wx - cx0)
        if self.eq >= 1 and sty["dome"]:
            K.rod((dome_x, 0, rt), (dome_x, 0, rt + 8), 34, cabd, "Aluminium")
            K.rod((dome_x, 0, rt + 8), (dome_x, 0, rt + 22), 60, WHITE, "Plastic")
            K.box(dome_x - 30, dome_x + 30, -30, 30, rt + 22, rt + 42, WHITE, "Plastic", typ="ScalableHemisphere")
        for s in (1, -1):
            K.box(wx - 6, wx + 4, s * (cyt - 18) - 5, s * (cyt - 18) + 5, rt, rt + 10,
                  (20, 60, 230, 255) if mil else (240, 170, 30, 255), "Glow", "LightBrick",
                  extra={"InputChannel.InputAxis": "Beacon", "Brightness": 0.8, "FlashSequence": "Blinker_Sequence"})
            y0, y1 = sorted((s * cy, s * (cy + 4)))
            K.box(cx1 - 18, cx1 - 6, y0, y1, zs - 19, zs - 9, (20, 200, 70, 255) if s > 0 else (210, 25, 25, 255),
                  "Glow", "LightBrick", extra={"Brightness": 0.5, "InputChannel.InputAxis": "Headlight"})
            if self.eq >= 1 and sty["horns"]:
                K.obox((wx - 23, s * 42, rt + 6), (0, 0, -1), (1, 0, 0), (8, 8, 22), CHROME, "Chrome", "ScalableConeFlat")
                K.box(wx - 40, wx - 33, s * 42 - 3, s * 42 + 3, rt, rt + 10, CHROME, "Chrome")
            if self.eq >= 2:
                for x in (cx0 + 120, wx - 25):
                    K.rod((x, s * (cyt - 9), rt), (x, s * (cyt - 9), rt + 8), 3, CHROME)
                K.rod((cx0 + 116, s * (cyt - 9), rt + 8), (wx - 21, s * (cyt - 9), rt + 8), 3.5, CHROME)
        K.box(wx - 12, wx, -6, 6, rt, rt + 8, P["frame"], "Aluminium")
        K.obox((wx - 6, 0, rt + 14), (0, 1, 0), (1, 0, 0), (12, 12, 12), (230, 230, 220, 255), "Plastic",
               "LightConeFlat", extra={"Brightness": 1.0, "LightDirection": "Z", "LightConeAngle": 18.0,
                                       "InputChannel.InputAxis": "Headlight"})
        if not mil and self.eq >= 1 and sty["flybridge"]:
            # open upper helm on the wheelhouse roof: rails, console, seat, ladder
            fx0, fx1, fy = cx0 + 4, wx - 4, cyt - 8
            n_p = max(2, int((fx1 - fx0) / 70) + 1)
            for s in (1, -1):
                pts = [(fx0 + (fx1 - fx0) * j / (n_p - 1), s * fy, rt) for j in range(n_p)]
                for p_ in pts:
                    K.rod(p_, add(p_, (0, 0, 55)), 3, CHROME)
                K.rod(add(pts[0], (0, 0, 55)), add(pts[-1], (0, 0, 55)), 3.5, CHROME, extend=2)
            K.rod((fx1, -fy, rt + 55), (fx1, fy, rt + 55), 3.5, CHROME, extend=2)
            K.box(fx1 - 30, fx1 - 4, -30, 30, rt, rt + 48, P["cabin"], "Plastic")
            K.ramp(fx1 - 30, fx1 - 4, -30, 30, rt + 48, rt + 62, back=(-1, 0, 0), bottom=(0, 0, -1), color=GLASS,
                   material="Glass")
            K.box(fx1 - 90, fx1 - 60, -45, 45, rt, rt + 30, P["cabin_d"], "Plastic")
            K.box(fx1 - 92, fx1 - 84, -45, 45, rt + 30, rt + 62, (40, 40, 42, 255), "Rubber")
            for yy in (-18, 18):
                K.rod((cx0 - 30, yy, D), (cx0 - 2, yy, rt + 2), 3, CHROME)
            for j in range(1, 5):
                zz = D + (rt - D) * j / 5
                xx = cx0 - 30 + 28 * j / 5
                K.rod((xx, -18, zz), (xx, 18, zz), 2.5, CHROME)
        if not mil:
            mx = cx0 + 20 if sty["mast_aft"] else (cx0 + wx) / 2
            mh = sty["mast_h"]
            K.rod((mx, 0, rt), (mx, 0, rt + mh), 4, P["frame"], "Aluminium")
            K.box(mx - 4, mx + 4, -4, 4, rt + mh, rt + mh + 6, (240, 240, 230, 255), "Glow", "LightBrick",
                  extra={"Brightness": 0.6, "InputChannel.InputAxis": "Headlight"})
            if self.eq >= 1 and sty["yard"]:
                K.box(mx - 3, mx + 3, -30, 30, rt + mh * 0.7, rt + mh * 0.7 + 4, P["frame"], "Aluminium")
        if self.eq >= 1 and not mil:            # patrol boats carry their whips on the stern rail
            for j in range(sty["antennas"]):
                ax = cx0 + 10 + 14 * j
                ay = (cyt - 14) * (1 if j % 2 else -1)
                K.rod((ax, ay, rt), (ax, ay, rt + 80 + 25 * j), 2.0, (30, 30, 32, 255), "Rubber")

    def doors(self, side_doors, dx0, dx1):
        K, P, c = self.K, self.P, self.cab
        cx0, cy, floor = c["cx0"], c["cy"], c["floor"]
        door_specs = [("aft", (cx0 + 8, 38.0, floor), (0.0, -90.0, 0.0),
                       ((cx0 - 0.5, -33.0, floor + 6), (cx0 + 1.5, 33.0, floor + 117)),
                       ((cx0 - 1.0, -24.0, floor + 55), (cx0 - 0.5, 24.0, floor + 100)), {"MaxLimit": 95.0}, "Action3")]
        if side_doors:
            for s in (1, -1):
                y0, y1 = sorted((s * (cy - 2.5), s * (cy - 0.5)))
                gy0, gy1 = sorted((s * (cy - 3.0), s * (cy + 0.0)))
                door_specs.append(("side", (dx1 + 6, s * (cy - 8.5), floor), (0.0, 180.0, 0.0),
                                   ((dx0, y0, floor + 6), (dx1 - 1, y1, floor + 117)),
                                   ((dx0 + 10, gy0, floor + 55), (dx1 - 10, gy1, floor + 100)),
                                   {"MaxLimit": 95.0} if s > 0 else {"MinLimit": -95.0, "SpeedFactor": -1.0}, "Action4"))
        K.weld = self.cab_w                       # door switches welded to the wheelhouse
        switches = {}
        for key, y in (("Action3", 0.62 * cy), ("Action4", -0.62 * cy)):
            if key == "Action4" and not side_doors:
                continue
            switches[key] = K.box(cx0 + 2, cx0 + 6, y - 5, y + 5, floor + 35, floor + 45, (200, 40, 40, 255),
                                  "Plastic", "SwitchBrick",
                                  extra={"InputChannel.InputAxis": key, "bReturnToZero": False, "SwitchName": "Door"})
        for kind, hinge, rot, leaf, glass, lim, key in door_specs:
            K.weld = self.cab_w
            X, Y, Z = frame((math.cos(math.radians(rot[1])), math.sin(math.radians(rot[1])), 0), (0, 0, 1))
            extra = {"ActuatorMode": "Seeking", "InputChannel.InputAxis": "Custom",
                     "InputChannel.SourceBricks": [src(switches[key])]}
            extra.update(lim)
            K.brick("Actuator_1sx1sx1s_Bottom", hinge, X, Y, Z, None, STEEL, "Aluminium", extra)
            self.protect.add(K.new_weld())
            K.fixed("Actuator_1sx1sx1s_Top", add(hinge, (0, 0, 5)), color=STEEL, material="Aluminium")
            (x0, y0, z0), (x1, y1, z1) = leaf
            K.box(x0, x1, y0, y1, z0, z1, P["cabin_d"], "Aluminium", connectors=0)
            (gx0, gy0, gz0), (gx1, gy1, gz1) = glass
            if self.eq >= 1:
                K.box(gx0, gx1, gy0, gy1, gz0, gz1, GLASS, "Glass", connectors=0)
        K.weld = self.cab_w

    def tower_and_turret(self):
        K, P, c = self.K, self.P, self.cab
        cx0, rt = c["cx0"], c["rt"]
        tl = 100.0 if self.sty["gun_bow"] else 142.0         # room for the mast outside the turret's swing
        tl = min(tl, c["wx"] - cx0 - 14)
        tx0, tx1, ty = cx0, cx0 + tl, 78.0 * min(1.0, c["cy"] / 105)
        tz = rt + self.sty["tower_h"]
        cabin, cabd, fr = P["cabin"], P["cabin_d"], P["frame"]
        tw = K.new_weld()                     # the tower can be shot off the roof as one piece
        K.box(tx0, tx1 - 12, -ty, ty, tz - 4, tz, cabd, "Aluminium")
        for s in (1, -1):
            y0, y1 = sorted((s * (ty - 3), s * ty))
            K.box(tx0, tx1 - 12, y0, y1, rt, tz - 4, cabin, "Aluminium")
            if self.eq >= 1:
                for j in range(5):
                    K.box(tx0 + 12 + j * 14, tx0 + 22 + j * 14, s * ty - 1, s * ty + 1, rt + 12, rt + 34, fr, "Aluminium")
        K.box(tx0, tx0 + 3, -ty, ty, rt, tz - 4, cabin, "Aluminium")
        K.plate((tx1 + 12, -ty, rt), (tx1 + 12, ty, rt), (tx1 - 12, -ty, tz), (tx1 - 12, ty, tz), (1, 0, 1), 3.0,
                cabin, "Aluminium", overlap=1.0)
        if self.eq >= 1:
            K.box(tx0 + 3, tx1 - 16, -ty + 3, ty - 3, rt, tz - 4, HIDDEN, "Float", "Float")
        if self.eq >= 1 and self.sty["lattice"]:
            top = (tx0 + 8, 0, tz + 110)
            for lx, ly in ((tx0 - 4, -14), (tx0 - 4, 14), (tx0 + 16, 0)):
                K.rod((lx, ly, tz), top, 4, fr, "Aluminium", extend=2)
            for zz, half in ((tz + 45, 20), (tz + 85, 14)):
                K.box(tx0 + 3, tx0 + 13, -half, half, zz, zz + 4, fr, "Aluminium")
            K.box(tx0 - 26, tx0 + 22, -5, 5, tz + 111, tz + 117, WHITE, "Plastic")
            K.box(tx0 + 4, tx0 + 12, -4, 4, tz + 117, tz + 123, (240, 240, 230, 255), "Glow", "LightBrick",
                  extra={"Brightness": 0.6, "InputChannel.InputAxis": "Headlight"})
        else:
            K.rod((tx0 + 8, 0, tz), (tx0 + 8, 0, tz + 70), 7, fr, "Aluminium")
            ly = tz + 70
            if self.eq >= 1:
                K.box(tx0 - 2, tx0 + 18, -10, 10, tz + 70, tz + 80, cabd, "Aluminium")
                ly = tz + 80
            if self.eq >= 1:
                K.box(tx0 - 26, tx0 + 22, -4, 4, tz + 80, tz + 86, WHITE, "Plastic")
                ly = tz + 86
            lx = tx0 + 2 if self.eq >= 1 else tx0 + 8          # light centred on the mast (top)
            K.box(lx - 4, lx + 4, -4, 4, ly, ly + 6, (240, 240, 230, 255), "Glow", "LightBrick",
                  extra={"Brightness": 0.6, "InputChannel.InputAxis": "Headlight"})
        if self.eq >= 1:
            for s in (1, -1):
                y0, y1 = sorted((s * 30, s * 52))
                K.box(tx0 + 24, tx0 + 52, y0, y1, tz, tz + 18, (58, 62, 52, 255), "Steel")
        if self.sty["gun_bow"]:
            # gun on the foredeck, in front of the wheelhouse (pedestal welded to the deck section)
            ln = self.ln
            xg = min(ln.X0 + 0.78 * ln.L, c["cx1"] + 115)
            zd = ln.sheer_z(xg + 31)
            K.weld = self.chunk_of[self.sec_of(xg + 31)]
            # tall enough that the barrel clears the bow rails / bulwarks in every direction
            top_obst = max(ln.sheer_z(x) for x in (xg, ln.X1 - 0.02 * ln.L)) + self.sty["rail_h"] + 14
            ped_h = max(58.0, top_obst - 37.0 - zd)
            ped = (xg, xg + 62, -22.0, 22.0, zd, zd + ped_h)
            K.box(*ped, STEEL, "Aluminium")
            if self.eq >= 1:
                K.box(xg - 8, xg + 70, -30, 30, zd, zd + 6, STEEL, "Steel")
            self.station(ped, K.weld, 115.0, 0.0)         # cannot swing into the wheelhouse
        else:
            ped = (tx1 - 72, tx1 - 10, -22.0, 22.0, tz, tz + 24.0)
            K.box(*ped, STEEL, "Aluminium")
            self.station(ped, tw, 150.0, -5.0)            # mast stays in the dead sector aft
        K.weld = self.cab_w

    def station(self, ped, base_weld, yaw, pitch_min):
        """Weapon station from the user's PU1, aimed and fired from the gunner seat."""
        K = self.K
        self.turret_ped, self.turret_ped_weld = ped, base_weld
        tz = ped[4]
        gunner = self.seats[1]
        tb = load_station()
        drop = {1, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16, 19}
        logic = {22, 23, 24}
        keep = [i for i in range(len(tb)) if i not in drop]
        base = len(K.v.bricks)
        remap = {old: base + n for n, old in enumerate(keep)}
        plate_bottom = tb[0].pos[2] - tb[0].get("BrickSize")[2] / 2
        ox, oz = ped[0] + 32 - 0.6, ped[5] - plate_bottom
        welds = {0: base_weld, 2: base_weld}      # fire-control logic welded to the pedestal
        for g in (1, 4):
            welds[g] = K.new_weld()
        self.turret = {"moving": (welds[1], welds[4]), "first": len(K.v.bricks), "base": base_weld}
        self.protect.update((welds[1], welds[4]))
        K.weld = self.cab_w
        for old in keep:
            b = copy.deepcopy(tb[old])
            if old in logic:
                b.pos = (ped[0] - 1.5, {22: -8.0, 23: 0.0, 24: 8.0}[old], ped[5] - 12)
            else:
                b.pos = (b.pos[0] + ox, b.pos[1], b.pos[2] + oz)
            for key in ("InputChannel.SourceBricks", "EnabledInputChannel.SourceBricks"):
                if key in b.props:
                    b.set(key, [src(remap[v - 1]) for v in b.get(key)])
            for key in ("BrickPattern", "PatternScale"):
                b.props.pop(key, None)
            if b.get("BrickMaterial") != "CloudyGlass":
                b.set("BrickColor", (60, 64, 68, 255) if b.type != "Gun_2A28" else (46, 48, 51, 255))
            if b.type == "Actuator_1sx1sx1s_Bottom":
                b.set("MinLimit", -yaw)
                b.set("MaxLimit", yaw)
                b.set("InputChannel.SourceBricks", [src(gunner)])
            if b.type == "Actuator_1x1x1_Bottom":
                b.set("MinLimit", pitch_min)
                b.set("MaxLimit", 45.0)
                b.set("InputChannel.SourceBricks", [src(gunner)])
            if b.type == "SwitchBrick" and b.get("InputChannel.InputAxis") == "Action1":
                b.set("InputChannel.SourceBricks", [src(gunner)])
            if b.type.startswith("Camera"):
                b.set("OwningSeat", src(gunner))
                b.set("CameraName", "Gun sight")
            if b.group in (1, 4) and not b.type.startswith("Actuator"):
                b.set("ConnectorSpacing", 0)
            b.group = welds[b.group]
            K.v.add(b)
            K.items.append((len(K.v.bricks) - 1, b.pos, "Steel", 2000.0, False))
        K.weld = self.cab_w

    def console(self):
        """Open motor boat: centre or side console with windscreen, wheel, throttle and screens;
        leaning post / helm seat behind it, bench seat aft, cushions on the foredeck."""
        K, ln, P = self.K, self.ln, self.P
        fz = self.floor_z
        sty = self.sty
        x0 = ln.X0 + sty["console_x"] * ln.L
        side = sty["console_side"]
        hw_c = ln.hull_hw(x0, fz + 30) - 0.30 * ln.hw - 6          # inner edge of the side lockers
        cw = 30.0 if not side else 26.0
        yc = 0.0 if not side else max(0.0, hw_c - cw - 2)
        w = K.new_weld()
        self.cab_w = w
        if self.eq >= 1 and sty["ttop"] and not side:
            # T-top canopy over the helm on four posts
            th = fz + 195
            for px in (x0 - 85, x0 + 45):
                for py in (-40, 40):
                    K.rod((px, py, fz + 1), (px, py, th), 4, CHROME)
            K.box(x0 - 100, x0 + 60, -55, 55, th, th + 4, P["roof"], "Plastic")
            K.box(x0 - 20, x0 - 10, -5, 5, th + 4, th + 10, (240, 240, 230, 255), "Glow", "LightBrick",
                  extra={"Brightness": 0.6, "InputChannel.InputAxis": "Headlight"})
        # console body (buoyant inside), sloped instrument face, windscreen
        K.box(x0, x0 + 55, yc - cw, yc + cw, fz, fz + 78, P["cabin"], "Float", "Float")
        K.ramp(x0, x0 + 18, yc - cw, yc + cw, fz + 78, fz + 92, back=(1, 0, 0), bottom=(0, 0, -1), color=P["cabin_d"],
               material="Plastic")
        K.box(x0 + 18, x0 + 55, yc - cw, yc + cw, fz + 78, fz + 92, P["cabin"], "Plastic")
        K.ramp(x0 + 22, x0 + 50, yc - cw - 2, yc + cw + 2, fz + 92, fz + 122, back=(-1, 0, 0), bottom=(0, 0, -1),
               color=GLASS, material="Glass")
        wy = yc
        K.rod((x0 + 6, wy, fz + 78), (x0 - 6, wy, fz + 84), 4, P["frame"], "Steel")
        K.obox((x0 - 8, wy, fz + 85), (0, 1, 0), unit((-1, 0, 0.6)), (34, 34, 3), (28, 28, 28, 255), "Rubber",
               "ScalableZylinder", vf=0.785)
        if self.eq >= 1:
            K.obox((x0 + 9, yc - 0.45 * cw, fz + 85.5), (0, -1, 0), unit((-1, 0, 1)), (0.7 * cw, 10, 1.0),
                   (8, 10, 12, 255), "Plastic", "TextBrick", extra={"Text": "GPS", "TextColor": (60, 200, 230, 255)})
            K.obox((x0 - 0.5, yc + 0.6 * cw, fz + 66), (0, 1, 0), (-1, 0, 0), (11, 11, 1.0), (24, 24, 24, 255),
                   "Plastic", "ImageCylinder", extra={"Image": "Gauge"})
            # throttle on the side of the console, grab rail around the top
            K.box(x0 + 10, x0 + 30, yc + cw, yc + cw + 6, fz + 62, fz + 74, (30, 30, 32, 255), "Plastic")
            K.rod((x0 + 20, yc + cw + 3, fz + 74), (x0 + 12, yc + cw + 3, fz + 88), 2.2, CHROME)
            for yy in (yc - cw - 4, yc + cw + 4):
                K.rod((x0 + 4, yy, fz + 60), (x0 + 4, yy, fz + 84), 2.5, CHROME)
            K.rod((x0 + 4, yc - cw - 4, fz + 84), (x0 + 4, yc + cw + 4, fz + 84), 2.5, CHROME, extend=2)
        # helm seat: leaning post with a backrest, or a pedestal chair
        sx = x0 - 55
        if self.eq >= 1 and not side:
            K.box(sx - 32, sx + 8, yc - 34, yc + 34, fz, fz + 14, P["cabin_d"], "Float", "Float")
            K.box(sx - 30, sx - 22, yc - 30, yc + 30, fz + 60, fz + 100, (40, 40, 42, 255), "Rubber")
            K.rod((sx - 26, yc - 26, fz + 14), (sx - 26, yc - 26, fz + 62), 3, CHROME)
            K.rod((sx - 26, yc + 26, fz + 14), (sx - 26, yc + 26, fz + 62), 3, CHROME)
            seat_z = fz + 14
        elif self.eq >= 1:
            K.rod((sx, yc, fz), (sx, yc, fz + 2), 34, P["frame"], "Steel")
            K.rod((sx, yc, fz + 2), (sx, yc, fz + 16), 9, CHROME)
            seat_z = fz + 16
        else:
            seat_z = fz
        self.seats = [K.fixed("Seat_2x2x7s", (sx, yc, seat_z - 1), color=(38, 38, 40, 255), material="Rubber")]
        if self.eq >= 1:
            self.seats.append(K.fixed("Seat_2x2x7s", (ln.X0 + 0.22 * ln.L, 0.0 if not side else -yc * 0.6, fz - 1),
                                      color=(38, 38, 40, 255), material="Rubber"))
        K.box(x0 + 30, x0 + 40, yc - 5, yc + 5, fz + 92, fz + 100, (240, 240, 230, 255), "Glow", "LightBrick",
              extra={"Brightness": 0.5, "InputChannel.InputAxis": "Headlight"})
        # cushions on the foredeck
        if self.eq >= 1 and sty["cushions"]:
            xf = self.x_fd + 8
            K.weld = self.chunk_of[self.sec_of(xf + 40)]
            zf = ln.sheer_z(xf + 80)
            hwf = min(ln.sheer_hw(xf + 80) - 22, 70)
            if hwf > 25:
                K.box(xf, xf + 80, -hwf, hwf, ln.sheer_z(xf), zf + 8, (46, 48, 52, 255), "Foam")
            K.weld = w

    # ------------------------------------------------------------------ factions (patrol boats only)
    EAGLE = [  # (u, v, length, height, angle) - flat steppe eagle facing the bow, ~60 x 44 cm
        (0, -2, 8, 22, 0), (0, 12, 7, 7, 0), (4.5, 11, 5, 3, -25), (0, -16, 11, 7, 0),
        (-10, 4, 19, 6, 22), (-22, 10, 17, 5, 34), (-11, -2, 17, 5, 6), (-23, 2, 14, 4, 14),
        (10, 4, 19, 6, -22), (22, 10, 17, 5, -34), (11, -2, 17, 5, -6), (23, 2, 14, 4, -14),
        (-3, -12, 3, 6, 0), (3, -12, 3, 6, 0)]

    def emblem(self, which, xc, yw, zc, s, sc):
        """Flat emblem on a vertical wall at y = yw (outward side s): 'III' bars or the eagle."""
        K = self.K
        if which == "south":
            for j in (-1, 0, 1):
                x = xc + j * 10 * sc
                y0, y1 = sorted((yw, yw + s * 0.8))
                K.box(x - 2.6 * sc, x + 2.6 * sc, y0, y1, zc - 16 * sc, zc + 16 * sc, (236, 236, 232, 255), "Plastic")
        else:
            gold = (214, 168, 44, 255)
            for u, v, ln_, h, a in self.EAGLE:
                ar = math.radians(a)
                X = (math.cos(ar), 0.0, math.sin(ar))
                K.obox((xc + u * sc, yw + s * 0.4, zc + v * sc), X, (0, s, 0), (ln_ * sc, h * sc, 0.8), gold,
                       "Plastic")

    def faction_marks(self):
        if not self.faction or not hasattr(self, "cab") or self.eq < 1:
            return
        K, ln, c = self.K, self.ln, self.cab
        K.weld = self.cab_w
        x0, x1 = c["dx1"] + 14, c["cx1"] - 14
        hwall = c["zs"] - c["D"]
        sc = max(0.5, min(1.0, (hwall - 12) / 44.0, (x1 - x0) / 66.0))
        xc, zc = (x0 + x1) / 2, c["D"] + hwall * 0.52
        for s in (1, -1):
            self.emblem(self.faction, xc, s * c["cy"], zc, s, sc)
        if self.faction != "south":
            return
        r = random.Random("worn-%d" % self.seed)
        # mismatched repair patches on the wheelhouse walls
        for s in (1, -1):
            for _ in range(r.choice((1, 2))):
                w, h = r.uniform(16, 30), r.uniform(12, 24)
                xp = r.choice((c["cx1"] - 8 - w / 2, x0 - 6 - w / 2)) if x0 - 6 - w > c["dx1"] else c["cx1"] - 8 - w / 2
                zp = r.uniform(c["D"] + 6 + h / 2, c["zs"] - 6 - h / 2)
                y0, y1 = sorted((s * c["cy"], s * (c["cy"] + 0.6)))
                col = r.choice(((96, 66, 44), (72, 76, 58), (92, 94, 96)))
                K.box(xp - w / 2, xp + w / 2, y0, y1, zp - h / 2, zp + h / 2, rgba(col), "Steel")
        # jerry cans on the aft deck, lashed to the transom
        K.weld = self.chunk_of[0]
        for j in range(r.choice((2, 3))):
            y = (j - 1) * 24 + r.uniform(-3, 3)
            zx = ln.sheer_z(ln.X0 + 8)
            K.box(ln.X0 + 3, ln.X0 + 14, y - 9, y + 9, zx, zx + 28, (66, 74, 48, 255), "Steel")
        # sandbags round the gun
        t = getattr(self, "turret_ped", None)
        if t:
            px0, px1, py0, py1, pz0, _ = t
            sand = (150, 134, 98, 255)
            K.weld = self.turret_ped_weld
            for (a0, a1, b0, b1) in ((px1 + 1, px1 + 17, -30, 30), (px0 - 6, px1 + 1, py1 + 1, py1 + 15),
                                     (px0 - 6, px1 + 1, py0 - 15, py0 - 1)):
                K.box(a0, a1, b0, b1, pz0, pz0 + 12, sand, "Rubber")

    # ------------------------------------------------------------------ deck gear
    def gear(self):
        K, ln, P = self.K, self.ln, self.P
        eq = self.eq
        open_boat = self.kind == "motor"
        rd = 2.5 if open_boat else 3.5
        # bow bulwarks (solid sides forward) or a bow pulpit
        if eq >= 1 and self.sty["bulwark"]:
            hb = self.sty["bulwark_h"]
            st = self.st
            xs_b = [x for x in st if ln.X0 + 0.60 * ln.L <= x < ln.X1 - 0.03 * ln.L] + [ln.X1 - 0.03 * ln.L]
            for a, b in zip(xs_b, xs_b[1:]):
                K.weld = self.chunk_of[self.sec_of(a + 1)]
                for s in (1, -1):
                    ya, yb = s * (ln.sheer_hw(a) - 1.5), s * (ln.sheer_hw(b) - 1.5)
                    za, zb = ln.sheer_z(a), ln.sheer_z(b)
                    K.plate((a, ya, za), (a, ya, za + hb), (b, yb, zb), (b, yb, zb + hb), (0, s, 0), 2.5,
                            P["hull"], self.hm, overlap=1.0)
                    if eq >= 2:
                        K.plate((a, ya, za + hb), (a, ya - s * 8, za + hb), (b, yb, zb + hb), (b, yb - s * 8, zb + hb),
                                (0, 0, 1), 2.0, P["frame"], self.hm, overlap=1.0)
        elif eq >= 1:
            K.weld = self.chunk_of[self.sec_of(ln.X1 - 0.05 * ln.L)]
            n = 3 + 2 * eq + self.sty["stanchions"]
            xs = [ln.X0 + ln.L * (0.70 + 0.27 * j / (n - 1)) for j in range(n)]
            h = self.sty["rail_h"] * (0.8 if open_boat else 1.0)
            for s in (1, -1):
                tops, mids = [], []
                for x in xs:
                    b = (x, s * (ln.sheer_hw(x) - 10), ln.sheer_z(x))
                    K.rod(b, add(b, (0, 0, h)), rd, CHROME)
                    tops.append(add(b, (0, 0, h)))
                    mids.append(add(b, (0, 0, h / 2)))
                tip = (ln.X1 - 0.02 * ln.L, 0, ln.sheer_z(ln.X1 - 0.02 * ln.L) + h)
                tops.append(tip)
                for a, b in zip(tops, tops[1:]):
                    K.rod(a, b, rd, CHROME, extend=2)
                if eq >= 2 or (eq >= 1 and self.sty["mid_rail"]):
                    for a, b in zip(mids, mids[1:]):
                        K.rod(a, b, rd * 0.7, CHROME, extend=1)
            K.rod((tip[0], 0, tip[2] - h), tip, rd, CHROME)
        # stern rails (decked boats)
        if not open_boat:
            K.weld = self.chunk_of[0]
            n = 3 + 2 * eq
            rh = self.sty["rail_h"] + 10
            xs = [ln.X0 + 12 + j * (0.33 * ln.L) / (n - 1) for j in range(n)]
            yr = ln.hw - 10
            for s in (1, -1):
                tops = []
                for x in xs:
                    K.box(x - 2, x + 2, s * yr - 2, s * yr + 2, ln.D, ln.D + rh, CHROME, "Chrome")
                    tops.append((x, s * yr, ln.D + rh))
                K.rod(tops[0], tops[-1], 3.5, CHROME, extend=2)
                if eq >= 1:
                    K.rod((xs[0], s * yr, ln.D + 35), (xs[-1], s * yr, ln.D + 35), 2.5, CHROME, extend=1)
                K.rod((xs[0], s * yr, ln.D + rh), (xs[0], s * 0.65 * ln.hw, ln.D + rh), 3.5, CHROME, extend=2)
                if self.kind == "military" and eq >= 1 and self.sty["antennas"] >= (1 if s > 0 else 2):
                    K.rod((xs[0], s * yr, ln.D + rh), (xs[0], s * yr, ln.D + rh + 190), 2.2, (30, 30, 32, 255), "Rubber")
                K.box(xs[0] - 2, xs[0] + 2, s * 0.65 * ln.hw - 2, s * 0.65 * ln.hw + 2, ln.D, ln.D + rh, CHROME,
                      "Chrome")
        # cleats
        for s in (1, -1):
            for x in ([ln.X0 + 0.05 * ln.L, ln.X0 + 0.85 * ln.L] + ([ln.X0 + 0.55 * ln.L] if eq >= 1 else [])):
                K.weld = self.chunk_of[self.sec_of(x)]
                y, z = s * (ln.sheer_hw(x) - 18), ln.sheer_z(x)
                K.box(x - 9, x + 9, y - 2.5, y + 2.5, z, z + 3, CHROME, "Chrome")
                K.box(x - 3, x + 3, y - 2.5, y + 2.5, z + 3, z + 6, CHROME, "Chrome")
        # windlass + anchor
        if eq >= 1 and not open_boat:
            xw = ln.X0 + (0.905 if self.sty["gun_bow"] else 0.86) * ln.L
            K.weld = self.chunk_of[self.sec_of(xw)]
            wz = ln.sheer_z(xw)
            K.box(xw - 15, xw + 15, -15, 15, wz, wz + 16, STEEL, "Steel")
            K.rod((xw + 15, 0, wz + 8), (xw + 22, 0, wz + 8), 16, STEEL, "Steel")
        if eq >= 2 and not open_boat:
            xa = ln.X1 - 0.015 * ln.L
            K.weld = self.chunk_of[self.sec_of(xa)]
            ra = (xa, 0, ln.sheer_z(xa) + 2)
            K.obox(add(ra, (12, 0, 3)), (1, 0, 0), (0, 0, 1), (40, 12, 5), STEEL, "Steel")
            K.box(ra[0] + 22, ra[0] + 26, -2, 2, ra[2] - 40, ra[2] + 4, STEEL, "Steel")
            K.obox((ra[0] + 24, 0, ra[2] - 44), (0, 1, 0), (1, 0, 0), (34, 8, 4), STEEL, "Steel")
        # life rafts (military/cutter) - welded with their cradles AND the deck chunk
        rafts = [ln.X0 + 0.25 * ln.L, ln.X0 + 0.25 * ln.L - 95][:self.sty["rafts"]]
        if eq >= 1 and not open_boat:
            for s, x in [(s, x) for s in (1, -1) for x in rafts]:
                K.weld = self.chunk_of[self.sec_of(x)]
                y = s * (ln.hw - 42)
                for dx in (-30, 30):
                    K.box(x + dx - 4, x + dx + 4, y - 22, y + 22, ln.D, ln.D + 8, STEEL, "Steel")
                K.rod((x - 42, y, ln.D + 29), (x + 42, y, ln.D + 29), 42, WHITE, "Plastic")
                if eq >= 2:
                    for dx in (-25, 25):
                        K.rod((x + dx - 1, y, ln.D + 29), (x + dx + 1, y, ln.D + 29), 44, (200, 90, 30), "Plastic")
        # aft benches / engine hatch
        if eq >= 2 and not open_boat and len(rafts) < 2 and self.sty["benches"]:
            K.weld = self.chunk_of[0]
            for s in (1, -1):
                y0, y1 = sorted((s * 25, s * (ln.hw - 50)))
                K.box(ln.X0 + 8, ln.X0 + 45, y0, y1, ln.D, ln.D + 38, P["cabin_d"], "Plastic")
                K.box(ln.X0 + 9, ln.X0 + 44, y0, y1, ln.D + 38, ln.D + 45, (40, 40, 42, 255), "Rubber")
            K.box(ln.X0 + 100, ln.X0 + 200, -55, 55, ln.D, ln.D + 4, P["frame"], "Aluminium")
        # portholes (cutter, below the deck forward) and hull numbers (patrol boats)
        if eq >= 1 and self.kind == "cutter":
            for j in range(self.sty["portholes"]):
                xp = ln.X0 + (0.62 + 0.07 * j) * ln.L
                K.weld = self.chunk_of[self.sec_of(xp)]
                zp = ln.sheer_z(xp) - 0.32 * ln.D
                for s in (1, -1):
                    yp = s * (ln.hull_hw(xp, zp) + 1.0)
                    K.obox((xp, yp, zp), (1, 0, 0), (0, s, 0), (16, 16, 1.5), CHROME, "Chrome", "ScalableZylinder",
                           vf=0.785)
                    K.obox((xp, yp + s * 0.8, zp), (1, 0, 0), (0, s, 0), (12, 12, 1.0), GLASS, "Glass",
                           "ScalableZylinder", vf=0.785)
        if eq >= 1 and self.kind == "military":
            xn = ln.X0 + 0.83 * ln.L
            K.weld = self.chunk_of[self.sec_of(xn)]
            zn = ln.chine_z(xn) + (ln.sheer_z(xn) - ln.chine_z(xn)) * 0.55
            for s in (1, -1):
                yn = s * (ln.hull_hw(xn, zn) + 3.0)
                K.obox((xn, yn, zn), (-1, 0, 0) if s > 0 else (1, 0, 0), (0, s, 0.05), (0.09 * ln.L, 30, 1),
                       P["hull"], "Plastic", "TextBrick", extra={"Text": self.sty["hull_no"], "Font": "Orbitron",
                                                                 "TextColor": P["text"]})
        # names on the hull
        if eq >= 1:
            for s in (1, -1):
                xs_ = ln.X0 + 0.23 * ln.L
                K.weld = self.chunk_of[self.sec_of(xs_)]
                zc_ = ln.chine_z(xs_) + (ln.sheer_z(xs_) - ln.chine_z(xs_)) * 0.8
                y_ = s * (ln.hull_hw(xs_, zc_) + 3.0)
                K.obox((xs_, y_, zc_), (-1, 0, 0) if s > 0 else (1, 0, 0), (0, s, 0.05), (0.10 * ln.L, 18, 1),
                       P["hull"], "Plastic", "TextBrick", extra={"Text": self.name.upper()[:12], "Font": "Orbitron",
                                                                 "TextColor": P["text"]})
        K.weld = self.chunk_of[0]
        K.box(ln.X0 - 4, ln.X0 - 3, -4, 4, ln.D - 12, ln.D - 6, (240, 240, 230, 255), "Glow", "LightBrick",
              extra={"Brightness": 0.4, "InputChannel.InputAxis": "Headlight"})
        if open_boat:
            # bow nav lights on the foredeck
            x = ln.X0 + 0.9 * ln.L
            K.weld = self.chunk_of[self.sec_of(x)]
            for s, col in ((1, (20, 200, 70, 255)), (-1, (210, 25, 25, 255))):
                y, z = s * (ln.sheer_hw(x) - 12), ln.sheer_z(x)
                K.box(x - 4, x + 4, y - 3, y + 3, z, z + 6, col, "Glow", "LightBrick",
                      extra={"Brightness": 0.5, "InputChannel.InputAxis": "Headlight"})

    # ------------------------------------------------------------------ main
    def build(self, name):
        self.name = name
        self.float_cells = []
        self.protect = set()
        self.plan_stabilisers()
        self.hull()
        self.lockers()
        self.stabilisers()
        self.cabin()
        self.gear()
        self.faction_marks()
        self.outboards()
        self.unweld_contacts()
        self.balance()
        self.tune()
        return self.K

    def unweld_contacts(self):
        """Do not weld what is already held: an axis-aligned box that sits face-to-face on another
        axis-aligned box connects through its connectors like any brick placed in the editor.
        Such bricks leave their weld group - unless a slanted brick of the same group leans on
        them (then they are what holds that slanted brick).  Every unwelded brick keeps a chain of
        face contacts back to a welded anchor, so nothing comes loose by itself."""
        K, v = self.K, self.K.v
        n = len(v.bricks)
        hidden = {it[0] for it in K.items if it[4]}
        first = self.turret["first"] if hasattr(self, "turret") else n
        BOX = {"ScalableBrick", "Float", "TankBrick", "LightBrick"}
        info = []
        for i, b in enumerate(v.bricks):
            R = rotm(b.rot)
            ax = all(abs(abs(c) - 1) < 1e-4 or abs(c) < 1e-4 for row in R for c in row)
            lo, hi = K.aabb(i)
            info.append((ax and b.type in BOX, lo, hi))
        cell = 60.0
        grid = {}
        for i, (ab, lo, hi) in enumerate(info):
            for gx in range(int(lo[0] // cell), int(hi[0] // cell) + 1):
                for gy in range(int(lo[1] // cell), int(hi[1] // cell) + 1):
                    for gz in range(int(lo[2] // cell), int(hi[2] // cell) + 1):
                        grid.setdefault((gx, gy, gz), []).append(i)

        def near(i):
            lo, hi = info[i][1], info[i][2]
            out = set()
            for gx in range(int((lo[0] - 1) // cell), int((hi[0] + 1) // cell) + 1):
                for gy in range(int((lo[1] - 1) // cell), int((hi[1] + 1) // cell) + 1):
                    for gz in range(int((lo[2] - 1) // cell), int((hi[2] + 1) // cell) + 1):
                        out.update(grid.get((gx, gy, gz), ()))
            out.discard(i)
            return out

        def face(a, b):
            (_, la, ha), (_, lb, hb) = info[a], info[b]
            for k in range(3):
                if abs(ha[k] - lb[k]) < 0.35 or abs(hb[k] - la[k]) < 0.35:
                    o = [min(ha[m], hb[m]) - max(la[m], lb[m]) for m in range(3) if m != k]
                    if min(o) >= 2.0:
                        return True
            return False

        def touch(a, b):
            (_, la, ha), (_, lb, hb) = info[a], info[b]
            return all(la[m] - 0.5 < hb[m] and lb[m] - 0.5 < ha[m] for m in range(3))

        cand = set()
        for i, b in enumerate(v.bricks):
            if (info[i][0] and b.group and b.group not in self.protect and i not in hidden and i < first):
                if not any(v.bricks[j].group == b.group and not info[j][0] and touch(i, j) for j in near(i)):
                    cand.add(i)
        attached = {i for i in range(n) if info[i][0] and i not in cand and v.bricks[i].group}
        changed = True
        while changed:
            changed = False
            for i in sorted(cand):
                if any(j in attached and face(i, j) for j in near(i)):
                    v.bricks[i].group = 0
                    attached.add(i)
                    cand.discard(i)
                    changed = True
        self.unwelded = sum(1 for b in v.bricks if b.group == 0)

    def tune(self):
        """Engine and stabiliser strength from the boat's mass and size.

        Calibrated on the user's own tuning in the game:
          * TUMAN-3 (cutter 8 m, ~4.6 t in this mass model): roll thrusters 1, bow pitch thrusters
            up 7 / down 1 (pitch sensor not inverted), outboards 5 (reverse -3.3) + two fixed
            hull thrusters 15 -> 40 forward in total;
          * SEVER-4 (patrol boat 10.5 m, ~12 t): roll 6, pitch 6.
        Roll: the needed torque grows with mass x beam^2, the user's two boats fit mass^1.7 x beam.
        Pitch: nearly the same on both boats, lifting the bow strong, pushing it down weak.
        Engines: total thrust ~ mass^0.75 (smaller boats get more power per tonne, like real ones),
        a quarter on the steerable outboards, the rest on the fixed hull jets."""
        m = self.K.mass()[0]
        roll = min(8.0, max(0.3, 6.0 * (m / 12000.0) ** 1.7 * (self.B / 330.0)))
        p_up = min(10.0, max(3.0, 7.0 * (m / 4600.0) ** (-0.16 if m > 4600 else 0.3)))   # small boats: gentler
        p_dn = p_up / 7.0
        for idx, which, k in getattr(self, "stab_thr", []):
            if which == "roll":
                v = k * roll
            else:
                v = -p_up if k < 0 else p_dn
            self.K.v.bricks[idx].set("InputScale", round(v, 2))
        total = 40.0 * (m / 4600.0) ** 0.75
        out = max(1.5, 0.25 * total / self.n_out)
        jet = max(2.0, 0.375 * total)
        for idx, kind in self.main_thr:
            v = {"out": out, "rev": -0.66 * out, "jet": jet}[kind]
            self.K.v.bricks[idx].set("InputScale", round(v, 1))
        self.thrust = (round(out, 1), round(-0.66 * out, 1), round(jet, 1))
        self.stab_k = (round(roll, 2), round(p_up, 2))

# ----------------------------------------------------------------------------- variation
STRIPES = [None, None, (170, 40, 36), (222, 120, 30), (40, 92, 172), (214, 180, 40), (226, 228, 230), (30, 120, 90)]


def make_style(kind, size, color, seed):
    """Look and layout choices: every seed gives a visibly different boat."""
    r = random.Random("style-%d" % seed)
    if kind == "motor":
        outb = 1 if size != "L" else r.choice((1, 2))
    elif kind == "cutter":
        outb = r.choice((1, 2, 2))
    else:
        outb = r.choice((2, 2, 3)) if size != "S" else 2
    sty = {
        "cab_shift": r.uniform(-0.045, 0.045), "cab_len": r.uniform(0.85, 1.15), "cab_w": r.uniform(0.58, 0.70),
        "zs": r.uniform(60, 80), "zr": r.uniform(124, 145), "rake": r.uniform(30, 65),
        "win_w": r.choice((60, 75, 90, 120, 200)), "dome": r.random() < 0.65, "horns": r.random() < 0.6,
        "antennas": r.choice((0, 1, 2, 2, 3)), "mast_aft": r.random() < 0.5, "mast_h": r.uniform(60, 110),
        "yard": r.random() < 0.5, "rafts": r.choice((0, 1, 1, 2)), "benches": r.random() < 0.6,
        "rail_h": r.uniform(48, 78), "mid_rail": r.random() < 0.6, "stanchions": r.choice((0, 1, 2)),
        "stripe": r.choice(STRIPES), "bottom_red": r.random() < 0.35, "cab_tint": r.uniform(-20, 20),
        "two_tone": r.random() < 0.35, "tower_h": r.uniform(40, 62), "console_x": r.uniform(0.39, 0.47),
        "ttop": r.random() < 0.55 and size != "S", "outboards": outb,
        "gun_bow": kind == "military" and size != "S" and r.random() < 0.45, "console_side": kind == "motor" and r.random() < 0.4,
        "portholes": r.choice((0, 2, 3)), "hull_no": "%s-%d" % (r.choice("PKB"), r.randint(101, 989)),
        "pedestal": r.random() < 0.6, "screens": r.choice((1, 2, 3)), "cushions": r.random() < 0.6,
        "hull_tint": r.uniform(-24, 24), "bulwark": kind != "motor" and r.random() < 0.45,
        "bulwark_h": r.uniform(30, 48), "lattice": r.random() < 0.5,
        "flybridge": kind == "cutter" and size != "S" and r.random() < 0.4,
    }
    if size == "S":                       # small hulls: keep the cabin low so they stay stiff
        sty["zr"] = min(sty["zr"], 128.0)
        sty["cab_w"] = min(sty["cab_w"], 0.64)
        sty["tower_h"] = min(sty["tower_h"], 48.0)
        sty["zs"] = min(sty["zs"], 70.0)
    return sty


# ----------------------------------------------------------------------------- station source
_STATION = None


def load_station():
    global _STATION
    if _STATION is None:
        v = Vehicle.load(os.path.join(DATA, "pu1_station.brv"))
        T = rot_matrix((-2.0, 0.0, 0.0))
        out = []
        for b in v.bricks:
            if b.type in ("Seat_3x2x2", "RCBrick"):
                out.append(None)
                continue
            b = copy.deepcopy(b)
            b.pos = apply(T, b.pos)
            R = tuple(apply(T, col) for col in rot_matrix(b.rot))
            b.rot = mat_to_rot(*R)
            out.append(b)
        # PU1 indices without seat/RC (they are 2, 3, 4); references re-pointed to the trimmed list
        trim = {}
        for i, b in enumerate(out):
            if b is not None:
                trim[i] = len(trim)
        for b in out:
            if b is None:
                continue
            for key in ("InputChannel.SourceBricks", "EnabledInputChannel.SourceBricks"):
                if key in b.props:
                    b.set(key, [trim[v - 1] + 1 for v in b.get(key) if (v - 1) in trim])
        _STATION = [b for b in out if b is not None]
    return [copy.deepcopy(b) for b in _STATION]


def rot_matrix(rot):
    from .kit import rotm
    return rotm(rot)


def apply(R, v):
    X, Y, Z = R
    return tuple(X[i] * v[0] + Y[i] * v[1] + Z[i] * v[2] for i in range(3))


# ----------------------------------------------------------------------------- analysis
def analyse(b):
    K = b.K
    m, com = K.mass()
    lo, hi = 0.0, 400.0
    for _ in range(50):
        mz = (lo + hi) / 2
        if K.buoyancy(mz)[0] < m:
            lo = mz
        else:
            hi = mz
    vol, cbx, cbz = K.buoyancy(lo)
    total = K.buoyancy(1e9)[0]
    I = 0.0
    for c, s in K.floats():
        if c[2] - s[2] / 2 < lo <= c[2] + s[2] / 2:
            I += s[0] * s[1] ** 3 / 12 + s[0] * s[1] * c[1] ** 2
    gm = cbz + (I / (vol * 1000) if vol else 0) - com[2]
    IL = 0.0
    for c, s in K.floats():
        if c[2] - s[2] / 2 < lo <= c[2] + s[2] / 2:
            IL += s[1] * s[0] ** 3 / 12 + s[0] * s[1] * (c[0] - cbx) ** 2
    bml = IL / (vol * 1000) if vol else 1e9
    pitch = math.degrees(math.atan2(com[0] - cbx, bml))
    welds = {}
    for br in K.v.bricks:
        welds[br.group] = welds.get(br.group, 0) + 1
    return dict(mass=m, com=com, draft=lo, trim=com[0] - cbx, pitch=pitch, reserve=total / m if m else 0, gm=gm,
                floats_l=total, weld_groups=len([k for k in welds if k]), unwelded=welds.get(0, 0))


def balance(b):
    """Shift trim by moving fuel: add a ballast tank in the stern or bow float cells."""
    return


class Result:
    def __init__(self, builder, info, name):
        self.builder, self.kit, self.info, self.name = builder, builder.K, info, name


def make_name(kind, seed):
    pre = {"motor": ["SKIF", "VOLNA", "ORLAN", "PRIBOI", "BRIZ"], "cutter": ["ALBATROS", "KASATKA", "NERPA", "TUMAN"],
           "military": ["SEVER", "RUBEZH", "GROM", "STRIZH", "KORSAR"]}[kind]
    r = random.Random(seed)
    return "%s-%d" % (r.choice(pre), r.randint(2, 99))


def generate(kind="military", size="M", detail="med", color="dark", seed=1, name=None, faction=None):
    lo_t, hi_t = DETAIL[detail]
    target = (lo_t + hi_t) / 2
    name = name or make_name(kind, seed)
    best = None
    lo, hi = 0, len(RES) - 1
    tried = {}

    def run(r):
        if r not in tried:
            bld = Builder(kind, size, detail, color, seed, r, faction)
            bld.build(name)
            tried[r] = bld
        return tried[r]

    while lo <= hi:                       # binary search on the resolution
        midr = (lo + hi) // 2
        n = len(run(midr).K.v.bricks)
        if n < lo_t:
            lo = midr + 1
        elif n > hi_t:
            hi = midr - 1
        else:
            best = run(midr)
            break
    if best is None:
        best = min(tried.values(), key=lambda b: abs(len(b.K.v.bricks) - target))
    info = analyse(best)
    info.update(bricks=len(best.K.v.bricks), length_m=round(best.L / 100, 2), beam_m=round(best.B / 100, 2),
                kind=kind, size=size, detail=detail, color=color, seed=seed, name=name,
                thrust=getattr(best, "thrust", None), in_range=lo_t <= len(best.K.v.bricks) <= hi_t)
    return Result(best, info, name)


def write_vehicle(result, folder, preview_png=None):
    os.makedirs(folder, exist_ok=True)
    data = result.kit.v.dumps(canonical=True)
    assert Vehicle.loads(data).dumps(canonical=True) == data
    with open(os.path.join(folder, "Vehicle.brv"), "wb") as f:
        f.write(data)
    m = Meta.load(os.path.join(DATA, "meta_template.brm"))
    m.name = result.name
    m.description = "Generated by BoatGen: %s, %s, %s detail." % (result.info["kind"], result.info["size"],
                                                                  result.info["detail"])
    m.brick_count = len(result.kit.v.bricks)
    xs = [b.pos for b in result.kit.v.bricks]
    m.size = tuple(float(max(p[i] for p in xs) - min(p[i] for p in xs) + 30) for i in range(3))
    m.weight = float(round(result.info["mass"] * 0.06, 1))
    m.price = 0.0
    idb = bytearray(m.id_section)
    r = random.Random(result.info["seed"] * 1009 + len(xs))
    for i in range(6, min(11, len(idb))):
        idb[i] = r.randrange(256)
    m.id_section = bytes(idb)
    now = Meta.datetime_to_ticks(datetime.now(timezone.utc).replace(tzinfo=None))
    m.created_ticks = m.modified_ticks = now
    m.save(os.path.join(folder, "MetaData.brm"))
    if preview_png:
        with open(os.path.join(folder, "Preview.png"), "wb") as f:
            f.write(preview_png)
    return folder
