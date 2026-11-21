#!/usr/bin/env python3
"""news-image-20261121 — deterministic front-page renderer.

Renders ONE 1024x1024 PNG summing up Saturday 21 November 2026 world news
as a newspaper front page: masthead + date, two big event panels (Poland/NATO,
Wall Street correction), three-item supporting strip.

Python 3.12/3.13 stdlib only, no network, no clock, no randomness — running it
twice produces byte-identical output. Writes to $MAKEFUN_OUTPUT_DIR/entry.png
(or /output/entry.png when the variable is unset).
"""

import os
import struct
import zlib

W, H = 1024, 1024

PAPER = (251, 247, 238)
INK = (17, 17, 17)
WHITE = (255, 255, 255)
RED = (185, 28, 28)
DARKRED = (127, 29, 29)
BLUE = (30, 58, 138)
GREY = (96, 96, 96)

# 5x7 bitmap font. Each glyph is 7 rows; each row is a 5-bit integer,
# most-significant bit = leftmost pixel. Written by hand in this session.
FONT = {
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 21, 10),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 6, 8, 16, 31),
    "3": (31, 2, 4, 2, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    " ": (0, 0, 0, 0, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 12, 12),
    ",": (0, 0, 0, 0, 12, 4, 8),
    ":": (0, 12, 12, 0, 12, 12, 0),
    ";": (0, 12, 12, 0, 12, 4, 8),
    "'": (4, 4, 8, 0, 0, 0, 0),
    "-": (0, 0, 0, 14, 0, 0, 0),
    "!": (4, 4, 4, 4, 4, 0, 4),
    "?": (14, 17, 1, 2, 4, 0, 4),
    "%": (25, 26, 2, 4, 8, 22, 19),
    "$": (4, 15, 20, 14, 5, 30, 4),
    "&": (12, 18, 20, 8, 21, 18, 13),
    "/": (1, 2, 2, 4, 8, 8, 16),
    "(": (2, 4, 8, 8, 8, 4, 2),
    ")": (8, 4, 2, 2, 2, 4, 8),
    "+": (0, 4, 4, 14, 4, 4, 0),
    "=": (0, 0, 14, 0, 14, 0, 0),
    '"': (10, 10, 0, 0, 0, 0, 0),
}


def text_width(s, scale):
    return len(s) * 6 * scale


def wrap_text(s, scale, max_w):
    """Greedy word wrap. Returns a list of lines, each <= max_w pixels."""
    lines = []
    for paragraph in s.split("\n"):
        words = paragraph.split(" ")
        cur = ""
        for word in words:
            trial = word if not cur else cur + " " + word
            if text_width(trial, scale) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines


class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)
        self.fill_rect(0, 0, w, h, bg)

    def px(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = color[0]
            self.buf[i + 1] = color[1]
            self.buf[i + 2] = color[2]

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.buf[i] = color[0]
                self.buf[i + 1] = color[1]
                self.buf[i + 2] = color[2]

    def hline(self, x, y, w, color, t=1):
        self.fill_rect(x, y, w, t, color)

    def vline(self, x, y, h, color, t=1):
        self.fill_rect(x, y, t, h, color)

    def line(self, x0, y0, x1, y1, color, t=1):
        """Thick line via DDA, drawing t x t blocks along the path."""
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        half = t // 2
        for s in range(steps + 1):
            x = x0 + round(dx * s / steps)
            y = y0 + round(dy * s / steps)
            self.fill_rect(x - half, y - half, t, t, color)

    def circle(self, cx, cy, r, color, t=2):
        """Midpoint circle outline."""
        x = 0
        y = r
        d = 1 - r
        half = t // 2
        while x <= y:
            for sx, sy in ((x, y), (y, x), (-x, y), (-y, x),
                           (x, -y), (y, -x), (-x, -y), (-y, -x)):
                self.fill_rect(cx + sx - half, cy + sy - half, t, t, color)
            x += 1
            if d < 0:
                d += 2 * x + 1
            else:
                y -= 1
                d += 2 * (x - y) + 1

    def text(self, x, y, s, scale, color):
        for ci, ch in enumerate(s):
            glyph = FONT.get(ch, FONT[" "])
            ox = x + ci * 6 * scale
            for row in range(7):
                bits = glyph[row]
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        self.fill_rect(ox + col * scale, y + row * scale,
                                       scale, scale, color)

    def text_centered(self, cx, y, s, scale, color):
        self.text(cx - text_width(s, scale) // 2, y, s, scale, color)

    def wrapped(self, x, y, s, scale, color, max_w, leading):
        """Draw wrapped text; returns y just past the last line."""
        for line in wrap_text(s, scale, max_w):
            self.text(x, y, line, scale, color)
            y += 7 * scale + leading
        return y


def draw_panel(cv, x, y, w, h, accent, dark, kicker, headline_lines,
               sub, body, graphic):
    cv.fill_rect(x, y, w, h, WHITE)
    cv.fill_rect(x, y, w, 3, INK)
    cv.fill_rect(x, y + h - 3, w, 3, INK)
    cv.fill_rect(x, y, 3, h, INK)
    cv.fill_rect(x + w - 3, y, 3, h, INK)
    # Kicker bar with white text.
    cv.fill_rect(x + 3, y + 3, w - 6, 44, accent)
    cv.text_centered(x + w // 2, y + 3 + 11, kicker, 3, WHITE)
    cy = y + 3 + 44 + 16
    for line in headline_lines:
        cv.text(x + 16, cy, line, 5, INK)
        cy += 7 * 5 + 4
    cv.hline(x + 16, cy + 2, w - 32, accent, 3)
    cy += 16
    cy = cv.wrapped(x + 16, cy, sub, 3, dark, w - 32, 5)
    cy += 8
    # Body at scale 2: scale 3 wrapped to 7-8 lines and collided with the
    # bottom graphic band (radar rings / chart line crossed the last lines).
    cy = cv.wrapped(x + 16, cy, body, 2, INK, w - 32, 3)
    graphic(cv, x, y, w, h)


def radar_graphic(cv, x, y, w, h):
    """Concentric target rings + crosshair, bottom-centred in the panel."""
    cx = x + w // 2
    cy = y + h - 58
    for r in (42, 28, 14):
        cv.circle(cx, cy, r, RED, 2)
    cv.fill_rect(cx - 4, cy - 4, 8, 8, RED)
    cv.hline(cx - 52, cy, 104, RED, 2)
    cv.vline(cx, cy - 52, 104, RED, 2)


def chart_graphic(cv, x, y, w, h):
    """Descending market line with arrowhead, bottom of the panel."""
    x0 = x + 24
    x1 = x + w - 24
    top = y + h - 108
    bot = y + h - 24
    cv.text(x0, top - 22, "S&P 500 - ONE WEEK", 2, GREY)
    pts = [(0.00, 0.10), (0.16, 0.32), (0.32, 0.24), (0.48, 0.52),
           (0.64, 0.60), (0.80, 0.82), (1.00, 0.96)]
    coords = [(round(x0 + fx * (x1 - x0)), round(top + fy * (bot - top)))
              for fx, fy in pts]
    for (ax, ay), (bx, by) in zip(coords, coords[1:]):
        cv.line(ax, ay, bx, by, RED, 4)
    ex, ey = coords[-1]
    cv.line(ex, ey, ex - 16, ey - 2, RED, 4)
    cv.line(ex, ey, ex - 4, ey - 16, RED, 4)


def render():
    cv = Canvas(W, H, PAPER)

    # Masthead.
    cv.text_centered(W // 2, 30, "THE WORLD TODAY", 8, INK)
    cv.hline(24, 98, W - 48, INK, 4)
    cv.text_centered(W // 2, 110, "SATURDAY 21 NOVEMBER 2026", 4, RED)
    cv.text_centered(
        W // 2, 148,
        "THE DAY'S TWO BIGGEST STORIES - AS REPORTED ON 21 NOVEMBER 2026",
        2, INK)
    cv.hline(24, 172, W - 48, INK, 4)

    # Panel 1 — Poland / NATO (verified: Reuters/AP 20 Nov; Poland's formal
    # NATO request + Rutte's Warsaw visit are the Saturday 21 Nov developments).
    draw_panel(
        cv, 24, 184, 476, 520, RED, DARKRED,
        "EUROPE - NATO",
        ["RUSSIAN", "MISSILES", "LAND IN", "POLAND"],
        "WARSAW ASKS NATO FOR MORE TROOPS",
        "KH-101 CRUISE MISSILE CRASHES NEAR NOWY LIPOWIEC. "
        "PM TUSK CALLS IT AN INTENTIONAL PROVOCATION. NO INJURIES. "
        "JETS SCRAMBLED, PATRIOTS ON ALERT.",
        radar_graphic)

    # Panel 2 — Wall Street (verified: AP/NPR, Morningstar, Fool, Schwab —
    # Friday 20 Nov close, first reported 21 Nov UTC, Saturday's business lead).
    draw_panel(
        cv, 524, 184, 476, 520, BLUE, BLUE,
        "MARKETS - WALL STREET",
        ["S&P 500", "SINKS INTO", "CORRECTION"],
        "AI ROUT WIPES OUT NASDAQ'S 2026 GAINS",
        "S&P -3.7% TO 6,910. NASDAQ -5.3% TO 22,618. "
        "DOW -1.9% TO 48,147. WORST WEEK SINCE 2020. "
        "NVIDIA TUMBLES AS SEC REPORTEDLY PROBES ITS ACCOUNTS. "
        "ANTHROPIC -9% A DAY AFTER RECORD $81BN IPO.",
        chart_graphic)

    # Supporting strip.
    cv.text_centered(W // 2, 720, "ALSO IN THE NEWS", 3, INK)
    cv.hline(24, 748, W - 48, INK, 2)
    cols = [
        (24, RED, "GTA 6",
         "GTA 6 MAKES $3.79BN IN A DAY - THE BIGGEST ENTERTAINMENT "
         "LAUNCH EVER. 32.5M COPIES SOLD."),
        (352, RED, "CYCLONE AKVAN",
         "CYCLONE AKVAN SLAMS INDIA'S EAST COAST. "
         "ABOUT 300,000 PEOPLE EVACUATED."),
        (680, RED, "DENMARK",
         "DENMARK SAYS IT FOILED A RUSSIAN PLOT TO KILL "
         "RAPPER KYIVSTONER."),
    ]
    for i, (cx0, accent, label, body) in enumerate(cols):
        if i:
            cv.vline(cx0 - 16, 764, 150, INK, 2)
        cv.text(cx0, 764, label, 3, accent)
        cv.hline(cx0, 792, 312, accent, 2)
        cv.wrapped(cx0, 806, body, 2, INK, 312, 3)

    # Footer.
    cv.hline(24, 936, W - 48, INK, 2)
    cv.text_centered(W // 2, 950, "SATURDAY 21 NOVEMBER 2026 - THE WORLD TODAY",
                     2, INK)
    return cv


def write_png(path, cv):
    raw = b"".join(
        b"\x00" + bytes(cv.buf[y * cv.w * 3:(y + 1) * cv.w * 3])
        for y in range(cv.h))

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "entry.png")
    size = write_png(path, render())
    print("wrote %s (%d bytes)" % (path, size))


if __name__ == "__main__":
    main()
