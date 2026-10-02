# Actor photos (`geck_actor_photo`)

`photo_cli.py "Sunny Smiles"` or the MCP tool `geck_actor_photo(subject="Sunny Smiles")`.
Output: `photos/<EditorID>-<time>.png` (full Render Window, 2880x1444 on this Mac) and
`photos/<EditorID>-<time>-cutout.png` (RGBA, subject only).

Verified live 2026-09-30: Sunny Smiles in 19-27 s with the studio already loaded; first load of
FalloutNV.esm + studio about 70 s. The earlier manual attempt took 15 minutes.

## What it does
1. Resolves the subject by EditorID or display name in the FalloutNV.esm index (NPC_ or CREA; DLC actors
   are not supported because the loader only loads FalloutNV.esm).
2. Writes `state/photo/GeckPhotoStudio.spec.json` and builds `GeckPhotoStudio.esp`: one interior cell
   `GeckPhotoStudio`, neutral lighting, the subject at the origin rotated 180 degrees. It is a separate
   throwaway plugin (project id `photo-studio`); your plugins are never touched or saved.
   Building it offline avoids GECK's "quest object" warning you get when dragging quest NPCs.
3. Installs and loads it with FalloutNV.esm only (refuses if GECK has unsaved edits). A load returns
   `stage: "loading"`; call again with the same subject until `stage: "done"` (the CLI loops for you).
4. Frames the subject via Cell View (`cell.show`), maximises the Render Window, tilts the camera level
   (`pitch`, default -60), deselects, picks the brighter lighting mode, then auto-fits zoom and centre by
   measuring real captures, and captures the window by CGWindowID. The cut-out keys out the background
   colour (estimated from the borders) plus GECK's reddish glow halo, fills tiny holes (eye glints) and
   removes the grey colour from the soft edge.

Options: `pitch` (Shift+drag px; positive looks down), `rotation` (degrees; 180 faces the camera),
`fill` (target height fraction; whole wheel ticks decide the final size), `lighting` (`auto`/`keep`/`toggle`).

## GECK Render Window facts learned (CrossOver, this Mac)
- **Posted window messages** work for: mouse wheel zoom (`WM_MOUSEWHEEL`), keys such as `A` (toggles
  between the dark cell-lit view and the bright editor light), window size/maximise, list-view clicks.
- **Posted mouse moves do nothing for the camera** (orbit with `MK_SHIFT`, pan with `MK_MBUTTON`).
  Real input inside the bottle works: Wine `SendInput` for Shift + `mouse_event` relative moves (orbit),
  or middle button + moves (pan). This briefly moves the macOS cursor; it is not macOS keyboard input.
- `SetForegroundWindow` returns false when another macOS app is frontmost; the Wine input still arrives.
- Double-clicking a cell in Cell View loads it into the Render Window; with actors this blocks GECK for
  longer than the helper's 500 ms send timeout, so `cell.show` now posts those clicks.
- The Cell View look-at camera comes from a **fixed world direction**, slightly above: rotating the subject
  180 degrees shows the front. It targets the reference origin (feet). Shift+drag -60 px around the selected
  subject levels the camera with the feet; vertical pan then raises it (no re-tilt).
- Wheel zoom is a **dolly**: a tick changes size more the closer the camera gets. Auto-fit models it and
  never zooms in more than one tick past a clean measurement.
- The Render Window cannot be taller than the screen (722 client px here), so a standing figure tops out
  around 1000-1250 px tall in the capture.
- `screencapture -l` includes the 28 pt macOS title bar and transparent rounded corners; both are handled.
- The selection box (red/green/blue lines) must be cleared before measuring or capturing: a real click in
  an empty corner deselects.
- FaceGen head textures can appear a moment after the body; the pipeline waits and redraws.

## Troubleshooting
- `UNSAVED_CHANGES`: save or discard in GECK yourself (see SESSION-START.md).
- `EDITOR_NOT_READY`: GECK is starting or busy; call again.
- `FRAMING_FAILED`: evidence includes the last measurements; captures are in `state/photo/work/`.
- `CAPTURE_FAILED`: grant Screen Recording to the app hosting the server (Terminal, Codex or Claude).
