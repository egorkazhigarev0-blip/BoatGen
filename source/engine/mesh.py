"""Compact scene description for the 3D preview (built into triangles by the WebGL viewer).

Each primitive: [shape, cx, cy, cz, Xx, Xy, Xz, Yx, Yy, Yz, Zx, Zy, Zz, sx, sy, sz, r, g, b, a, mat]
in game coordinates (cm, X forward, Y starboard, Z up).
shape: 0 box, 1 ramp (full faces -X/-Z), 2 rounded ramp, 3 cylinder (axis Z), 4 cone (base -Z),
       5 hemisphere (base -Z), 6 seat (base pivot), 7 gun barrel (axis X)
mat:   0 paint, 1 metal, 2 glass, 3 glow, 4 rubber
"""
from .kit import rotm, add, mul, FIXED_SIZE, BASE_PIVOT

SHAPE = {"ScalableBrick": 0, "Float": 0, "TankBrick": 0, "LightBrick": 0, "TextBrick": 0, "ThrusterBrick": 0,
         "ScalableRamp": 1, "ScalableRampRounded": 2, "ScalableZylinder": 3, "ImageCylinder": 3,
         "ScalableConeFlat": 4, "LightConeFlat": 4, "ScalableHemisphere": 5}
MAT = {"Aluminium": 1, "Steel": 1, "Chrome": 1, "Copper": 1, "Glass": 2, "CloudyGlass": 2, "Glow": 3,
       "Rubber": 4, "Foam": 4}
SKIP = {"SensorBrick", "SwitchBrick", "MathBrick", "RCBrick"}
DEFAULT_COL = {"ThrusterBrick": (44, 44, 46, 255), "Gun_2A28": (46, 48, 51, 255),
               "Camera_sosna-u": (60, 64, 68, 255)}


def _r(v):
    return round(v, 2)


def scene(result):
    K = result.kit
    hidden = {it[0] for it in K.items if it[4]}
    prims = []
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for i, b in enumerate(K.v.bricks):
        if i in hidden or b.type in SKIP:
            continue
        X, Y, Z = rotm(b.rot)
        size = b.get("BrickSize")
        c = b.pos
        if b.type in SHAPE:
            shape = SHAPE[b.type]
        elif b.type.startswith("Seat"):
            shape, size = 6, FIXED_SIZE.get(b.type, (60, 60, 70))
        elif b.type.startswith("Gun"):
            shape, size = 7, FIXED_SIZE[b.type]
        else:
            shape, size = 0, FIXED_SIZE.get(b.type, (10, 10, 10))
        if size is None:
            continue
        if b.type in BASE_PIVOT and shape != 6:
            c = add(c, mul(Z, size[2] / 2))
        col = b.get("BrickColor") or DEFAULT_COL.get(b.type, (150, 150, 150, 255))
        mat = b.get("BrickMaterial")
        m = MAT.get(mat, 0)
        if b.type in ("LightBrick", "LightConeFlat"):
            m = 3
        if b.type.startswith("Gun") or b.type.startswith("Actuator"):
            m = 1
        a = col[3] if len(col) > 3 else 255
        if m == 2:
            a = min(a, 150)
        prims.append([shape, _r(c[0]), _r(c[1]), _r(c[2])] + [round(v, 4) for v in X + Y + Z] +
                     [_r(size[0]), _r(size[1]), _r(size[2]), col[0], col[1], col[2], a, m])
        for k in range(3):
            h = sum(abs((X, Y, Z)[j][k]) * size[j] / 2 for j in range(3))
            lo[k] = min(lo[k], c[k] - h)
            hi[k] = max(hi[k], c[k] + h)
    return {"prims": prims, "lo": lo, "hi": hi}
