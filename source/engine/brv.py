#!/usr/bin/env python3
"""
brv.py - reader / writer for Brick Rigs vehicle files (Vehicle.brv, format version 18).

The format was reverse-engineered from one sample (a pickup with a drone, 1135 bricks);
it has been verified by a byte-exact read -> write round trip, NOT by loading generated
files in the game.  Anything marked "unverified" below is a guess.

FILE LAYOUT (all integers little endian)
----------------------------------------
header
    u8   version                      (18)
    u16  brick_count
    u16  type_count                   number of distinct brick types used
    u16  property_count               number of property tables that follow
type table
    type_count x pstring              brick type names ("ScalableBrick", "Seat_2x2x7s", ...)
property tables, property_count times (one per property that at least one brick uses)
    pstring name                      e.g. "BrickColor"
    u16     value_count               number of DISTINCT values of this property
    u32     data_length               total bytes of all values
    bytes   data                      values stored back to back
    if value_count > 1:
        u16 value_size                > 0: every value has this size
                                      == 0: followed by value_count x u16 sizes
    (value_count == 1: no size field, the single value is data_length long)
brick records, brick_count times
    u16  type_index                   index into the type table
    u32  payload_length
    payload:
        u8   n_props
        n_props x (u16 property_index, u16 value_index)   only non-default properties
        3 x f32  position             X forward, Y right, Z up, centimetres
        3 x f32  rotation             degrees (pitch/yaw/roll order is unverified)
        u16  aux                      always 0 in the sample (unverified meaning)
        u16  group                    0 = none; 1..94 in the sample. Meaning unverified
                                      (looks like a group / sub-assembly id)

pstring = u8 length + UTF-8 bytes.   "Text" values use a u16 length instead.
Bricks refer to other bricks (wiring: input channel sources) by their 1-BASED index in the
brick record list, stored as u16 (verified on the pickup: every source points at a switch or
sensor only when read 1-based).  The record tail is (u16 editor group, u16 weld group);
bricks sharing a non-zero weld group are welded together by the game.

USAGE
-----
    python brv.py info Vehicle.brv
    python brv.py roundtrip Vehicle.brv        # checks the byte-exact round trip
    python brv.py dump Vehicle.brv out.json    # human readable dump

    from brv import Vehicle, Brick
    v = Vehicle.load("Vehicle.brv")
    v.bricks[0].set("BrickColor", (255, 0, 0, 255))
    v.save("Vehicle_new.brv")
"""
import json
import struct
import sys
from collections import Counter, OrderedDict

VERSION = 18

# The game's internal property order.  Inside one brick record the properties are listed in
# this order, and it also breaks ties when the property tables are ordered (see dumps()).
# Derived from two sample vehicles (1135 + 32 bricks), no brick contradicts it.  Pairs of
# properties that never occur together in the samples are ordered arbitrarily.
ENTRY_ORDER = [
    "BrickColor", "BrickMaterial", "SteeringAngle", "SteeringSpeed", "SuspensionLength",
    "SuspensionStiffness", "SuspensionDamping", "bInvertDrive", "ActuatorMode",
    "BrickPattern", "PatternOffset", "PatternScale", "PatternRotation", "SpinnerShape",
    "bGenerateLift", "BrickSize", "SpinnerRadius", "SpinnerSize", "SpinnerAngle",
    "ConnectorSpacing", "Text", "Font", "Image", "SpawnScale", "SizeScale", "SmokeColor",
    "bDriven", "bHasBrake", "bHasHandBrake", "FontSize", "TextColor", "WheelDiameter",
    "WheelWidth", "TireThickness", "TirePressureRatio", "OutlineThickness", "ImageColor",
    "OutputChannel.MinIn", "OutputChannel.MaxIn", "OutputChannel.MinOut",
    "OutputChannel.MaxOut", "InputChannel.InputAxis", "Brightness",
    "InputChannel.SourceBricks", "SpeedFactor", "MinLimit", "MaxLimit", "FlashSequence",
    "LightDirection", "MinAngle", "MaxAngle", "LightConeAngle", "InputScale", "FuelType",
    "EnabledInputChannel.InputAxis", "EnabledInputChannel.SourceBricks", "SensorType",
    "bReturnToZero", "TraceMask",
]

# ---------------------------------------------------------------------------- value codecs
def _pstr_dec(v):
    return v[1:1 + v[0]].decode("utf-8")


def _pstr_enc(s):
    b = s.encode("utf-8")
    if len(b) > 255:
        raise ValueError("string too long for a pstring")
    return bytes([len(b)]) + b


def _text_dec(v):
    n = struct.unpack_from("<H", v)[0]
    return v[2:2 + n].decode("utf-8")


def _text_enc(s):
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def _struct_codec(fmt):
    n = struct.calcsize(fmt)
    count = len(struct.unpack(fmt, bytes(n)))

    def dec(v):
        r = struct.unpack(fmt, v)
        return r[0] if count == 1 else r

    def enc(x):
        return struct.pack(fmt, *((x,) if count == 1 else x))
    return dec, enc


def _bricklist_dec(v):
    n = struct.unpack_from("<H", v)[0]
    return list(struct.unpack_from("<%dH" % n, v, 2))


def _bricklist_enc(lst):
    return struct.pack("<H%dH" % len(lst), len(lst), *lst)


CODECS = {}
for _n in ("BrickColor", "TextColor", "SmokeColor", "ImageColor"):
    CODECS[_n] = (lambda v: tuple(v), lambda x: bytes(x))
for _n in ("BrickMaterial", "SpinnerShape", "ActuatorMode", "InputChannel.InputAxis",
           "EnabledInputChannel.InputAxis", "Font", "Image", "BrickPattern", "SensorType",
           "FuelType", "TraceMask", "FlashSequence", "LightDirection"):
    CODECS[_n] = (_pstr_dec, _pstr_enc)
CODECS["Text"] = (_text_dec, _text_enc)
for _n in ("SwitchName", "SeatName", "CameraName"):
    CODECS[_n] = (_text_dec, _text_enc)              # u16 length + UTF-8
for _n in ("Operation", "AmmoType", "InputChannelA.InputAxis", "InputChannelB.InputAxis"):
    CODECS[_n] = (_pstr_dec, _pstr_enc)
for _n in ("InputChannelA.Value", "InputChannelB.Value"):
    CODECS[_n] = _struct_codec("<f")
for _n in ("InputChannelA.SourceBricks", "InputChannelB.SourceBricks"):
    CODECS[_n] = (_bricklist_dec, _bricklist_enc)
CODECS["OwningSeat"] = _struct_codec("<H")           # 1-based index of the seat
for _n in ("SteeringAngle", "SteeringSpeed", "SuspensionLength", "SuspensionStiffness",
           "SuspensionDamping", "SpinnerAngle", "Brightness", "SpeedFactor", "MinLimit",
           "MaxLimit", "SpawnScale", "SizeScale", "PatternRotation", "FontSize", "MinAngle",
           "MaxAngle", "WheelDiameter", "WheelWidth", "TireThickness", "TirePressureRatio",
           "OutlineThickness", "LightConeAngle", "OutputChannel.MinOut",
           "OutputChannel.MaxOut", "InputScale", "OutputChannel.MinIn",
           "OutputChannel.MaxIn"):
    CODECS[_n] = _struct_codec("<f")
for _n in ("SpinnerRadius", "SpinnerSize", "PatternScale", "PatternOffset"):
    CODECS[_n] = _struct_codec("<2f")
CODECS["BrickSize"] = _struct_codec("<3f")
CODECS["ConnectorSpacing"] = _struct_codec("<H")
for _n in ("bInvertDrive", "bHasHandBrake", "bGenerateLift", "bReturnToZero", "bDriven",
           "bHasBrake"):
    CODECS[_n] = (lambda v: v[0] != 0, lambda x: bytes([1 if x else 0]))
for _n in ("InputChannel.SourceBricks", "EnabledInputChannel.SourceBricks"):
    CODECS[_n] = (_bricklist_dec, _bricklist_enc)


def encode_value(name, value):
    """Python value -> raw bytes. Raw bytes are passed through unchanged."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return CODECS[name][1](value)


def decode_value(name, raw):
    """Raw bytes -> Python value (raw bytes if the property has no known codec)."""
    return CODECS[name][0](raw) if name in CODECS else raw


# ---------------------------------------------------------------------------- data model
class Brick:
    """One brick. `props` maps property name -> raw bytes (only non-default properties)."""

    def __init__(self, type, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), props=None,
                 group=0, aux=0):
        self.type = type
        self.pos = tuple(float(x) for x in pos)
        self.rot = tuple(float(x) for x in rot)
        self.props = OrderedDict()
        self.group = group
        self.aux = aux
        for k, v in (props or {}).items():
            self.set(k, v)

    def set(self, name, value):
        self.props[name] = encode_value(name, value)
        return self

    def get(self, name, default=None):
        return decode_value(name, self.props[name]) if name in self.props else default

    def __repr__(self):
        return "Brick(%s, pos=%s, rot=%s, %d props)" % (
            self.type, tuple(round(x, 2) for x in self.pos),
            tuple(round(x, 2) for x in self.rot), len(self.props))


class Vehicle:
    def __init__(self, bricks=None, version=VERSION):
        self.version = version
        self.bricks = list(bricks or [])
        self._type_order = None   # remembered table orders from a loaded file
        self._value_order = None

    def add(self, brick):
        """Append a brick, return its index (needed for wiring via SourceBricks)."""
        self.bricks.append(brick)
        return len(self.bricks) - 1

    # ------------------------------------------------------------------ reading
    @classmethod
    def loads(cls, data):
        version, nbricks, ntypes, nprops = struct.unpack_from("<BHHH", data, 0)
        if version != VERSION:
            raise ValueError("unsupported .brv version %d (only %d was reverse engineered)"
                             % (version, VERSION))
        p = 7
        types = []
        for _ in range(ntypes):
            n = data[p]
            types.append(data[p + 1:p + 1 + n].decode("utf-8"))
            p += 1 + n
        tables = []                       # list of (name, [raw values])
        for _ in range(nprops):
            n = data[p]
            name = data[p + 1:p + 1 + n].decode("utf-8")
            p += 1 + n
            cnt, dlen = struct.unpack_from("<HI", data, p)
            p += 6
            blob = data[p:p + dlen]
            p += dlen
            if cnt == 1:
                sizes = [dlen]
            elif cnt == 0:
                sizes = []
            else:
                fixed = struct.unpack_from("<H", data, p)[0]
                p += 2
                if fixed:
                    sizes = [fixed] * cnt
                else:
                    sizes = list(struct.unpack_from("<%dH" % cnt, data, p))
                    p += 2 * cnt
            if sum(sizes) != dlen:
                raise ValueError("corrupt property table %r" % name)
            vals, o = [], 0
            for s in sizes:
                vals.append(bytes(blob[o:o + s]))
                o += s
            tables.append((name, vals))
        bricks = []
        for _ in range(nbricks):
            tidx, plen = struct.unpack_from("<HI", data, p)
            p += 6
            pl = data[p:p + plen]
            p += plen
            n = pl[0]
            b = Brick(types[tidx])
            o = 1
            for _ in range(n):
                pi, vi = struct.unpack_from("<HH", pl, o)
                o += 4
                b.props[tables[pi][0]] = tables[pi][1][vi]
            b.pos = struct.unpack_from("<3f", pl, o)
            o += 12
            b.rot = struct.unpack_from("<3f", pl, o)
            o += 12
            b.aux, b.group = struct.unpack_from("<HH", pl, o)
            o += 4
            if o != plen:
                raise ValueError("brick payload has %d unexpected extra bytes" % (plen - o))
            bricks.append(b)
        if p != len(data):
            raise ValueError("%d unexpected trailing bytes" % (len(data) - p))
        v = cls(bricks, version)
        v._type_order = types
        v._value_order = OrderedDict((name, vals) for name, vals in tables)
        return v

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls.loads(f.read())

    # ------------------------------------------------------------------ writing
    def dumps(self, canonical=False):
        """Serialise.  canonical=False keeps the table order of the file this vehicle was
        loaded from (new entries are appended), canonical=True rebuilds all tables from
        scratch the way the game does: types in first-use order, property tables ordered
        by the first brick that uses them (ties by ENTRY_ORDER), values in first-use order,
        properties inside a brick in ENTRY_ORDER.  For both samples both modes give
        byte-identical output."""
        if len(self.bricks) > 0xFFFF:
            raise ValueError("a .brv can hold at most 65535 bricks")
        use_saved = (not canonical) and self._type_order is not None
        types = list(self._type_order) if use_saved else []
        used_vals = OrderedDict()
        if use_saved:
            for k, vals in self._value_order.items():
                used_vals[k] = list(vals)
        for b in self.bricks:
            if b.type not in types:
                types.append(b.type)
            for name, raw in b.props.items():
                lst = used_vals.setdefault(name, [])
                if raw not in lst:
                    lst.append(raw)
        if use_saved:
            # drop tables / values / types nothing uses any more, keep the saved order
            used_t = {b.type for b in self.bricks}
            types = [t for t in types if t in used_t]
            used_raw = {}
            for b in self.bricks:
                for name, raw in b.props.items():
                    used_raw.setdefault(name, set()).add(raw)
            used_vals = OrderedDict((k, [x for x in v if x in used_raw.get(k, ())])
                                    for k, v in used_vals.items() if k in used_raw)
            order = list(used_vals.keys())
        else:
            # tables are ordered by the first brick that uses them; ties (several properties
            # first used by the same brick) follow ENTRY_ORDER.  Verified on two files.
            first = {}
            for i, b in enumerate(self.bricks):
                for n in b.props:
                    first.setdefault(n, i)
            rank = {n: i for i, n in enumerate(ENTRY_ORDER)}
            order = sorted(first, key=lambda n: (first[n], rank.get(n, len(rank))))
        tindex = {t: i for i, t in enumerate(types)}
        pindex = {n: i for i, n in enumerate(order)}
        vindex = {n: {raw: i for i, raw in enumerate(used_vals[n])} for n in order}

        out = bytearray(struct.pack("<BHHH", self.version, len(self.bricks), len(types),
                                    len(order)))
        for t in types:
            out += _pstr_enc(t)
        for name in order:
            vals = used_vals[name]
            out += _pstr_enc(name)
            out += struct.pack("<HI", len(vals), sum(len(x) for x in vals))
            for x in vals:
                out += x
            if len(vals) > 1:
                sizes = [len(x) for x in vals]
                if len(set(sizes)) == 1:
                    out += struct.pack("<H", sizes[0])
                else:
                    out += struct.pack("<H", 0) + struct.pack("<%dH" % len(sizes), *sizes)
        for b in self.bricks:
            if len(b.props) > 255:
                raise ValueError("too many properties on one brick")
            pl = bytearray([len(b.props)])
            if canonical or not use_saved:
                rank = {n: i for i, n in enumerate(ENTRY_ORDER)}
                names = sorted(b.props, key=lambda n: rank.get(n, len(rank)))
            else:
                names = list(b.props)          # keep the order read from the file
            for name in names:
                pl += struct.pack("<HH", pindex[name], vindex[name][b.props[name]])
            pl += struct.pack("<3f", *b.pos) + struct.pack("<3f", *b.rot)
            pl += struct.pack("<HH", b.aux, b.group)
            out += struct.pack("<HI", tindex[b.type], len(pl)) + pl
        return bytes(out)

    def save(self, path, canonical=False):
        with open(path, "wb") as f:
            f.write(self.dumps(canonical))

    # ------------------------------------------------------------------ helpers
    def summary(self):
        by_type = Counter(b.type for b in self.bricks)
        lines = ["%d bricks, %d distinct types" % (len(self.bricks), len(by_type))]
        for t, n in by_type.most_common():
            lines.append("  %5d  %s" % (n, t))
        return "\n".join(lines)

    def bounding_box(self):
        """Axis aligned bounding box (min, max) in cm over all bricks that carry a BrickSize.
        Parts with a built-in size (wheels, seats, guns, ...) are NOT included, so on a
        vehicle that has them the box can be smaller than the one the game stores in the
        .brm.  The rotation order (pitch, yaw, roll about Y, Z, X, Unreal style) is
        unverified for angles that are not multiples of 90 degrees."""
        import math
        lo, hi = [1e18] * 3, [-1e18] * 3
        for b in self.bricks:
            sz = b.get("BrickSize")
            if sz is None:
                continue
            p, y, r = (math.radians(a) for a in b.rot)
            cp, sp, cy, sy, cr, sr = (math.cos(p), math.sin(p), math.cos(y), math.sin(y),
                                      math.cos(r), math.sin(r))
            R = [[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                 [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                 [-sp, cp * sr, cp * cr]]
            for ax in range(3):
                h = sum(abs(R[ax][k]) * sz[k] / 2 for k in range(3))
                lo[ax] = min(lo[ax], b.pos[ax] - h)
                hi[ax] = max(hi[ax], b.pos[ax] + h)
        return tuple(lo), tuple(hi)

    def to_json(self):
        out = []
        for i, b in enumerate(self.bricks):
            d = OrderedDict(index=i, type=b.type, pos=b.pos, rot=b.rot, group=b.group)
            d["props"] = OrderedDict((k, decode_value(k, v) if k in CODECS else v.hex())
                                     for k, v in b.props.items())
            out.append(d)
        return out


def _cli(argv):
    if len(argv) < 3 or argv[1] not in ("info", "roundtrip", "dump"):
        print(__doc__.split("USAGE")[1])
        return 2
    path = argv[2]
    raw = open(path, "rb").read()
    v = Vehicle.loads(raw)
    if argv[1] == "info":
        print(v.summary())
    elif argv[1] == "roundtrip":
        a, b = v.dumps(), v.dumps(canonical=True)
        print("size %d | keep-order write %s | canonical write %s" % (
            len(raw), "IDENTICAL" if a == raw else "DIFFERS",
            "IDENTICAL" if b == raw else "DIFFERS"))
        return 0 if a == raw and b == raw else 1
    else:
        out = argv[3] if len(argv) > 3 else path + ".json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(v.to_json(), f, ensure_ascii=False, indent=1)
        print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
