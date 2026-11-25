#!/usr/bin/env python3
"""main.py — THE WORLD TODAY, Wednesday 25 November 2026.

A self-contained program that draws one 1024x1024 broadsheet front page
summing up the day's world news, and writes it to entry.png. Standard
library only, no network, no randomness: every run writes identical bytes.

The page is built as a real newspaper front page: plate masthead, dateline
row, one dominant lead story with a drawn route diagram, two secondary
stories (one with a bar chart of the day's market moves), an IN BRIEF
column, a markets strip and a footer line. All type is drawn by a
hand-built stroke font (sans and serif voices) and a filled-polygon
masthead face; all pictures are diagrams drawn in code. No photographs.

Stories (each cross-checked on at least two independent sources):
  lead      Shenzhou-24 launches 25 Nov 00:18 UTC from Jiuquan; Muhammad
            Zeeshan Ali becomes the first Pakistani in orbit and the
            first foreign astronaut aboard Tiangong (AP, Xinhua, CMSA).
  secondary Gulf: Houthi drone hits a Riyadh financial-district tower
            on 24 Nov, 11 injured; Iran sets seven conditions for talks
            and its navy claims tankers hit mines, unverified
            (Saudi Civil Defense via SPA, Reuters, JMIC).
  secondary Markets: Nasdaq -1.48%, S&P 500 -0.50%, Dow +0.85% on
            24 Nov as tariff fears hit chips; Nvidia -5.86%, Micron
            -10.97%, SOX -7.88% (CNBC, Reuters, Xinhua).
  briefs    Huawei convicted on 10 of 12 counts in Brooklyn, acquitted
            of racketeering (Reuters, AP); Russian jets enter South
            Korea's air zone again (Yonhap); Malaysia to send 6,500
            Rohingya home in December (Reuters); Israeli strike kills
            Hamas security chief in Gaza City (Reuters, AP).
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------------------
# PNG output: 8-bit RGB, no filter, zlib level 9. Written from scratch here;
# the format is a fixed standard (signature, IHDR, one IDAT, IEND).
# ---------------------------------------------------------------------------


def _png_chunk(tag, payload):
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def encode_png(path, w, h, rows):
    """rows: list of h rows, each a bytes-like of w*3 RGB bytes."""
    body = bytearray()
    for row in rows:
        body.append(0)
        body += row
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    blob = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(body), 9))
        + _png_chunk(b"IEND", b"")
    )
    with open(path, "wb") as fh:
        fh.write(blob)


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

PAPER = (247, 243, 234)
INK = (26, 25, 22)
SOFT = (52, 50, 45)
FAINT = (122, 117, 107)
HAIR = (168, 161, 148)
RED = (172, 28, 36)
NAVY = (30, 52, 84)
GREEN = (22, 106, 62)
SEA = (64, 92, 118)
SKY = (172, 184, 198)
CREAM = (255, 254, 250)

# ---------------------------------------------------------------------------
# Raster: a supersampled RGB canvas (SS=2) with coverage blending.
# Public coordinates are design units on the final 1024x1024 grid.
# ---------------------------------------------------------------------------

SS = 2


class Raster:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.pw, self.ph = w * SS, h * SS
        self.buf = bytearray(bytes(bg) * (self.pw * self.ph))
        self.clip = None

    def _put(self, x, y, rgb, cov):
        if cov <= 0.0 or x < 0 or y < 0 or x >= self.pw or y >= self.ph:
            return
        c = self.clip
        if c is not None and not (c[0] <= x < c[2] and c[1] <= y < c[3]):
            return
        i = (y * self.pw + x) * 3
        b = self.buf
        if cov >= 1.0:
            b[i], b[i + 1], b[i + 2] = rgb
        else:
            inv = 1.0 - cov
            b[i] = int(b[i] * inv + rgb[0] * cov + 0.5)
            b[i + 1] = int(b[i + 1] * inv + rgb[1] * cov + 0.5)
            b[i + 2] = int(b[i + 2] * inv + rgb[2] * cov + 0.5)

    def box(self, x, y, w, h, rgb):
        x0 = max(0, int(round(x * SS)))
        y0 = max(0, int(round(y * SS)))
        x1 = min(self.pw, int(round((x + w) * SS)))
        y1 = min(self.ph, int(round((y + h) * SS)))
        c = self.clip
        if c is not None:
            x0, y0 = max(x0, c[0]), max(y0, c[1])
            x1, y1 = min(x1, c[2]), min(y1, c[3])
        for yy in range(y0, y1):
            base = yy * self.pw * 3
            for xx in range(x0, x1):
                i = base + xx * 3
                self.buf[i], self.buf[i + 1], self.buf[i + 2] = rgb

    def rule(self, x, y, w, thick, rgb):
        self.box(x, y, w, thick, rgb)

    def disc(self, cx, cy, r, rgb):
        """Filled disc, centre in design units, radius in design units."""
        rpx = max(1.0, r * SS)
        x0 = int((cx - r) * SS)
        x1 = int((cx + r) * SS) + 1
        y0 = int((cy - r) * SS)
        y1 = int((cy + r) * SS) + 1
        ccx, ccy = cx * SS, cy * SS
        for yy in range(max(0, y0), min(self.ph, y1)):
            for xx in range(max(0, x0), min(self.pw, x1)):
                d = math.hypot(xx + 0.5 - ccx, yy + 0.5 - ccy)
                if d <= rpx:
                    self._put(xx, yy, rgb, 1.0 if d <= rpx - 0.6 else 0.55)

    def seg(self, x0, y0, x1, y1, width, rgb):
        """Thick segment drawn as a chain of discs (round caps)."""
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length / max(0.35, width * 0.45)) + 1)
        for s in range(steps + 1):
            t = s / steps
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, width / 2.0, rgb)

    def poly(self, pts, rgb):
        """Filled polygon, even-odd scanline fill, points in design units."""
        if len(pts) < 3:
            return
        edges = []
        n = len(pts)
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if ay == by:
                continue
            edges.append((ax, ay, bx, by))
        ys = [p[1] for p in pts]
        y0, y1 = int(min(ys) * SS), int(max(ys) * SS) + 1
        for yy in range(max(0, y0), min(self.ph, y1)):
            y = (yy + 0.5) / SS
            xs = []
            for ax, ay, bx, by in edges:
                if (ay <= y < by) or (by <= y < ay):
                    t = (y - ay) / (by - ay)
                    xs.append(ax + (bx - ax) * t)
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa = int(xs[k] * SS)
                xb = int(xs[k + 1] * SS)
                for xx in range(max(0, xa), min(self.pw, xb)):
                    self._put(xx, yy, rgb, 1.0)

    def downscale(self):
        """Return the final 1024x1024 RGB rows (list of bytes)."""
        rows = []
        for y in range(self.h):
            row = bytearray()
            for x in range(self.w):
                r = g = b = 0
                for dy in range(SS):
                    for dx in range(SS):
                        i = ((y * SS + dy) * self.pw + (x * SS + dx)) * 3
                        r += self.buf[i]
                        g += self.buf[i + 1]
                        b += self.buf[i + 2]
                n = SS * SS
                row += bytes((r // n, g // n, b // n))
            rows.append(bytes(row))
        return rows

# ---------------------------------------------------------------------------
# Stroke font. Every glyph is a list of strokes on a 5-wide grid; capitals
# stand 7 units tall (y 0..7, baseline 7), lowercase sits on the same
# baseline with x-height 2..7 and descenders to 9.5. Encoded as strings:
# strokes separated by ";", points inside a stroke as "x,y" pairs.
# The sans voice draws every stroke at one width; the serif voice varies
# the width by stroke angle and adds small ticks at cap/baseline ends.
# ---------------------------------------------------------------------------

_GLYPHS = {
    "A": "0,7 2.5,0 5,7;1.2,4.5 3.8,4.5",
    "B": "0,0 0,7;0,0 3,0 5,1.5 3,3 0,3;0,3 3,3 5,4.5 3,7 0,7",
    "C": "5,1.5 3.5,0 1,0 0,1.5 0,5.5 1,7 3.5,7 5,5.5",
    "D": "0,0 0,7;0,0 3,0 5,2 5,5 3,7 0,7",
    "E": "0,0 0,7;0,0 5,0;0,3.5 4,3.5;0,7 5,7",
    "F": "0,0 0,7;0,0 5,0;0,3.5 4,3.5",
    "G": "5,1.5 3.5,0 1,0 0,1.5 0,5.5 1,7 3.5,7 5,5.5 5,3.5 2.5,3.5",
    "H": "0,0 0,7;5,0 5,7;0,3.5 5,3.5",
    "I": "0,0 5,0;2.5,0 2.5,7;0,7 5,7",
    "J": "1,0 4,0;3.5,0 3.5,5.5 2,7 0.5,6",
    "K": "0,0 0,7;4.5,0 0,3.5 5,7",
    "L": "0,0 0,7;0,7 5,7",
    "M": "0,7 0,0 2.5,4 5,0 5,7",
    "N": "0,7 0,0 5,7 5,0",
    "O": "1.5,0 3.5,0 5,1.5 5,5.5 3.5,7 1.5,7 0,5.5 0,1.5 1.5,0",
    "P": "0,0 0,7;0,0 3.5,0 5,1.5 3.5,3.5 0,3.5",
    "Q": "1.5,0 3.5,0 5,1.5 5,5.5 3.5,7 1.5,7 0,5.5 0,1.5 1.5,0;3,5 5,7",
    "R": "0,0 0,7;0,0 3.5,0 5,1.5 3.5,3.5 0,3.5;3,3.5 5,7",
    "S": "4.5,1 3,0 1,0 0,2 0,3 5,4 5,5 4,7 1,7 0,6",
    "T": "0,0 5,0;2.5,0 2.5,7",
    "U": "0,0 0,5.5 1,7 4,7 5,5.5 5,0",
    "V": "0,0 2.5,7 5,0",
    "W": "0,0 1.2,7 2.5,3.5 3.8,7 5,0",
    "X": "0,0 5,7;5,0 0,7",
    "Y": "0,0 2.5,3.5 5,0;2.5,3.5 2.5,7",
    "Z": "0,0 5,0 0,7 5,7",
    "a": "5,2.5 4,2 1,2 0,3 0,6 1,7 4,7 5,6 5,2;5,2 5,7",
    "b": "0,0 0,7;0,3.5 1,2 3.5,2 5,3.5 5,5.5 3.5,7 0,7",
    "c": "5,3.5 3.5,2 1,2 0,3.5 0,5.5 1,7 3.5,7 5,5.5",
    "d": "5,0 5,7;5,4 3,2 1,2 0,3.5 0,5.5 1,7 3,7 5,5.5",
    "e": "5,4 4,2 1,2 0,3.5 0,5.5 1,7 3.5,7 5,5.5;0,4.5 5,4.5",
    "f": "2,7 2,0 4.5,0;0,2.5 3.5,2.5",
    "g": "5,3 3.5,2 1,2 0,3.5 0,5.5 1,7 3.5,7 5,6;5,2 5,7 4,9.5 1,9.5",
    "h": "0,0 0,7;0,4 1.5,2 3.5,2 5,3.5 5,7",
    "i": "2.5,2 2.5,7;2.3,0.2 2.7,0.2",
    "j": "3.5,2 3.5,7 2,9.5 0.5,8.5;3.3,0.2 3.7,0.2",
    "k": "0,0 0,7;4.5,2 0,4.5 5,7",
    "l": "2.5,0 2.5,7",
    "m": "0,7 0,2 2,2 2,7;2,3.5 3.5,2 5,3.5 5,7",
    "n": "0,7 0,2 1.5,2 3.5,2 5,3.5 5,7",
    "o": "1.5,2 3.5,2 5,3.5 5,5.5 3.5,7 1.5,7 0,5.5 0,3.5 1.5,2",
    "p": "0,2 0,9.5;0,3.5 1,2 3.5,2 5,3.5 5,5.5 3.5,7 0,7",
    "q": "5,2 5,9.5;5,3.5 3,2 1,2 0,3.5 0,5.5 1,7 3,7 5,5.5",
    "r": "0,7 0,2;0,3.5 2,2 4,2.5 5,4",
    "s": "4.5,3 3.5,2 1.5,2 0,3 0,4 5,5 5,6 3.5,7 1.5,7 0.5,6",
    "t": "2.5,0 2.5,7;0,3 4,3;1.5,7 3.5,7",
    "u": "0,2 0,5.5 1,7 4,7 5,5.5 5,2",
    "v": "0,2 2.5,7 5,2",
    "w": "0,2 1.2,7 2.5,4 3.8,7 5,2",
    "x": "0,2 5,7;5,2 0,7",
    "y": "0,2 2.5,7 5,2;2.5,7 2.5,9.5 1,9.5",
    "z": "0,2 5,2 0,7 5,7",
    "0": "1.5,0 3.5,0 5,1.5 5,5.5 3.5,7 1.5,7 0,5.5 0,1.5 1.5,0",
    "1": "1,1 2.5,0 2.5,7;0,7 5,7",
    "2": "0,1 1.5,0 3.5,0 5,1.5 5,3.5 0,7 5,7",
    "3": "0,1 1.5,0 3.5,0 5,1.5 3.5,3.5 5,3.5 5,5.5 3.5,7 1.5,7 0,6",
    "4": "0,5 4,0 4,7;0,4.5 5,4.5",
    "5": "5,0 0,0 0,3.5 4,3.5 5,5 4,7 1,7 0,6",
    "6": "5,1 3.5,0 1,0 0,1.5 0,5.5 1,7 4,7 5,5.5 3.5,3.5 0,3.5",
    "7": "0,0 5,0 2,7",
    "8": "1.5,0 3.5,0 5,1.5 3.5,3.5 1.5,3.5 0,1.5 1.5,0;1.5,3.5 3.5,3.5 5,5.5 3.5,7 1.5,7 0,5.5 1.5,3.5",
    "9": "0,5.5 1,7 3.5,7 5,5.5 5,1.5 3.5,0 1.5,0 0,1.5 0,3.5 3.5,3.5",
    ".": "2.3,6.5 2.7,6.5",
    ",": "2.5,6.5 2.5,7.5 1,9",
    ":": "2.3,2.5 2.7,2.5;2.3,6.5 2.7,6.5",
    ";": "2.3,2.5 2.7,2.5;2.5,6.5 2.5,7.5 1,9",
    "!": "2.5,0 2.5,5;2.3,6.5 2.7,6.5",
    "?": "1,1 2.5,0 4,1 4,2.5 2.5,4 2.5,5;2.3,6.5 2.7,6.5",
    "'": "2.5,0 2,2",
    '"': "1.5,0 1,2;3.5,0 3,2",
    "-": "0,3.5 5,3.5",
    "–": "0,3.5 5,3.5",
    "—": "0,3.5 5,3.5",
    "(": "4,0 2,1.5 2,5.5 4,7",
    ")": "1,0 3,1.5 3,5.5 1,7",
    "/": "5,0 0,7",
    "&": "4,1 2.5,0 1,1 1,2.5 4.5,6 4,7 1.5,7 0.5,6 0.5,4.5 2.5,2.5",
    "%": "0,0 5,7;1.5,1 1.5,2.5;3.5,4.5 3.5,6",
    "$": "4,1 1,0 1,2 4,3 4,5 1,7 2.5,-0.5 2.5,7.5",
    "°": "2,0.5 3.5,0.5 4,1.5 3.5,2.5 2,2.5 1.5,1.5 2,0.5",
    "·": "2.3,3.3 2.7,3.3",
    "+": "2.5,1 2.5,6;0,3.5 5,3.5",
    "=": "0,2.5 5,2.5;0,4.5 5,4.5",
    "•": "2.3,3.3 2.7,3.3",
    "_": "0,7 5,7",
}

_NARROW = set("il.,':;!|°·•")
_WIDE = set("mwMW")


def _parse_glyph(spec):
    strokes = []
    for part in spec.split(";"):
        pts = []
        for tok in part.split():
            xs, ys = tok.split(",")
            pts.append((float(xs), float(ys)))
        if len(pts) >= 2:
            strokes.append(pts)
        elif len(pts) == 1:
            strokes.append([pts[0], (pts[0][0] + 0.4, pts[0][1])])
    return strokes


_GLYPH_CACHE = {}


def glyph_strokes(ch):
    if ch not in _GLYPH_CACHE:
        spec = _GLYPHS.get(ch, _GLYPHS["?"])
        _GLYPH_CACHE[ch] = _parse_glyph(spec)
    return _GLYPH_CACHE[ch]


def char_advance(ch, unit):
    if ch == " ":
        return 3.0 * unit
    if ch in _NARROW:
        return 3.1 * unit
    if ch in _WIDE:
        return 6.9 * unit
    return 5.9 * unit

# ---------------------------------------------------------------------------
# Plate face: filled shapes for the masthead "THE WORLD TODAY" only, drawn
# on an 8-wide x 14-tall grid. Each letter is a list of polygons; the
# rasteriser fills them solid, so the flag reads as real display type.
# ---------------------------------------------------------------------------

_PLATE = {
    "T": [[(0, 0), (8, 0), (8, 3), (5.2, 3), (5.2, 14), (2.8, 14), (2.8, 3), (0, 3)]],
    "H": [[(0, 0), (3, 0), (3, 5.5), (5, 5.5), (5, 0), (8, 0), (8, 14), (5, 14), (5, 8.5), (3, 8.5), (3, 14), (0, 14)]],
    "E": [[(0, 0), (8, 0), (8, 3), (3, 3), (3, 5.5), (6.5, 5.5), (6.5, 8.5), (3, 8.5), (3, 11), (8, 11), (8, 14), (0, 14)]],
    "W": [[(0, 0), (2.2, 0), (4, 8), (5.8, 0), (8, 0), (8, 14), (6.2, 14), (4, 5), (1.8, 14), (0, 14)]],
    "O": [[(0, 0), (8, 0), (8, 3), (0, 3)], [(0, 0), (3, 0), (3, 14), (0, 14)],
          [(5, 0), (8, 0), (8, 14), (5, 14)], [(0, 11), (8, 11), (8, 14), (0, 14)]],
    "R": [[(0, 0), (3, 0), (3, 14), (0, 14)], [(3, 0), (8, 0), (8, 2.5), (3, 2.5)],
          [(3, 4.5), (7, 4.5), (7, 7), (3, 7)], [(5.5, 0), (8, 0), (8, 7), (5.5, 7)],
          [(4, 6.5), (7, 6.5), (8, 14), (5, 14)]],
    "L": [[(0, 0), (3, 0), (3, 14), (0, 14)], [(0, 11), (8, 11), (8, 14), (0, 14)]],
    "D": [[(0, 0), (3, 0), (3, 14), (0, 14)], [(3, 0), (8, 0), (8, 3), (3, 3)],
          [(5, 0), (8, 0), (8, 14), (5, 14)], [(3, 11), (8, 11), (8, 14), (3, 14)]],
    "A": [[(0, 14), (2.2, 0), (4.2, 0), (2.6, 14)], [(3.8, 0), (6, 0), (8, 14), (5.4, 14)],
          [(2.2, 8.5), (5.8, 8.5), (5.8, 11), (2.2, 11)]],
    "Y": [[(0, 0), (2.5, 0), (4, 5), (5.5, 0), (8, 0), (5.2, 8), (5.2, 14), (2.8, 14), (2.8, 8)]],
    " ": [],
}


def plate_width(text, cap):
    unit = cap / 14.0
    total = 0.0
    for ch in text:
        total += 8.0 * unit if ch != " " else 4.0 * unit
        total += 1.1 * unit
    return total - 1.1 * unit


def draw_plate(cv, x, y, text, cap, rgb):
    """Draw filled masthead letters; (x, y) is the top-left of the run."""
    unit = cap / 14.0
    cx = x
    for ch in text:
        if ch == " ":
            cx += 5.1 * unit
            continue
        for poly in _PLATE.get(ch, []):
            scaled = [(cx + px * unit, y + py * unit) for (px, py) in poly]
            cv.poly(scaled, rgb)
        cx += 9.1 * unit


# ---------------------------------------------------------------------------
# Text engine. Sizes are in design px; a glyph unit is size/7. The serif
# voice thickens steep strokes and thins flat ones, and puts a short tick
# at stroke ends that land on the cap line or the baseline.
# ---------------------------------------------------------------------------


def _stroke_width(face, size, dx, dy):
    base = size * 0.085
    if face != "serif":
        return base
    steep = abs(dy) >= abs(dx)
    return base * (1.35 if steep else 0.78)


def _draw_glyph(cv, ch, x, top, size, face, rgb):
    unit = size / 7.0
    w = size * 0.085
    for pts in glyph_strokes(ch):
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            px0, py0 = x + ax * unit, top + ay * unit
            px1, py1 = x + bx * unit, top + by * unit
            sw = _stroke_width(face, size, bx - ax, by - ay)
            cv.seg(px0, py0, px1, py1, sw, rgb)
        if face == "serif":
            for (ax, ay) in (pts[0], pts[-1]):
                if ay in (0.0, 7.0):
                    tx = x + ax * unit
                    ty = top + ay * unit
                    cv.seg(tx - w * 0.9, ty, tx + w * 0.9, ty, w * 0.8, rgb)


def text_width(text, size, face="sans", tracking=0.0):
    unit = size / 7.0
    total = 0.0
    for ch in text:
        total += char_advance(ch, unit) + tracking
    return total - tracking if text else 0.0


def draw_text(cv, x, y, text, size, face="sans", rgb=INK, tracking=0.0):
    """Draw one line; y is the cap top. Returns the width drawn."""
    unit = size / 7.0
    cx = x
    for ch in text:
        if ch != " ":
            _draw_glyph(cv, ch, cx, y, size, face, rgb)
        cx += char_advance(ch, unit) + tracking
    return cx - x - tracking


def draw_text_centred(cv, cx, y, text, size, face="sans", rgb=INK, tracking=0.0):
    w = text_width(text, size, face, tracking)
    return draw_text(cv, cx - w / 2.0, y, text, size, face, rgb, tracking)


def wrap_text(text, size, face, max_w, max_lines=None):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if text_width(trial, size, face) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if max_lines is not None and len(lines) >= max_lines:
                return lines
    if cur:
        lines.append(cur)
    if max_lines is not None:
        return lines[:max_lines]
    return lines


def draw_wrapped(cv, x, y, lines, size, face, rgb, leading, justify=False, width=None):
    """Draw pre-wrapped lines; justified lines spread slack over gaps
    unless the slack per gap exceeds 7 px, in which case they go ragged."""
    yy = y
    for li, line in enumerate(lines):
        last = li == len(lines) - 1
        if justify and width is not None and not last and " " in line:
            natural = text_width(line, size, face)
            gaps = line.count(" ")
            slack = width - natural
            if gaps > 0 and slack / gaps <= 7.0 and slack > 0:
                extra = slack / gaps
                unit = size / 7.0
                cx = x
                for ch in line:
                    if ch != " ":
                        _draw_glyph(cv, ch, cx, yy, size, face, rgb)
                    cx += char_advance(ch, unit)
                    if ch == " ":
                        cx += extra
                yy += leading
                continue
        draw_text(cv, x, yy, line, size, face, rgb)
        yy += leading
    return yy


def autofit_size(text, size, face, max_w, max_lines, min_size=14.0):
    """Largest size <= `size` that fits the text in max_lines lines.
    The fit check counts ALL wrapped lines (uncapped); the capped wrap
    used at draw time would hide overflow and always claim a fit."""
    s = size
    while s > min_size:
        if len(wrap_text(text, s, face, max_w)) <= max_lines:
            return s
        s -= 0.5
    return s

# ---------------------------------------------------------------------------
# Furniture helpers
# ---------------------------------------------------------------------------


def hline(cv, x, y, w, rgb=HAIR, thick=1.0):
    cv.rule(x, y, w, thick, rgb)


def kicker(cv, x, y, text, size=13.0):
    return draw_text(cv, x, y, text, size, "sans", RED, tracking=1.6)


def byline(cv, x, y, text):
    return draw_text(cv, x, y, text, 11.0, "sans", FAINT, tracking=1.2)


def tri_up(cv, cx, cy, s, rgb):
    cv.poly([(cx, cy - s), (cx + s * 0.9, cy + s * 0.7), (cx - s * 0.9, cy + s * 0.7)], rgb)


def tri_down(cv, cx, cy, s, rgb):
    cv.poly([(cx, cy + s), (cx + s * 0.9, cy - s * 0.7), (cx - s * 0.9, cy - s * 0.7)], rgb)


# ---------------------------------------------------------------------------
# Drawn visuals. Schematic diagrams in code: a route map for the space
# lead (ground station, dashed climb arc, capsule, station), and a bar
# chart of one day's market moves.
# ---------------------------------------------------------------------------


def visual_route(cv, x, y, w, h):
    cv.box(x, y, w, h, PAPER)
    cv.rule(x, y, w, 1.0, INK)
    cv.rule(x, y + h - 1, w, 1.0, INK)
    cv.rule(x, y, 1.0, h, INK)
    cv.rule(x + w - 1, y, 1.0, h, INK)
    # hatched sky
    for i in range(9):
        hx = x + 18 + i * 46
        cv.seg(hx, y + 14, hx + 26, y + 30, 0.8, SKY)
    # stars
    for sx, sy in ((0.16, 0.16), (0.42, 0.10), (0.68, 0.20), (0.86, 0.12), (0.30, 0.30), (0.55, 0.28)):
        cv.disc(x + sx * w, y + sy * h, 1.6, INK)
    # ground line and launch site
    gy = y + h - 34
    cv.rule(x + 10, gy, w - 20, 1.5, INK)
    gx = x + 64
    cv.poly([(gx - 16, gy), (gx - 8, gy - 26), (gx + 8, gy - 26), (gx + 16, gy)], NAVY)
    cv.seg(gx, gy - 26, gx, gy - 44, 1.2, NAVY)
    draw_text(cv, x + w - 82, gy + 8, "JIUQUAN", 10.0, "sans", FAINT, tracking=1.0)
    # dashed climb arc to the station
    sx0, sy0 = gx, gy - 44
    sx1, sy1 = x + w - 78, y + 52
    steps = 26
    prev = None
    for i in range(steps + 1):
        t = i / steps
        px = sx0 + (sx1 - sx0) * t
        py = sy0 + (sy1 - sy0) * t - 46 * math.sin(math.pi * t)
        if prev is not None and i % 2 == 0:
            cv.seg(prev[0], prev[1], px, py, 1.6, NAVY)
        prev = (px, py)
    # capsule on the arc
    t = 0.55
    cx = sx0 + (sx1 - sx0) * t
    cy = sy0 + (sy1 - sy0) * t - 46 * math.sin(math.pi * t)
    cv.disc(cx, cy, 5.0, RED)
    cv.disc(cx, cy, 2.2, CREAM)
    # station: ringed module
    tx, ty = sx1, sy1
    cv.seg(tx - 30, ty, tx + 30, ty, 1.4, NAVY)
    cv.seg(tx, ty - 12, tx, ty + 12, 1.4, NAVY)
    cv.disc(tx, ty, 11.0, NAVY)
    cv.disc(tx, ty, 6.0, SKY)
    cv.disc(tx, ty, 2.4, INK)
    draw_text(cv, tx - 30, ty + 20, "TIANGONG", 10.0, "sans", FAINT, tracking=1.0)
    draw_text(cv, x + 10, y + h - 16, "SHENZHOU-24 · LONG MARCH 2F · 00:18 UTC", 9.5, "sans", FAINT, tracking=0.8)


def visual_bars(cv, x, y, w, h, points, labels, big):
    """points: list of % moves; labels: short tags under each bar.
    Bars above the axis are navy, below it red; the tallest bar sets the
    scale. Names sit in a reserved strip under the bar zone; `big` is the
    headline value drawn top-left inside the chart."""
    zone = h - 16
    axis = y + zone * 0.42
    cv.rule(x, axis, w, 1.2, INK)
    top = max(abs(v) for v in points) or 1.0
    bw = w / len(points)
    for i, v in enumerate(points):
        cx = x + bw * (i + 0.5)
        bar_w = bw * 0.52
        bh = (abs(v) / top) * zone * 0.55
        if v >= 0:
            cv.box(cx - bar_w / 2, axis - bh, bar_w, bh, NAVY)
        else:
            cv.box(cx - bar_w / 2, axis, bar_w, bh, RED)
        draw_text_centred(cv, cx, y + h - 11, labels[i], 8.5, "sans", FAINT, tracking=0.6)
    draw_text(cv, x, y + 2, big, 22.0, "serif", INK)

# ---------------------------------------------------------------------------
# Page assembly. A running cursor lays the page out top to bottom; the
# secondary row is capped at y=940 and the markets strip is anchored at
# y=950, so nothing can ever print through them.
# ---------------------------------------------------------------------------

MX = 40
CW = 944
RIGHT = MX + CW


def render(content, path):
    cv = Raster(1024, 1024, PAPER)

    # ---- folio strip -------------------------------------------------------
    draw_text(cv, MX, 22, content["folio"], 10.5, "sans", FAINT, tracking=1.0)
    draw_text_centred(cv, 512, 22, content["edition"], 10.5, "sans", FAINT, tracking=1.0)
    fw = text_width("LATE CITY FINAL", 10.5, "sans", tracking=1.0)
    draw_text(cv, RIGHT - fw, 22, "LATE CITY FINAL", 10.5, "sans", FAINT, tracking=1.0)
    hline(cv, MX, 38, CW)

    # ---- nameplate + double rule ------------------------------------------
    name = "THE WORLD TODAY"
    nw = plate_width(name, 92)
    draw_plate(cv, 512 - nw / 2.0, 52, name, 92, INK)
    cv.rule(MX, 152, CW, 3.0, INK)
    hline(cv, MX, 158, CW)

    # ---- dateline row ------------------------------------------------------
    draw_text(cv, MX, 168, content["dateline_left"], 10.5, "sans", FAINT, tracking=1.0)
    draw_text_centred(cv, 512, 166, content["date"], 15.0, "serif", INK)
    ww = text_width(content["weather"], 10.5, "sans", tracking=1.0)
    draw_text(cv, RIGHT - ww, 168, content["weather"], 10.5, "sans", FAINT, tracking=1.0)
    hline(cv, MX, 188, CW)

    # ---- lead story --------------------------------------------------------
    lead = content["lead"]
    y = 204
    kicker(cv, MX, y, lead["kicker"])
    y += 22
    hsize = autofit_size(lead["headline"], 57.0, "serif", CW, 2)
    hlead = hsize * 1.21
    hlines = wrap_text(lead["headline"], hsize, "serif", CW, 2)
    for ln in hlines:
        draw_text(cv, MX, y, ln, hsize, "serif", INK)
        y += hlead
    y += 12
    dlines = wrap_text(lead["deck"], 20.5, "serif", CW, 2)
    for ln in dlines:
        draw_text(cv, MX, y, ln, 20.5, "serif", SOFT)
        y += 24
    y += 18
    row_y = y
    vx, vy, vw, vh = MX, row_y, 444, 204
    visual_route(cv, vx, vy, vw, vh)
    cy = vy + vh + 10
    clines = wrap_text(lead["caption"], 13.0, "serif", vw, 2)
    for ln in clines:
        draw_text(cv, vx, cy, ln, 13.0, "serif", SOFT)
        cy += 16
    cy += 4
    draw_text(cv, vx, cy, lead["credit"], 10.5, "sans", FAINT, tracking=1.0)
    cap_end = cy + 12
    # right zone: stat block, byline, two justified body columns
    zx = vx + vw + 24
    zw = RIGHT - zx
    stat = lead.get("stat")
    by = row_y
    if stat:
        draw_text(cv, zx, by, stat["value"], 54.0, "serif", INK)
        by += 58
        draw_text(cv, zx, by, stat["label"], 12.0, "sans", RED, tracking=1.6)
        by += 18
        for ln in wrap_text(stat["sub"], 12.0, "serif", zw, 2):
            draw_text(cv, zx, by, ln, 12.0, "serif", SOFT)
            by += 14
        by += 6
    byline(cv, zx, by, lead["byline"])
    by += 20
    col_w = (zw - 22) / 2.0
    anchor = row_y + 250
    max_lines = max(2, int((anchor - by) / 18.5))
    blines = wrap_text(lead["body"], 13.5, "serif", col_w, max_lines * 2)
    half = (len(blines) + 1) // 2
    draw_wrapped(cv, zx, by, blines[:half], 13.5, "serif", SOFT, 18.5,
                 justify=True, width=col_w)
    draw_wrapped(cv, zx + col_w + 22, by, blines[half:], 13.5, "serif", SOFT,
                 18.5, justify=True, width=col_w)
    body_end = by + max(len(blines[:half]), len(blines[half:])) * 18.5
    lead_bottom = max(cap_end, body_end)
    cv.rule(MX, lead_bottom + 14, CW, 3.0, INK)

    # ---- secondary row -----------------------------------------------------
    y0 = lead_bottom + 34
    col_x = [MX, 364, 688]
    col_w2 = 296
    cv.rule(350, y0, 1.0, 940 - y0, HAIR)
    cv.rule(674, y0, 1.0, 940 - y0, HAIR)
    stories = content["stories"]
    for idx, st in enumerate(stories):
        cx = col_x[idx]
        yy = y0
        kicker(cv, cx, yy, st["kicker"], size=12.0)
        yy += 20
        hsize2 = autofit_size(st["headline"], 26.5, "serif", col_w2, 3)
        hlines2 = wrap_text(st["headline"], hsize2, "serif", col_w2, 3)
        for ln in hlines2:
            draw_text(cv, cx, yy, ln, hsize2, "serif", INK)
            yy += hsize2 * 1.16
        yy += 8
        if "chart" in st:
            ch = st["chart"]
            visual_bars(cv, cx, yy, col_w2, 76, ch["points"], ch["labels"], ch["value"])
            yy += 76 + 10
            cap = max(2, int((940 - yy) / 18.5))
            slines = wrap_text(st["body"], 13.5, "serif", col_w2, cap)
            draw_wrapped(cv, cx, yy, slines, 13.5, "serif", SOFT, 18.5)
        else:
            cap = max(2, int((940 - yy) / 18.5))
            slines = wrap_text(st["body"], 13.5, "serif", col_w2, cap)
            draw_wrapped(cv, cx, yy, slines, 13.5, "serif", SOFT, 18.5)
    # IN BRIEF column
    bx = col_x[2]
    byy = y0
    draw_text(cv, bx, byy, "IN BRIEF", 13.0, "sans", INK, tracking=1.6)
    byy += 26
    for i, (lab, txt) in enumerate(content["briefs"]):
        draw_text(cv, bx, byy, lab, 11.0, "sans", RED, tracking=1.2)
        byy += 14
        tlines = wrap_text(txt, 12.5, "serif", col_w2, 2)
        for ln in tlines:
            draw_text(cv, bx, byy, ln, 12.5, "serif", SOFT)
            byy += 14.5
        byy += 3
        if i < len(content["briefs"]) - 1:
            hline(cv, bx, byy, col_w2)
            byy += 7

    # ---- markets strip -----------------------------------------------------
    cv.rule(MX, 950, CW, 3.0, INK)
    draw_text(cv, MX, 962, "MARKETS", 11.0, "sans", INK, tracking=1.6)
    ex = 190
    for (name, value, change) in content["markets"]:
        draw_text(cv, ex, 960, name, 9.5, "sans", FAINT, tracking=1.0)
        vw2 = draw_text(cv, ex, 972, value, 20.0, "serif", INK)
        if change:
            up = change.startswith("+")
            col = GREEN if up else RED
            tx = ex + vw2 + 12
            if up:
                tri_up(cv, tx + 4, 984, 4.0, col)
            else:
                tri_down(cv, tx + 4, 984, 4.0, col)
            draw_text(cv, tx + 11, 976, change, 11.0, "sans", col)
        else:
            draw_text(cv, ex + vw2 + 12, 976, "—", 11.0, "sans", FAINT)
        ex += 190

    # ---- footer ------------------------------------------------------------
    draw_text(cv, MX, 1004, content["footer"], 10.0, "sans", FAINT, tracking=0.8)

    rows = cv.downscale()
    encode_png(path, 1024, 1024, rows)

# ---------------------------------------------------------------------------
# The day's content: Wednesday 25 November 2026.
# ---------------------------------------------------------------------------

CONTENT = {
    "folio": "VOL. IV · NO. 329",
    "edition": "WORLD EDITION",
    "date": "WEDNESDAY 25 NOVEMBER 2026",
    "weather": "LONDON 8° CLOUDY",
    "dateline_left": "LONDON",
    "lead": {
        "kicker": "JIUQUAN · SPACE",
        "headline": "SHENZHOU-24 FLIES FIRST PAKISTANI TO ORBIT",
        "deck": "China sends three astronauts to Tiangong; Muhammad Zeeshan Ali, 40, is the first foreign visitor to the station.",
        "byline": "BY STAFF CORRESPONDENT",
        "body": "JIUQUAN — A Long March 2F rocket lifted Shenzhou-24 into orbit at 00:18 UTC, carrying commander Tang Hongbo, Wu Yi and Pakistani astronaut Muhammad Zeeshan Ali. Ali, 40, spends a week on Tiangong doing biotech tests, then returns on Shenzhou-23.",
        "caption": "Shenzhou-24 lifts off from Jiuquan with the first foreign astronaut aboard.",
        "credit": "Staff illustration",
        "stat": {
            "value": "1st",
            "label": "FIRST FOREIGNER",
            "sub": "first foreigner aboard Tiangong",
        },
    },
    "stories": [
        {
            "kicker": "RIYADH · GULF",
            "headline": "RIYADH TOWER HIT AGAIN",
            "body": "A Houthi drone hit a Riyadh financial tower Tuesday, injuring 11. Iran sets seven terms for talks; its mine claims are unverified.",
        },
        {
            "kicker": "NEW YORK · MARKETS",
            "headline": "AI SELL-OFF RETURNS",
            "body": "Nasdaq fell 1.5% as chips sank; the Dow rose 0.8%.",
            "chart": {
                "points": [0.85, -0.5, -1.48, -5.86, -10.97],
                "labels": ["DOW", "S&P", "NAS", "NVDA", "MICR"],
                "value": "-1.5%",
            },
        },
    ],
    "briefs": [
        ("NEW YORK", "Huawei guilty on 10 counts"),
        ("SEOUL", "Russian jets near S. Korea"),
        ("KUALA LUMPUR", "Malaysia to return 6,500 Rohingya"),
        ("GAZA CITY", "Hamas security chief killed"),
    ],
    "markets": [
        ("NASDAQ", "23,734", "-1.48%"),
        ("S&P 500", "7,201", "-0.50%"),
        ("DOW", "50,019", "+0.85%"),
        ("BRENT", "$88.97", ""),
    ],
    "footer": "THE WORLD TODAY — drawn entirely by a program; no photographs. Wednesday 25 November 2026.",
}


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "out")
    os.makedirs(outdir, exist_ok=True)
    render(CONTENT, os.path.join(outdir, "entry.png"))


if __name__ == "__main__":
    main()
