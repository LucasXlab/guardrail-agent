# Real demonstration media

All simulation, CLI and Python API examples use synthetic data. They are educational control-flow and accounting examples, not strategy backtests, real orders, financial returns or authentication claims. The code was developed with AI assistance.

## Provenance

- `demo.cast` is an unmodified local asciicast v2 from `scripts/showcase.py`. The helper uses temporary HOME/XDG/asciinema configuration, an explicit local filename and no upload command.
- `showcase-raw.json` retains complete stdout/stderr, the command, expected exit and actual exit for each call. Three sections are actual installed CLI calls; `costs` is explicitly labelled output of actual public Python API calls from `scripts/showcase.py --costs`.
- Displayed commands use `guardrail-agent` and `python` as readable aliases. The helper actually invokes its installed environment's `sys.executable -m guardrail_agent`; the API example invokes the same interpreter with the absolute path to `scripts/showcase.py --costs`. These command-path substitutions are presentation only. Raw stdout/stderr are unchanged, and no JSON fields are projected or omitted. Relative audit/report filenames are used in a disposable working directory; no private machine path appears in recorded output.
- `synthetic-audit.json`, `synthetic-receipt.json`, `synthetic-truncated.json` and `synthetic-report.html` are actual generated artifacts. The truncated audit is a copied document with its last record removed. Keep a trusted receipt independently in real use; these bundled public fixtures are for reproduction, not a trustworthy custody service.
- `terminal.txt` normalizes recorded CRLF to LF. The feature terminal PNGs faithfully render complete recorded sections with visual line wrapping; they do not invent or project JSON fields. Full raw stdout/stderr remain available separately.
- `demo.gif` contains all four recorded sections held for 3.2, 4.2, 3.0 and 3.6 seconds. These are readability holds, not execution timing. The original cast retains its real timestamps.
- `feature-report.png` is a 1200×980 top browser viewport of the unmodified generated HTML report, with all external requests blocked. It crops the viewport only; open `synthetic-report.html` for the entire report.
- `logo.svg`, badges and `social-preview.png` are native illustrations. The social image is a schematic, not a running CLI screenshot. `readme-*` files have their separate source explanation in `../docs/readme-demo.md`.
- `recording.json` binds cast, raw output, authoring scripts and raster assets by SHA-256 and records dimensions/frames.

## Reproduce

Install the source checkout first. For optional authoring, install `asciinema` and `Pillow` into the development environment; neither is a runtime dependency. These commands replace only this showcase's named assets, leaving `readme-*` intact:

```sh
.venv/bin/python -m pip install asciinema Pillow
PATH="$PWD/.venv/bin:$PATH" sh scripts/record_showcase.sh
.venv/bin/python scripts/render_media.py
```

The recorder defaults to `.venv/bin/python`; `GUARDRAIL_PYTHON` and `ASCIINEMA` may select another installed environment. The renderer uses listed Menlo/Arial/Arial Unicode or DejaVu/Noto CJK system fonts and fails rather than silently losing glyphs.

For the optional report capture, separately install Node.js, Playwright and its Chromium browser, then run `node scripts/capture_report.cjs` from this checkout. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` may select an existing browser. Run the renderer afterwards to add that screenshot's hash to the manifest. Browser authoring dependencies are separate from this standard-library simulator.

Source version is `0.1.0`. CI is prepared and Stars are pending; the local badges do not claim remote CI success, a registry release or a Star count. A supplied receipt is assumed trusted, not signed or authenticated by this program. Rewriting an audit and its reference together cannot establish authenticity.
