#!/usr/bin/env python3
"""Render the profile header banner as a dark and a light SVG.

GitHub serves README images through its camo proxy as plain <img>, so the
SVGs must be fully self-contained: no external fonts, no scripts. Two files
(rather than one SVG with an internal prefers-color-scheme query) let the
README's <picture> element follow the viewer's GitHub theme setting instead
of only their operating-system theme.

The right-hand artwork ports the angushsu.me hero DotField to static SVG +
CSS: the AH monogram assembles from scattered dots over a faint grid that
dissolves toward its edges, then shimmers in a slow diagonal wave. Geometry,
timing, and the seeded scatter mirror components/dot-field.tsx; the mask in
ah-monogram.txt is copied from lib/monogram.ts.

Usage:
    python3 scripts/build_header.py      # writes assets/header-{dark,light}.svg
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SCRIPTS = Path(__file__).resolve().parent

ACCENT = "#2F81F7"

WIDTH, HEIGHT = 880, 220
LEFT = 36

NAME = "Angus Hsu"
ROLE = "Full-Stack Engineer · Taipei"
PITCH = "Web applications · Data platforms · AI integration"
STATUS = "SHIPPING · UTC+8"
TAGS = ("React", "TypeScript", "Python", "FastAPI", "MCP", "TM1")

# Dot field: the box it occupies on the right, and how the mask is sampled.
FIELD_X, FIELD_W = 600, WIDTH - 600
MASK_STEP = 2  # the site also samples every other cell on small canvases
MASK_FILL = 0.84  # share of the field the monogram may span

# Animation, matching dot-field.tsx (milliseconds there, seconds here).
ASSEMBLY_S = 1.5
STAGGER_S = 0.75
START_DELAY_S = 0.45  # let the name land first
SHIMMER_PERIOD_S = 2 * math.pi / 1.2  # the site's wave advances 0.0012 rad/ms
SHIMMER_BUCKETS = 12
GRID_ALPHA_BUCKETS = 10
SCATTER_SEED = 611

# Monospace glyph advance at 11px, used to size tag pills without a renderer.
MONO_ADVANCE_11PX = 6.7


@dataclass(frozen=True)
class Palette:
    bg: str
    border: str
    title: str
    subtitle: str
    dim: str
    tag_bg: str
    tag_border: str
    tag_text: str


DARK = Palette(
    bg="#0d1117",
    border="#21262d",
    title="#e6edf3",
    subtitle="#8b949e",
    dim="#6e7681",
    tag_bg="#161b22",
    tag_border="#30363d",
    tag_text="#8b949e",
)

LIGHT = Palette(
    bg="#ffffff",
    border="#d0d7de",
    title="#1f2328",
    subtitle="#656d76",
    dim="#8c959f",
    tag_bg="#f6f8fa",
    tag_border="#d0d7de",
    tag_text="#656d76",
)


@dataclass(frozen=True)
class Dot:
    x: float
    y: float
    mark: bool
    phase: float  # 0..1 along the diagonal; drives stagger and shimmer
    fade: float  # 1 at the centre, 0 at the field's edge
    start_dx: float  # scattered start position, relative to home
    start_dy: float


def seeded_random(seed: int) -> Callable[[], float]:
    """Same LCG as dot-field.tsx, so the scatter matches the site."""
    state = seed

    def next_value() -> float:
        nonlocal state
        state = (state * 1664525 + 1013904223) % 4294967296
        return state / 4294967296

    return next_value


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = min(1.0, max(0.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def load_mask() -> list[str]:
    rows = (SCRIPTS / "ah-monogram.txt").read_text(encoding="utf-8").split()
    return [row for row in rows if row and set(row) <= {".", "#"}]


def is_mark(mask: list[str], row: int, column: int) -> bool:
    """A sampled cell is a stroke if most of its block is."""
    if row < 0 or column < 0:
        return False
    hits = 0
    for dy in range(MASK_STEP):
        for dx in range(MASK_STEP):
            r, c = row * MASK_STEP + dy, column * MASK_STEP + dx
            if r < len(mask) and c < len(mask[r]) and mask[r][c] == "#":
                hits += 1
    return hits * 2 >= MASK_STEP * MASK_STEP


def build_field() -> tuple[list[Dot], float]:
    mask = load_mask()
    columns = math.ceil(len(mask[0]) / MASK_STEP)
    rows = math.ceil(len(mask) / MASK_STEP)
    spacing = min(FIELD_W * MASK_FILL / columns, HEIGHT * MASK_FILL / rows)
    origin_x = FIELD_X + (FIELD_W - (columns - 1) * spacing) / 2
    origin_y = (HEIGHT - (rows - 1) * spacing) / 2
    centre_x, centre_y = FIELD_X + FIELD_W / 2, HEIGHT / 2
    radius = math.hypot(FIELD_W / 2, HEIGHT / 2)
    scatter = seeded_random(SCATTER_SEED)

    dots: list[Dot] = []
    for row in range(-math.ceil(origin_y / spacing), math.ceil((HEIGHT - origin_y) / spacing) + 1):
        for column in range(
            -math.ceil((origin_x - FIELD_X) / spacing),
            math.ceil((FIELD_X + FIELD_W - origin_x) / spacing) + 1,
        ):
            x = origin_x + column * spacing
            y = origin_y + row * spacing
            mark = is_mark(mask, row, column)
            distance = math.hypot(x - centre_x, y - centre_y)
            fade = 1.0 if mark else 1 - smoothstep(0.35, 0.98, distance / radius)
            if not mark and fade <= 0.02:
                continue
            angle = scatter() * math.pi * 2
            reach = (0.35 + scatter() * 0.75) * radius
            dots.append(
                Dot(
                    x=x,
                    y=y,
                    mark=mark,
                    phase=(column + row) / (columns + rows),
                    fade=fade,
                    start_dx=centre_x + math.cos(angle) * reach - x,
                    start_dy=centre_y + math.sin(angle) * reach - y,
                )
            )
    return dots, spacing


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def field_svg(p: Palette) -> str:
    dots, spacing = build_field()
    mark_r = fmt(spacing * 0.32)
    grid_r = fmt(max(0.8, spacing * 0.09))

    # Grid: grouped by quantised alpha so each group is one fill, as on the site.
    grid: dict[int, list[str]] = defaultdict(list)
    for d in dots:
        if d.mark:
            continue
        level = min(GRID_ALPHA_BUCKETS - 1, round(d.fade * 0.16 * (GRID_ALPHA_BUCKETS - 1)))
        if level:
            grid[level].append(f'<circle cx="{fmt(d.x)}" cy="{fmt(d.y)}" r="{grid_r}"/>')

    # Mark: grouped by diagonal phase so one group-level animation draws the
    # shimmer wave, while each dot carries its own assembly offset and delay.
    marks: dict[int, list[str]] = defaultdict(list)
    for d in dots:
        if not d.mark:
            continue
        bucket = min(SHIMMER_BUCKETS - 1, max(0, int(d.phase * SHIMMER_BUCKETS)))
        delay = START_DELAY_S + max(0.0, d.phase) * STAGGER_S
        marks[bucket].append(
            f'<circle cx="{fmt(d.x)}" cy="{fmt(d.y)}" r="{mark_r}" '
            f'style="--x:{fmt(d.start_dx)}px;--y:{fmt(d.start_dy)}px;animation-delay:{fmt(delay)}s"/>'
        )

    out = ['<g class="grid">']
    for level in sorted(grid):
        alpha = fmt(level / (GRID_ALPHA_BUCKETS - 1))
        out.append(f'<g fill="{p.title}" fill-opacity="{alpha}">{"".join(grid[level])}</g>')
    out.append("</g>")
    out.append(f'<g class="mark" fill="{ACCENT}">')
    for bucket in sorted(marks):
        # The site's shimmer is sin(wave - phase * 9): later phases lag behind.
        lag = (bucket + 0.5) / SHIMMER_BUCKETS * 9 / (2 * math.pi) * SHIMMER_PERIOD_S
        delay = lag % SHIMMER_PERIOD_S - SHIMMER_PERIOD_S  # negative: start mid-wave
        out.append(f'<g class="shimmer" style="animation-delay:{fmt(delay)}s">{"".join(marks[bucket])}</g>')
    out.append("</g>")
    return "\n    ".join(out)


def tags_svg(p: Palette, y: int) -> str:
    out: list[str] = []
    x = float(LEFT)
    for tag in TAGS:
        w = round(len(tag) * MONO_ADVANCE_11PX + 20, 1)
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="24" rx="12" '
            f'fill="{p.tag_bg}" stroke="{p.tag_border}"/>'
            f'<text class="mono" x="{round(x + w / 2, 1)}" y="{y + 16}" font-size="11" '
            f'text-anchor="middle" fill="{p.tag_text}">{tag}</text>'
        )
        x = round(x + w + 8, 1)
    return "\n    ".join(out)


def render(p: Palette) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" fill="none" role="img" aria-labelledby="title">
  <title id="title">{NAME} — {ROLE}</title>
  <defs>
    <clipPath id="card"><rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="8"/></clipPath>
    <style>
      .mono {{ font-family: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace; }}
      .sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif; }}

      @keyframes fadein   {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
      @keyframes appear   {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
      @keyframes pulse    {{ 0%, 100% {{ opacity: 0.35; }} 50% {{ opacity: 1; }} }}
      @keyframes grow     {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
      @keyframes assemble {{
        from {{ transform: translate(var(--x), var(--y)); opacity: 0; }}
        25%  {{ opacity: 1; }}
        to   {{ transform: translate(0, 0); opacity: 1; }}
      }}
      @keyframes shimmer  {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.72; }} }}

      .f1 {{ animation: fadein .6s ease-out .15s both; }}
      .f2 {{ animation: fadein .6s ease-out .40s both; }}
      .f3 {{ animation: fadein .6s ease-out .65s both; }}
      .f4 {{ animation: fadein .6s ease-out .90s both; }}
      .bar {{ transform-origin: 0 0; animation: grow .9s cubic-bezier(.2,.8,.2,1) both; }}
      .dot {{ animation: pulse 2.4s ease-in-out infinite; }}
      .grid {{ animation: appear 1.2s ease-out .2s both; }}
      .mark circle {{ animation: assemble {ASSEMBLY_S}s cubic-bezier(.16,1,.3,1) both; }}
      .shimmer {{ animation: shimmer {fmt(SHIMMER_PERIOD_S)}s ease-in-out infinite; }}

      @media (prefers-reduced-motion: reduce) {{
        * {{ animation: none !important; }}
      }}
    </style>
  </defs>

  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="8" fill="{p.bg}" stroke="{p.border}"/>
  <rect class="bar" x="0" y="0" width="140" height="3" rx="1.5" fill="{ACCENT}"/>

  <g class="f1">
    <circle class="dot" cx="{LEFT + 4}" cy="38" r="4" fill="{ACCENT}"/>
    <text class="mono" x="{LEFT + 16}" y="42" font-size="11" letter-spacing="1" fill="{p.dim}">{STATUS}</text>
  </g>

  <text class="sans f2" x="{LEFT - 2}" y="98" font-size="46" font-weight="700" letter-spacing="-1.2" fill="{p.title}">{NAME}</text>
  <text class="sans f3" x="{LEFT}" y="128" font-size="17" font-weight="600" fill="{p.title}">{ROLE}</text>
  <text class="sans f3" x="{LEFT}" y="151" font-size="14" fill="{p.subtitle}">{PITCH}</text>

  <g class="f4">
    {tags_svg(p, 170)}
  </g>

  <g clip-path="url(#card)">
    {field_svg(p)}
  </g>
</svg>
"""


def main() -> None:
    assets = SCRIPTS.parent / "assets"
    assets.mkdir(exist_ok=True)
    for name, palette in (("dark", DARK), ("light", LIGHT)):
        target = assets / f"header-{name}.svg"
        target.write_text(render(palette), encoding="utf-8")
        print(f"wrote {target.relative_to(assets.parent)} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
