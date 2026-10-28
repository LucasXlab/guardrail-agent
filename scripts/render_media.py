"""Faithfully render local CLI/API recording; all demonstration data is synthetic.

Authoring dependency: Pillow. No generated terminal text, model or network calls.
PNG wrapping and GIF readability holds are presentation changes, not CLI output.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

INK = "#10151e"
PANEL = "#1b2933"
PAPER = "#edf3ee"
MUTED = "#b1bfd0"
BLUE = "#63d9b1"
AMBER = "#efc382"
RED = "#f0aaa2"


def face(size, *, mono=False, cjk=False):
    if cjk:
        options = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    elif mono:
        options = [
            "/System/Library/Fonts/Menlo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
    else:
        options = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in options:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install a listed system font; do not silently render unreadable glyphs")


def mixed_wrap(text, width=1144, size=21):
    mono, cjk = face(size, mono=True), face(size, cjk=True)
    result = []
    for original in text.expandtabs(4).splitlines():
        line, pixels = "", 0.0
        for char in original:
            font = cjk if ord(char) > 127 else mono
            amount = font.getlength(char)
            if pixels + amount > width:
                result.append(line)
                line, pixels = "", 0.0
            line += char
            pixels += amount
        result.append(line)
    return result


def mixed_draw(draw, xy, text, fill, size=21):
    x, y = xy
    mono, cjk = face(size, mono=True), face(size, cjk=True)
    for char in text:
        font = cjk if ord(char) > 127 else mono
        draw.text((x, y), char, font=font, fill=fill)
        x += font.getlength(char)


def terminal(title, text, height=None):
    lines = mixed_wrap(text)
    natural = 184 + len(lines) * 27
    height = height or max(440, natural)
    if natural > height:
        raise ValueError(f"Excerpt does not fit: {title}")
    image = Image.new("RGB", (1280, height), INK)
    draw = ImageDraw.Draw(image)
    draw.text((44, 25), "guardrail-agent", font=face(27, mono=True), fill=BLUE)
    draw.text((44, 73), title, font=face(25), fill=PAPER)
    draw.text((747, 33), "ACTUAL RUN  /  SYNTHETIC DATA", font=face(16, mono=True), fill=MUTED)
    draw.rounded_rectangle((26, 117, 1254, height - 38), radius=14, fill=PANEL)
    for index, line in enumerate(lines):
        fill = BLUE if line.startswith("$ ") else PAPER
        if '"ok": false' in line or "oversize_gate_approved: false" in line:
            fill = RED
        elif "execution_quote:" in line or "actual_fill:" in line or "cash_after:" in line:
            fill = AMBER
        elif line.startswith(("[JSON", "[showcase", "[exit ")):
            fill = MUTED
        mixed_draw(draw, (48, 136 + index * 27), line, fill)
    draw.text(
        (44, height - 27),
        "Actual CLI / labelled public API output; full results: showcase-raw.json",
        font=face(15),
        fill=MUTED,
    )
    return image


def social():
    canvas = Image.new("RGB", (1280, 640), INK)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((60, 55, 144, 139), radius=18, fill=PANEL)
    draw.line((83, 75, 83, 119), fill=BLUE, width=6)
    draw.line((121, 75, 121, 119), fill=BLUE, width=6)
    draw.line((91, 97, 113, 97), fill=AMBER, width=4)
    draw.text((172, 61), "guardrail-agent", font=face(58), fill=PAPER)
    draw.text((63, 185), "Trace a proposal.", font=face(51), fill=PAPER)
    draw.text((63, 249), "Question its receipt.", font=face(51), fill=BLUE)
    draw.text((65, 341), "Deterministic gates and simulated execution", font=face(27), fill=PAPER)
    draw.text(
        (65, 386), "Fixed synthetic data. No real trades or models.", font=face(23), fill=MUTED
    )
    for x, y, title, detail in [
        (794, 200, "01  PROPOSE", "Synthetic intent"),
        (1013, 200, "02  GATE", "Rules / state"),
        (794, 342, "03  EXECUTE", "Fees + slippage"),
        (1013, 342, "04  VERIFY", "Trusted receipt"),
    ]:
        draw.rounded_rectangle((x, y, x + 204, y + 120), radius=14, fill=PANEL)
        draw.text((x + 15, y + 22), title, font=face(18, mono=True), fill=BLUE)
        draw.text((x + 15, y + 67), detail, font=face(18), fill=PAPER)
    draw.text(
        (65, 516), "PYTHON 3.11+  /  MIT  /  SOURCE v0.1.0", font=face(19, mono=True), fill=MUTED
    )
    draw.text(
        (65, 560), "A teaching simulation, not investment research.", font=face(22), fill=AMBER
    )
    draw.text((794, 515), "Receipt trust is external.", font=face(22), fill=PAPER)
    draw.text((794, 562), "SCHEMATIC / NOT A CLI SCREENSHOT", font=face(15, mono=True), fill=MUTED)
    return canvas


def badge(label, value):
    left, right = 20 + 7 * len(label), 20 + 7 * len(value)
    label, value = html.escape(label), html.escape(value)
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{left + right}" height="24" role="img" aria-label="{label}: {value}"><rect width="{left + right}" height="24" rx="5" fill="#263a43"/><path d="M{left} 0h{right - 5}q5 0 5 5v14q0 5-5 5h-{right - 5}z" fill="#365d58"/><g fill="#edf3ee" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11" text-anchor="middle"><text x="{left / 2}" y="16">{label}</text><text x="{left + right / 2}" y="16">{value}</text></g></svg>\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cast", type=Path, default=Path("assets/demo.cast"))
    parser.add_argument("--out", type=Path, default=Path("assets"))
    args = parser.parse_args()
    events = [json.loads(row) for row in args.cast.read_text().splitlines()]
    transcript = "".join(row[2] for row in events[1:] if row[1] == "o").replace("\r\n", "\n")
    if "\x1b" in transcript or "\r" in transcript:
        raise ValueError("Unexpected controls: record again without altering cast output")
    if re.search(r"/(?:Users|home|private|tmp)/", transcript, re.I):
        raise ValueError("Recording contains a private machine path")
    sections = {}
    for chunk in re.split(r"(?m)^=== CASE: ", transcript)[1:]:
        name, text = chunk.split(" ===\n", 1)
        sections[name] = text.strip() + "\n"
    titles = {
        "simulation": "Seeded proposals: accepted and rejected",
        "costs": "Actual simulated fill, fee and cash change",
        "receipt": "An intact audit matches its trusted reference",
        "tamper": "A deleted record fails against the original receipt",
    }
    assert set(sections) == set(titles), "Expected four real scenarios"
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "terminal.txt").write_text(transcript)
    for name, title in titles.items():
        terminal(title, sections[name]).save(out / f"feature-{name}.png", optimize=True)
        (out / f"feature-{name}.txt").write_text(sections[name])
    chosen = list(titles)
    height = max(900, *(184 + len(mixed_wrap(sections[name])) * 27 for name in chosen))
    frames = [terminal(titles[name], sections[name], height=height) for name in chosen]
    holds = [3200, 4200, 3000, 3600]
    frames[0].save(
        out / "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=holds,
        loop=0,
        disposal=2,
        optimize=False,
    )
    social().save(out / "social-preview.png", optimize=True)
    for name, pair in {
        "ci": ("CI", "prepared"),
        "license": ("license", "MIT"),
        "version": ("source", "v0.1.0"),
        "python": ("Python", "3.11+"),
        "stars": ("stars", "pending"),
    }.items():
        (out / f"badge-{name}.svg").write_text(badge(*pair))

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "schema": "guardrail-media-v1",
        "source_version": "0.1.0",
        "cast_sha256": digest(args.cast),
        "cast_events": len(events) - 1,
        "showcase_script_sha256": digest(Path("scripts/showcase.py")),
        "renderer_script_sha256": digest(Path(__file__)),
        "raw_results_sha256": digest(args.cast.parent / "showcase-raw.json"),
        "rendering": "Complete recorded stdout; CRLF -> LF and visual wrapping only. Costs section is explicitly labelled actual public Python API output; other sections are installed CLI calls.",
        "gif": {
            "cases": chosen,
            "frame_holds_ms": holds,
            "timing": "readability holds, not original execution timing",
        },
        "social_preview": "Original native schematic, not runtime screenshot",
        "html_capture": "feature-report.png is a browser viewport of actual synthetic-report.html; complete HTML retained",
        "assets": {},
    }
    for path in sorted(out.glob("*")):
        if path.name.startswith("readme-"):
            continue
        if path.suffix in {".png", ".gif"}:
            with Image.open(path) as image:
                manifest["assets"][path.name] = {
                    "width": image.width,
                    "height": image.height,
                    "frames": getattr(image, "n_frames", 1),
                    "sha256": digest(path),
                }
    (out / "recording.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
