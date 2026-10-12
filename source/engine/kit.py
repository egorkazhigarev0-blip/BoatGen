"""Construction kit for Brick Rigs vehicles (.brv): oriented bricks, weld groups, connectors.

Conventions: X forward, Y starboard, Z up, centimetres, Unreal FRotator (pitch, yaw, roll).
Weld groups: bricks with the same non-zero `group` are welded by the game ("пайка").
ConnectorSpacing: 12-bit mask, 2 bits per face; 0 = the brick never snaps to neighbours
(used for moving parts so they do not stick to the hull), 4095 = connectors on every face.
"""
import itertools
import math

from .brv import Vehicle, Brick


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)
def mid(*ps): return tuple(sum(p[i] for p in ps) / len(ps) for i in range(3))


def rotm(rot):
    p, y, r = (math.radians(a) for a in rot)
    cp, sp, cy, sy, cr, sr = math.cos(p), math.sin(p), math.cos(y), math.sin(y), math.cos(r), math.sin(r)
    X = (cp * cy, cp * sy, sp)
    Y = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    Z = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return X, Y, Z


def mat_to_rot(X, Y, Z):
    sp = max(-1.0, min(1.0, X[2]))
    p = math.degrees(math.asin(sp))
    if abs(abs(sp) - 1) > 1e-9:
        y = math.degrees(math.atan2(X[1], X[0]))
        r = math.degrees(math.atan2(-Y[2], Z[2]))
    else:
        r = 0.0
        y = math.degrees(math.atan2(-Y[0], Y[1]))
    rot = (p, y, r)
    R = rotm(rot)
    err = max(abs(R[i][k] - (X, Y, Z)[i][k]) for i in range(3) for k in range(3))
    if err > 1e-5:
        raise ValueError("bad rotation frame")
    return rot


def frame(X, Zhint):
    X = unit(X)
    Z = unit(sub(Zhint, mul(X, dot(Zhint, X))))
    return X, cross(Z, X), Z


# rough sizes of bricks with a built-in size (for previews and checks)
FIXED_SIZE = {"Seat_2x2x7s": (60, 60, 70), "Actuator_1sx1sx1s_Bottom": (10, 10, 5),
              "Actuator_1sx1sx1s_Top": (10, 10, 5), "Actuator_1x1x1_Bottom": (20, 20, 20),
              "Actuator_1x1x1_Top": (20, 20, 20), "Gun_2A28": (60, 18, 16), "Camera_sosna-u": (22, 18, 18)}
BASE_PIVOT = {"Seat_2x2x7s", "Actuator_1sx1sx1s_Bottom", "Actuator_1sx1sx1s_Top"}
DENSITY = {"Plastic": 1.0, "Aluminium": 2.7, "Rubber": 1.1, "Steel": 7.8, "Chrome": 7.2, "Glass": 2.5,
           "Copper": 8.9, "Glow": 1.0, "Float": 0.05, "Fuel": 0.85, "Foam": 0.1, "Fixed": 1.5}


class Kit:
    def __init__(self):
        self.v = Vehicle()
        self.weld = 0
        self.items = []          # (index, centre, density key, volume, hidden)
        self.hidden = False
        self.next_weld = 0

    def new_weld(self):
        self.next_weld += 1
        self.weld = self.next_weld
        return self.weld

    # ------------------------------------------------------------------ core
    def brick(self, typ, centre, X, Y, Z, size, color=None, material=None, extra=None, vf=1.0,
              connectors=None):
        b = Brick(typ, centre, mat_to_rot(X, Y, Z))
        if color is not None:
            col = tuple(int(c) for c in color)
            b.set("BrickColor", col + (255,) * (4 - len(col)))      # always RGBA
        if size is not None:
            b.set("BrickSize", tuple(float(s) for s in size))
        if material and material not in ("Plastic", "Float", "Fuel", "Fixed"):
            b.set("BrickMaterial", material)
        if connectors is not None:
            b.set("ConnectorSpacing", int(connectors))
        for k, val in (extra or {}).items():
            b.set(k, val)
        b.group = self.weld
        idx = self.v.add(b)
        dens = material or "Plastic"
        vol = size[0] * size[1] * size[2] * vf if size else 0.0
        if typ.startswith("Seat"):
            dens, vol = "Fixed", 20000.0
        self.items.append((idx, centre, dens, vol, self.hidden))
        return idx

    def box(self, x0, x1, y0, y1, z0, z1, color, material="Plastic", typ="ScalableBrick", extra=None,
            connectors=None):
        c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        return self.brick(typ, c, (1, 0, 0), (0, 1, 0), (0, 0, 1),
                          (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), color, material, extra,
                          connectors=connectors)

    def obox(self, centre, X, Zhint, size, color, material="Plastic", typ="ScalableBrick", extra=None,
             vf=1.0, connectors=None):
        X, Y, Z = frame(X, Zhint)
        return self.brick(typ, centre, X, Y, Z, size, color, material, extra, vf, connectors)

    def plate(self, p0, p1, q0, q1, outward, thick, color, material="Plastic", overlap=3.0, typ="ScalableBrick"):
        """Thin plate over the quad p0-p1 / q0-q1 (p -> q is the length direction)."""
        a, b = mid(p0, p1), mid(q0, q1)
        X = unit(sub(b, a))
        across = unit(add(sub(p1, p0), sub(q1, q0)))
        n = unit(cross(X, across))
        if dot(n, outward) < 0:
            n = mul(n, -1)
        X, Y, Z = frame(X, n)
        length = abs(dot(sub(b, a), X)) + overlap
        width = (norm(sub(p1, p0)) + norm(sub(q1, q0))) / 2 + overlap
        c = sub(mid(p0, p1, q0, q1), mul(Z, thick / 2))
        return self.brick(typ, c, X, Y, Z, (length, width, thick), color, material)

    def rod(self, p0, p1, dia, color, material="Chrome", typ="ScalableZylinder", extend=0.0, connectors=None):
        d = sub(p1, p0)
        Z = unit(d)
        hint = (0, 0, 1) if abs(Z[2]) < 0.9 else (1, 0, 0)
        X = unit(cross(hint, Z))
        return self.brick(typ, mid(p0, p1), X, cross(Z, X), Z, (dia, dia, norm(d) + extend), color, material,
                          vf=0.785, connectors=connectors)

    def ramp(self, x0, x1, y0, y1, z0, z1, back, bottom, color, material="Plastic", typ="ScalableRamp",
             connectors=None):
        """Axis aligned ramp: its full faces point to the world directions `back` and `bottom`."""
        X = tuple(-a for a in back)
        Z = tuple(-a for a in bottom)
        Y = cross(Z, X)
        ext = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
        size = tuple(ext[max(range(3), key=lambda i: abs(ax[i]))] for ax in (X, Y, Z))
        c = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        return self.brick(typ, c, X, Y, Z, size, color, material, vf=0.5, connectors=connectors)

    def fixed(self, typ, pos, X=(1, 0, 0), Zh=(0, 0, 1), color=None, material=None, extra=None,
              connectors=None):
        X, Y, Z = frame(X, Zh)
        return self.brick(typ, pos, X, Y, Z, None, color, material, extra, connectors=connectors)

    # ------------------------------------------------------------------ geometry helpers
    def aabb(self, idx):
        b = self.v.bricks[idx]
        s = b.get("BrickSize")
        R = rotm(b.rot)
        if s is None:
            s = FIXED_SIZE.get(b.type, (10, 10, 10))
            c = add(b.pos, mul(R[2], s[2] / 2)) if b.type in BASE_PIVOT else b.pos
        else:
            c = b.pos
        h = [sum(abs(R[k][i]) * s[k] / 2 for k in range(3)) for i in range(3)]
        return tuple(c[i] - h[i] for i in range(3)), tuple(c[i] + h[i] for i in range(3))

    # ------------------------------------------------------------------ estimates
    def mass(self):
        m = mx = my = mz = 0.0
        for idx, c, dens, vol, hid in self.items:
            w = vol * DENSITY.get(dens, 1.0) / 1000.0
            m += w
            mx += w * c[0]
            my += w * c[1]
            mz += w * c[2]
        return m, (mx / m, my / m, mz / m)

    def floats(self):
        out = []
        for idx, c, dens, vol, hid in self.items:
            b = self.v.bricks[idx]
            if b.type == "Float":
                out.append((c, b.get("BrickSize")))
        return out

    def buoyancy(self, draft):
        v = vx = vz = 0.0
        for c, s in self.floats():
            z0 = c[2] - s[2] / 2
            if z0 >= draft:
                continue
            h = min(c[2] + s[2] / 2, draft) - z0
            vol = s[0] * s[1] * h / 1000.0
            v += vol
            vx += vol * c[0]
            vz += vol * (z0 + h / 2)
        return v, (vx / v if v else 0.0), (vz / v if v else 0.0)
