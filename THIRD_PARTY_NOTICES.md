# Third-party notices

## GECK MCP (Fallout 3), by maksimka2432fr23 (MIT)
- Source: https://github.com/maksimka2432fr23/codex-skill-mcp-fallout3 (commit `b3c1044a`, 2026-09-06)
- Used in: `windows/` (ported to Fallout: New Vegas; changes listed in `windows/PORT-NOTES.md`)
- Licence: MIT, full text in `windows/LICENSE`

## Python dependencies (installed by pip, not bundled)
- MCP Python SDK (MIT), pydantic (MIT), Pillow (MIT-CMU), NumPy (BSD-3-Clause): `bridge/`
- MCP Python SDK, pywinauto (BSD-3-Clause), psutil (BSD-3-Clause), Pillow: `windows/`
- Optional: PyFFI (BSD-3-Clause) for `bridge/sprite_flipbook.py`

## Not included
- No Bethesda files: no GECK, no `.esm`/`.esp`/`.bsa` game data and no data derived from them.
  Each user builds the master index and record templates from their own copy of the game.
- Fallout, Fallout: New Vegas and G.E.C.K. are trademarks of Bethesda Softworks / ZeniMax Media.
