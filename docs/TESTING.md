# Console wire-v2 acceptance - 24 October 2026

Fresh MCP setup/readiness and disposable live test passed: anchor0D/probe0E,
item count0/1/0, equipped condition66%, absolute health~99, authorized coc
cell/loading verification and new runtime context/epoch. Same key returned prior
receipt; old target refused without a new inbox. Exact decimal-string process
identity preserved. Normal exit and activation/file restoration completed.
Existing workshop game/companion files were preserved. See current STATUS.md
for exact final tests/package hashes; earlier 42-tool beta evidence is historical.

# 24 October 2026 - local beta feedback checks

Unpublished working tree; beta feedback precedes GitHub approval.
- Live disposable nine-script dependency compile completed, rebuilt and installed
  with full saved-script proof; no manual Save/Exit/Next intervention.
- Live two-script fixture including PlayerRef compiled consecutively and completed.
- Intentional bad source retained Save Current Script prompt; bytecode stayed zero.
  Owner explicitly discarded that test and exited; reviewed release completed.
  This test did not display a separate compiler-error dialog.
- Private report artifact read-only comparison: compression-only NPC flag delta
  now passes; zero semantic differences/missing records. Private artifact unchanged.
- Hidden script HWND/native source guards, load ownership/context/deadline,
  canonical diff review, PlayerRef narrow exception and CLI transient parsing
  have offline regression coverage. See current STATUS.md for final counts/paths.
- Broader 32/64 KiB shapes, large reference/branch workloads and controlled Shadow
  foreground/minimized/disconnect trials remain open; no unattended guarantee.

[Beta setup and review semantics](BETA-TESTING.md).

# 0.4.0 candidate acceptance - 23 October 2026

Current candidate is unpublished and **not release-ready**. Offline evidence is
local under bridge/evidence/v040-*. Do not read historical live passes below as
acceptance of this implementation.

| Check | Current evidence |
| --- | --- |
| Fresh baseline | 201 bridge tests, 4 skipped; 6 ESP tests passed |
| Expanded bridge suite | 246 tests, 3 skipped, passed with existing Zig 0.14.1; post-live startup fix: 15 console tests passed |
| ESP regression | 6 passed |
| Windows-port CI procedure | Existing windows/.venv: pip install -e ., then 23 tests passed |
| Native helper | Actual Probe.cs in synthetic Win32 host: measured ANSI RichEdit readback through 131000 characters, root restore, known prompt/hash guard; no GECK compiler-size claim |
| Fresh stdio MCP / CLI | Same durable checkpoint returned; discovery reports 42 tools (including four opt-in console tools) |
| Frozen writer | HEAD versus current writer, identical frozen synthetic spec/source/FormID map: b9da443f908ebd7c1de6cd15de98c02837da2da50367887db60d87932faa8e56 |
| Disposable acceptance inputs | Six offline-valid fixtures, nine dependent scripts each: basic, near 32/64 KiB comments, flat/long branching and 256 references |
| Native GECK/game/Shadow conditions | Not run for this candidate; shared-session coordination required |
| Download extraction | Local candidate source toolkit smoke results recorded in STATUS.md after packaging |

Fixture generator (creates inputs only): tools/create_reliability_fixture.py.
Prepared local inputs: bridge/state/v040-acceptance-20261022/. All use the new
HelloReliability.esp disposable plugin. Sources, bytecode fixtures and master
records in public tests are synthetic; no private mod data is exported.

## Console scope added 23 October

The separate console DLL is tested against an actual compiled synthetic xNVSE
host. A separate real FNV/xNVSE smoke test also passed on 23 October: numeric
GetModIndex=11, quest stopped/start/stop readback=0/1/0, stale identity refusal
and original-key replay without re-execution. Activation restored after normal
exit; test DLL/plugin archived. Broader GECK/Shadow gates remain pending.
Coverage includes identity/expiry/changed-plugin rejection,
API rejection, GetModIndex typed readback, delayed quest effect proof, duplicate
suppression and context change during verification. Python checks cover shared
reservation, restart idempotency, archival recovery, install ownership/backups
and release only after normal game exit. See STATUS.md for final test counts.

Real FNV gate: coordinate explicit opt-in console setup with the owner; preserve
existing DLL/plugin/activation state. With a disposable plugin/save, verify real
GetModIndex and an initially stopped quest becoming running on a later loop.
Check stale target refusal, timeout/status without replay, then restore test files.
Do not infer this pass from the fake host or earlier telemetry evidence.

## Consolidated owner-coordinated live checklist

1. Confirm GECK/game are available for disposable testing; finish/close ongoing
   FNV normally. Back up any existing Data/HelloReliability.esp and any companion
   files before changes. Record original files/hashes and restore afterward.
2. Build/install/load the fixed nine-script fixture, compile via start/status/resume,
   save each checkpoint, validate all full SCTX/SCHR/SCDA/FormIDs/types/references/
   variable layouts, then verify rebuild/install record and asset receipts.
   Use a fresh MCP server and CLI; retain independent plugin-load/compile outcomes.
3. Repeat fixed input fixtures near 32/64 KiB and reference/branch variants. Record
   actual source sizes/shape and native compiler errors separately from truncated
   readback, selection delay and incomplete save. No 64 KiB limit is established.
4. Exercise timeout/resume, known/wrong/unknown dialogs, failed close, late failure,
   retained checkpoints, hidden-root restoration and stale-install save refusal.
   Preserve unknown work/prompts; never force-kill an arbitrary editor session.
5. Repeat the same workload with Shadow foregrounded and tabbed away. Separately
   test minimized and owner disconnect/reconnect, keeping scripts/build/launch
   state fixed. Timestamp repeated trials and record both Windows operation and
   requesting-client survival; unavailable conditions remain recoverable/unverified.
6. Optional companion setup requires explicit owner request: preview exact paths/
   backups with preflight, use checked local Zig, install only with FNV closed,
   restart through xNVSE, advance a disposable save and verify fresh telemetry/
   current prefix. Reject old process/build/save-context mappings and unsupported
   mixed probes. Restore original test files afterward. Vanilla manual diagnostics
   remain available, and no console-input capability exists.

Use PASS/FAIL/UNAVAILABLE per item with timestamped receipts. A screenshot or a
successful input API return cannot establish accepted input. Complete these gates
before calling 0.4.0 release-ready. Commit/push/merge/publication require owner approval.

Record layout reference used for independent semantic validation:
[xEdit FNV record definitions](https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/Core/wbDefinitionsFNV.pas)
(SCHR, SLSD/SCVR, QUST DATA). No xEdit implementation source was copied.

---

# Testing log

## 19 October 2026 - generalized companion live acceptance

The public generated companion passed in-game acceptance, with the project-specific
precursor DLL archived before launch. A fresh main stdio server exposed 31 tools;
geck_runtime_snapshot and geck_runtime_compare plus the shared CLI verified actual
process/module/profile/build identity and a game-resolved runtime index. All four
configured rules passed: initialized quest, driving active, zero speed error and
zero idle fuel waste. Speed was 250; fuel stayed 99.87500762939453 over two seconds.
A fresh stopped-state MCP/CLI check confirmed speed 100, SpeedDelta/SpeedApplied
zero, and a comparison against the driving baseline returned Driving -1 and speed
-150. A wrong expected build hash returned a structured error with no observations.

The local acceptance harness initially required a full tank of exactly 100, which
was stricter than the gameplay requirement: moving to the panel consumed some fuel.
The captured idle delta was already zero. Corrected the local harness to require
positive fuel and zero idle consumption, retained the first capture, and reran
MCP/CLI acceptance successfully. No public runtime code or test expectations were
weakened, and no extra game commands or screen control were used.


## 18 October 2026 - optional automatic xNVSE diagnostics

- Bridge: 197 tests ran, 193 passed / 4 skipped (three existing platform skips and
  optional native compilation). ESP verifier: 6 passed; Windows-port: 23 passed.
- Separate Windows native suite with GECK_MCP_ZIG: all 8 companion tests passed,
  including compilation and execution of the generated 32-bit DLL in six fake-host
  modes, plus load failure/epoch/exit and bounded compile-cache checks.
- Fresh stdio main-server discovery exposes 31 tools. Both new tools report
  structured unavailable errors without a configured/loaded companion. Portable
  service tests cover positive reads, rule failures/pass, deltas, malformed/stale
  data, process/load/build mismatch and guarded installation/backup/rebinding.
- The project-specific precursor passed live CLI/fresh stdio MCP diagnostics and
  source-fix regression on Windows/xNVSE 6.4.9: speed 60 -> 250, idle fuel drain
  1.5 per 1.5 seconds -> zero over two seconds. The generalized public adapter has
  native fake-host coverage, not a separate in-game acceptance pass. No game assets,
  saves, raw logs or local profiles are included. See bridge/docs/AUTOMATIC-RUNTIME.md.

## 18 October 2026 - runtime diagnostics (offline)

- Bridge suite: 189 tests, 186 passed / 3 skipped; 20 new synthetic runtime tests.
- Fresh stdio MCP process exercises all four runtime tools; CLI and MCP reports match.
- ESP verifier: 6 passed. Windows-port regression: 23 passed.
- Incremental parser tested at every byte boundary, including split CRLF; command
  echoes, wrong forms, missing values, partial/locked/rewritten logs, query errors,
  ambiguous checkpoints and unverified identity cannot become a passing assertion.
- Checked idempotency, declarative pass/fail/inconclusive rules, checkpoint deltas,
  safe helper archival, and independence from editor locks and operation context.
- Old HEAD and feature builders produced identical Salvatore bytes on the same current
  private inputs (SHA-256 c4cb440371c544389a7b15ecf818dc156f96dd5eca46e5d22e0fd0e6c3e54b63).
  Workshop inputs changed during the earlier before/after check; no writer change.
- Local acceptance launcher passed a synthetic end-to-end harness test; actual game
  results are listed separately below. No runtime Wine/CrossOver/extender support is claimed.
- Known existing test noise: intentional negative protocol error traces and worker
  ResourceWarnings; neither failed these offline suites.


## 18 October 2026 - runtime Windows vanilla acceptance

- User supplied fresh console inventory identity for an ordinary vanilla item. A
  complete baseline count 3 and a separately executed post-drop count 2 produced
  delta -1, with exact command/form binding and raw source-line provenance.
- Intentionally querying the inventory item as a quest produced the expected invalid
  quest error: capture=errored, missing observation, assertions=inconclusive. No false
  zero or pass. Missing output from an earlier mistyped batch also stayed awaiting_output.
- Live compiler output exposed a CR CR LF parsing bug. Fixed LF record boundaries,
  added a synthetic repeated-CR compiler-error fixture and every-byte replay check,
  then replayed the unchanged log after preserving the pre-fix manifest. No previous
  accepted checkpoint was rewritten and no extra game action was needed for the fix.
- Shortened new batch names for manual entry. Closed bridge collection without claiming
  logger shutdown; user then confirmed normal FNV exit. Archived all six unchanged
  owned batches across the active/unused sessions, preserving logs and evidence locally.
- Valid quest-variable and persistent-reference probes remain offline tested only.
  Live acceptance used the same Service core; fresh stdio MCP/CLI parity was tested
  offline. No GECK attachment, screen control, plugin/save edits or workshop edits.


What has been run, where, and what happened. Newest first.

## 2026-10-06: final live native MCP acceptance, bridge 0.2.1

Shadow Windows PC, vanilla Steam GECK, native launcher, public main `3d9dcf4` at test start. No bridge code changed
in this session. Used the registered Codex `geck-hello` tools for HelloWasteland and a fresh stdio MCP client for an
isolated throwaway `HelloAcceptanceFinal.esp` (one STAT and one object script from the existing HelloPreview fixture).

| Check | Result | Evidence |
| --- | --- | --- |
| Status, validate, build, install, attach through MCP | pass | Clean GECK; HelloWasteland build/installed SHA `23650eea...`; all three editor panes visible/reachable |
| Initial HelloWasteland load | pass | `loaded_verified`, 14/14 references; explicit `editor_session` accepted |
| Forced HelloWasteland reload | pass | `reload=true` completed as `loaded_verified`; 14/14 references still match |
| Cell framing and render captures | pass | Frames `light.red` and `barrel.left`; nonblank 455x169 PrintWindow PNGs. 2Shay confirmed the view was perfect, correcting an accidental negative answer |
| Fresh stdio MCP discovery / test-plugin load | pass | 25 tools; isolated plugin built/installed, loaded and attached with its configured STAT identity |
| Script compiler CLI, without `--skip-load` | pass | Automatically recognised `already_loaded`; HelloPreviewScript actually compiled with no errors, saved, cached, rebuilt and installed; no uncompiled scripts remain; exit 0 |
| Compiled test-plugin reload / attach | pass | Forced MCP reload returned `loaded_verified` |
| Preview open / close through MCP | pass | HelloPreviewTile preview opened and closed; lifecycle/identity checked, preview image not separately visually assessed |
| Guarded whole-plugin MCP save / persisted validation | pass | `save_entire_active_plugin=true` with expected hash/model; `saved_verified`, then persisted STAT/model validation passed |
| Clean GECK restart / new session | pass | PID changed 19108 → 21476; HelloWasteland loaded and verified again with 14/14 refs |
| Post-restart render capture | pass after uncovering | Initial `CAPTURE_BLANK` safely refused because Cell View covered Render Window. Existing guarded helper `render.steps` max/redraw brought it forward: nonblank 1280x777 PrintWindow. After restoring normal layout, nonblank 910x338 screen capture at 200% DPI |
| Cleanup / preserved mod | pass | No unresolved Hello operations; GECK left clean on HelloWasteland. SalvatoreGanacci.esp and game plugins.txt SHA-256 unchanged. New throwaway ESP moved out of Data into ignored evidence, not deleted |

Raw evidence: `bridge/state/acceptance/final-20261006-codex/` (ignored): `final-direct-mcp.json`,
`preview-mcp.jsonl`, `render-layout.json`, `cleanup.json`, `protected-files.json`, test profile/spec/script and saved
test ESP. Captures are under ignored `bridge/photos/render-20261006-*.png`.

Not repeated: deliberate crash mid-load (prior acceptance already covered it), GECK Extender, Wine/Proton or macOS.
The compiler is a supported CLI, not an MCP compilation tool. The fresh stdio test covers preview/save; those steps
were not performed using the HelloWasteland connector because its profile deliberately has no configured STAT records.

## 2026-10-06: Codex bridge takeover and console diagnosis

Fix 9 follow-up: public suite **169 tests passed, 3 skipped**, ESP verifier **6 passed**; isolated workshop migration
suite **13 passed**. Static Havok collision is checked by NIF readback and deterministic CLI output. Full non-install
old/new Salvatore asset builds matched **48/48 files byte-for-byte** at seed 0. Both public/delegated current profile
dry-runs matched `c8fa39d051cfc109405a71ed30206a292ca439f6b0509cda2cfe4d27c26174f0`. A fresh delegated
native GECK status succeeded with isolated state. No writer changes, game writes or new live compilation/load cycle.

Shadow Windows PC; branch `codex/bridge-console-fix`, baseline `fdaf790`.

| Check | Result | Notes |
| --- | --- | --- |
| Bridge unit suite | pass | 168 tests run, 3 skipped |
| ESP verifier suite | pass | 6 tests run |
| Salvatore profile dry-run | pass | Validates and matches installed Build C SHA-256 `6e3375186e2f46894e8d5eae45519e0292a62908592316e844d82cbb74349cde`; no files installed |
| GECK status through Codex MCP | pass | Direct `geck_status`: no unsaved changes, Object Window/Cell View/Render Window visible and reachable |
| Installed plugin inspection through MCP | pass | `geck_plugin_inspect(which="installed")`: generated, installed hash matches build |
| Runtime actor ID | user verified | 2Shay clicked Salvatore: `0A000813`; plugin contains ACRE `01000813` |
| Main quest console lookup | user verified pass | `sqv 0A00080F` shows quest variables using the unchanged bridge-built plugin. Earlier commands used wrong runtime prefix 01 |
| Corrected summon command | user verified pass | `startquest 0A000818` summons Salvatore without “Invalid info” on the unchanged bridge-built plugin |

No GECK edits, plugin swaps, writer changes or new full live acceptance run in this session.

## 2026-10-05: 0.2.0 fixes, Windows 11, native launcher

Same Shadow cloud PC as 3 Oct (display scaled 200%). Branch `bridge-fixes`. Runner jobs `.claude-runner\done\046`-`063`.
Live tests used only throwaway plugins: `HelloWasteland.esp` (profile `projects/hellowasteland.json`) and a local
acceptance plugin `HelloPreview.esp` (one STAT for the preview tools, one 5-line object script for
`compile_scripts.py`; files in `bridge/state/acceptance/`, not shipped). Driver: `bridge/state/acceptance/acceptance.py`.

| Check | Result | Notes |
| --- | --- | --- |
| Fix 3 cause | confirmed | Direct stdio client (job 047): `session_id` reaches the server. Through the Claude desktop device proxy the server received `{}` |
| `bridge` unit tests, Windows | pass | Job 054: 161 run, 9 skipped (6 sprite tests without PyFFI, 2 Wine launcher tests, 1 symlink without privilege). Job 063 with PyFFI installed: 168 run, 3 skipped. Linux without PyFFI: 168 pass, 9 skipped |
| Salvatore regression | pass | Spec at workshop HEAD: sha256 `382f249d…` (byte-identical). Current workshop spec (author field edited, uncommitted): `a5d045c3…` with the old and the new code |
| `build_plugin.py <spec> --dry-run --state <workshop state>` | pass | Job 038 failed here with `no template dump` |
| Helper rebuild (`build_helper.py`) | pass | Old exe kept in `bridge/state/helper-old/` |
| Acceptance round 1 (job 052) | pass, except capture | status → load (`loaded_verified`, 44 s) → cell verify 14/14 with frame → reload (68 s) → cell verify 14/14 → `compile_scripts.py` without `--skip-load` (load, compile, save, cache, rebuild, install; exit 0) → preview open/close → kill GECK mid-load, restart |
| Acceptance round 2 (job 053, after the GECK restart) | pass, except one capture | The first load released the killed load's barrier (`releasedStaleOperations`), then the same steps passed again |
| MCP through the Claude desktop device proxy (server `geck-hello`, HelloWasteland profile) | pass | `geck_status` (3 windows visible, Render Window reachable); `geck_plugin_load` without a session (released the barrier left by the kill test) → `loaded_verified`; reload → `loaded_verified` only after the reload was seen; `geck_cell_verify` with `editor_session` and with none, framing `light.red` / `barrel.left`; `geck_plugin_install`, `geck_plugin_save`, `geck_recovery_acknowledge` with `editor_session` reached the server (install unchanged; save and acknowledge refused by their own guards, as expected for this profile). Proxy check: `editor_session: "999:1"` → `STALE_SESSION` (argument arrives); `session_id: "999:1"` → accepted as if absent (the proxy drops it) |
| Render capture | pass | Jobs 054-056 and MCP: PNGs of the framed cell (floor tiles, barrel, light markers), 455x169 (PrintWindow, = the client size GECK reports) or 910x338 (screen copy at 200% scaling); 4 of 4 non-blank in job 056. Found on the way: a DPI-unaware screen copy took the wrong area (job 052); a covered Render Window gave a picture of the covering window (overlap check added); PrintWindow alternates between the rendered view and the plain grey background (retry with a repaint request added) |
| Sprite tools (job 063, no GECK) | pass | PyFFI 2.2.3 + setuptools 84.0.0 from the lock file; 168 unit tests, 3 skipped (the 6 sprite tests now run). Vanilla `clutter\ashtray\ashtray01.nif` (material 24) as collision template: no option keeps 24, `organic` → 6, `cloth` → 1, read back from the written NIF. Same frames with hash seed 1, 2 or unset → one mesh sha; the workshop script without the re-run gave a different mesh for seeds 1 and 2, and with seed 0 the same bytes as the public one. `creature_skeleton.py --project` (mistergutsy, 40 files, 8 KFs edited): identical bytes for seeds 1 and 2 and to the workshop script. Salvatore esp regression unchanged (`382f249d…` / `a5d045c3…`) |
| Loads without the mouse (jobs 058-061) | pass | Experiment with GECK's Data dialog (then Cancel): posted double-clicks toggle a row with the cursor elsewhere; a sent `WM_NOTIFY NM_DBLCLK` timed out. Helper changed to post-only toggles (verified, up to 3 tries). Job 061: 3 loads (HelloWasteland → HelloPreview → HelloWasteland) all `loaded_verified`, every toggle on the first try, while 2Shay used the mouse (214 distinct cursor positions in 641 samples) |

Not run: Linux/Proton; macOS + CrossOver with this version; `windows/` server; GECK Extender. The new windows-latest
CI job has not run yet (it runs on the first push).

### Found and fixed during these runs
- GECK started by a script had Object Window, Cell View and Render Window all hidden before any load (job 051). A
  posted `WM_NULL` did not bring them back; `ShowWindow` did. Started by hand, they were visible. This matches jobs
  031/041 (hidden after a load).
- A Data list checkbox did not toggle while nobody was at the PC (job 049); the load then left the Data dialog open and a
  barrier. Now the dialog is cancelled and the load fails cleanly (`failed_before_change`).
- Reloading the already-shown plugin was reported `loaded_verified` before GECK started reloading (job 051).

## 2026-10-03: Windows 11, native launcher (first real Windows run)

Machine: Shadow cloud PC, Windows 11 Home 10.0.22621, NVIDIA RTX 2000 Ada. Fallout: New Vegas + vanilla GECK from Steam
(default folder). Python 3.12.10. Profile `bridge/projects/hellowasteland.json` copied from `example-windows.json`
(`"launcher": "native"`). Repo at `ba37349` plus the two helper fixes below.

| Step | Result | Notes |
| --- | --- | --- |
| GECK renders (FalloutNV.esm, exterior cell) | pass | Loads in under a minute; camera responsive |
| `bridge` unit tests | 106 of 133 pass, 6 skipped | 20 failures + 7 errors are test-fixture issues, not tool bugs: fixtures use CrossOver bottle paths (`WRONG_EDITOR`, launcher command asserts with `/`), SQLite files still open at temp cleanup (`WinError 32`), symlinks need a privilege (`WinError 1314`). Known: CI skips windows-latest |
| `test_esp_check.py` | pass (6) | |
| `windows` unit tests | pass (23) | |
| `esm_index.py FalloutNV.esm` | pass | 465,017 records, 70,872 indexed |
| `Probe.Mcp.exe status` | pass | No SmartScreen/Defender prompt (git clone has no download mark) |
| status one-liner | pass | `ok: true`, persistent worker |
| `build_plugin.py examples/hello-wasteland.spec.json` | pass | 18 records, 14 references, validation OK |
| MCP over stdio (`run_mcp.py`) | pass | 24 tools; `geck_status` ok |
| `install_plugin.py` | pass | New `Data\HelloWasteland.esp`, sha256 `23650eea…45a7` |
| `live_load.py --timeout 1500` | **fail, fixed, pass** | See fixes 1 and 2. After the fixes: `loaded_verified` in 66 s |
| `cell_verify.py --cell HelloWasteland --frame light.red` | pass | 14/14 references matched; camera framed. Render Window shows the tiled room, fire and lights |

### Fixes found by this run (in `bridge/Probe.cs`, helper rebuilt with the .NET Framework `csc.exe`)
1. **Data dialog stayed hidden.** On Windows the modal Data dialog opened by the posted menu command was created but
   not shown until GECK received real input, so the load failed with `MODAL_BLOCKED` ("no dialog appeared").
   The helper now shows exactly one hidden `Data` dialog owned by the editor after 500 ms.
2. **Data checkboxes did not toggle.** GECK hit-tests the cursor position of the double-click, so the sent synthetic
   double-click did nothing on Windows, and a sent button-down can block in the list's drag detection until the real
   mouse moves (GECK showed "not responding"; a mouse move freed it, no data changed). On native Windows the helper now
   parks the cursor over the row (no real click), posts the four mouse messages and restores the cursor.
   Under Wine (detected via `ntdll!wine_get_version`) the original sent double-click is unchanged.

Each failed attempt was left as an unresolved operation; after checking that the Data dialog was cancelled and the
editor was clean, the barrier was cleared with `acknowledge` and a note.

### Not run yet
- `windows/` server against the real GECK (`geck_doctor`, `geck_list_windows`, `geck_cell_view_snapshot`)
- A second pass with GECK Extender
- `geck_status` through the Claude desktop and Codex registrations after an app restart
- macOS + CrossOver re-check with the rebuilt helper (the Wine code path is unchanged)

## 2026-10-02/03: macOS + CrossOver
Status, build, install, live load and cell verify (14/14) passed on the author's Mac; see `RELEASE-STATUS.md`
outside the repo for details.
