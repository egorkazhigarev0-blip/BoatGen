#!/usr/bin/env python3
"""
brm.py - reader / writer for Brick Rigs vehicle metadata (MetaData.brm, version 18).

Reverse-engineered from TWO samples (a published 1135-brick pickup and a local 32-brick
build), so only part of the layout is understood.  The part that is not understood
(`id_section`) is kept as raw bytes and written back unchanged, which makes the read ->
write round trip byte exact (verified on both samples).

LAYOUT (little endian)
    u8   version                  18
    u16  name_length, name        UTF-8
    u16  description_length, description
    u16  brick_count
    f32  size_x, size_y, size_z   bounding box in cm.  For scalable bricks it can be computed
                                  from the .brv (see Vehicle.bounding_box in brv.py); parts
                                  with a built-in size (wheels, seats, ...) are not included
                                  in that computation, so x/z can come out smaller.
    f32  weight                   meaning unverified (2689.9 / 61.9 in the samples)
    f32  price                    meaning unverified (88516.4 / 13630.9)
    id_section                    UNKNOWN, variable length (15 bytes for the local build,
                                  33 bytes for the pickup that was published to the Workshop:
                                  there it contains the string "Steam" and a 64-bit number
                                  that looks like the Workshop item id).  Both samples start
                                  with the same 6 bytes.
    u64  created_ticks            .NET ticks (100 ns since 0001-01-01, UTC)
    u64  modified_ticks
    u8   tag_count (3), then tag_count x (u8 length, text)
         the three slots hold e.g. "Truck", "_2000s", "Military", or "None" when unset
"""
import struct
import sys
from datetime import datetime, timedelta

_EPOCH = datetime(1, 1, 1)


def _ticks_ok(t):
    return datetime(2000, 1, 1) <= _EPOCH + timedelta(microseconds=t // 10) <= datetime(2100, 1, 1)


class Meta:
    def __init__(self):
        self.version = 18
        self.name = ""
        self.description = ""
        self.brick_count = 0
        self.size = (0.0, 0.0, 0.0)
        self.weight = 0.0
        self.price = 0.0
        self.id_section = bytes(15)
        self.created_ticks = 0
        self.modified_ticks = 0
        self.tags = ["None", "None", "None"]

    @classmethod
    def loads(cls, d):
        m = cls()
        p = 0
        m.version = d[p]
        p += 1
        n = struct.unpack_from("<H", d, p)[0]
        p += 2
        m.name = d[p:p + n].decode("utf-8")
        p += n
        n = struct.unpack_from("<H", d, p)[0]
        p += 2
        m.description = d[p:p + n].decode("utf-8")
        p += n
        m.brick_count = struct.unpack_from("<H", d, p)[0]
        p += 2
        sx, sy, sz, m.weight, m.price = struct.unpack_from("<5f", d, p)
        m.size = (sx, sy, sz)
        p += 20
        # The middle part has no length field, so find the tag list that ends exactly at
        # the end of the file and the two timestamps right before it.
        for q in range(p + 16, len(d)):
            cnt = d[q]
            if cnt > 16:
                continue
            o, tags, ok = q + 1, [], True
            for _ in range(cnt):
                if o >= len(d):
                    ok = False
                    break
                ln = d[o]
                if o + 1 + ln > len(d):
                    ok = False
                    break
                try:
                    tags.append(d[o + 1:o + 1 + ln].decode("utf-8"))
                except UnicodeDecodeError:
                    ok = False
                    break
                o += 1 + ln
            if not ok or o != len(d):
                continue
            c, mo = struct.unpack_from("<QQ", d, q - 16)
            if _ticks_ok(c) and _ticks_ok(mo):
                m.id_section = bytes(d[p:q - 16])
                m.created_ticks, m.modified_ticks = c, mo
                m.tags = tags
                return m
        raise ValueError("unrecognised .brm layout")

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls.loads(f.read())

    def dumps(self):
        out = bytearray([self.version])
        nb = self.name.encode("utf-8")
        db = self.description.encode("utf-8")
        out += struct.pack("<H", len(nb)) + nb + struct.pack("<H", len(db)) + db
        out += struct.pack("<H", self.brick_count)
        out += struct.pack("<5f", *self.size, self.weight, self.price)
        out += self.id_section
        out += struct.pack("<QQ", self.created_ticks, self.modified_ticks)
        out += bytes([len(self.tags)])
        for t in self.tags:
            tb = t.encode("utf-8")
            out += bytes([len(tb)]) + tb
        return bytes(out)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.dumps())

    @staticmethod
    def ticks_to_datetime(t):
        return _EPOCH + timedelta(microseconds=t // 10)

    @staticmethod
    def datetime_to_ticks(dt):
        return int((dt - _EPOCH).total_seconds() * 10_000_000)

    def describe(self):
        return ("name=%r desc=%r bricks=%d size(cm)=%s weight=%.1f price=%.1f tags=%s\n"
                "created=%s UTC modified=%s UTC id_section=%d bytes" % (
                    self.name, self.description, self.brick_count,
                    tuple(round(x, 1) for x in self.size), self.weight, self.price,
                    self.tags, self.ticks_to_datetime(self.created_ticks),
                    self.ticks_to_datetime(self.modified_ticks), len(self.id_section)))


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("info", "roundtrip"):
        print("usage: brm.py info|roundtrip MetaData.brm")
        sys.exit(2)
    raw = open(sys.argv[2], "rb").read()
    m = Meta.loads(raw)
    if sys.argv[1] == "info":
        print(m.describe())
    else:
        same = m.dumps() == raw
        print("round trip", "IDENTICAL" if same else "DIFFERS")
        sys.exit(0 if same else 1)
