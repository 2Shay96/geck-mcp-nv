# Fix 7: game console form resolution

6 October 2026. Fix 7 resolved: the historical console commands used the wrong runtime load index.
2Shay verified main-quest lookup and the original summon command using corrected IDs. No plugin writer change was necessary.

## Evidence

The current installed plugin and workshop build are identical SHA-256 `6e3375186e2f46894e8d5eae45519e0292a62908592316e844d82cbb74349cde`. Public `build_plugin.py --project <workshop>/projects/salvatore_mod.windows.json --dry-run` reproduces that hash and passes validation. Windows bridge suite: 168 tests, 3 skips; ESP verifier: 6 tests passed.

Every inspected backup and current build contains these records in the QUST top group (group type 0), with identical EDIDs and record headers (flags 0, form version 15):

| Local ID | EditorID | Role |
|---|---|---|
| 00080F | SalvatoreGanacciQuest | Main quest |
| 000818 | SalvatoreGanacciCmdSummon | Summon command quest |
| 000819 | SalvatoreGanacciCmdFar | Far command quest |
| 00081A | SalvatoreGanacciCmdReset | Reset command quest |

File-local FormIDs have prefix 01 because the plugin has one master, FalloutNV.esm. This alone does not prove its runtime load index. The local `plugins.txt` currently lists FalloutNV.esm and SalvatoreGanacci.esp. Runtime confirmation is still required.

GECK-saved backup `17222cef2e1dc9cb1dfd7ff7d81a5f01776202394bf113b22749d993943e856f` versus current Build C:

- Same four quest records and their EDIDs; command quest DATA fields unchanged.
- Main quest DATA first byte: GECK 0x11, bridge 0x01.
- TES4 HEDR next-object-ID: GECK 0xB0F, bridge 0x832; record/group count unchanged at 47.
- Other changes: creature ACBS, AIDT, NIFZ, SPLO order, weapon DNAM. Differences are not proof of a console lookup failure.

Older GECK-saved backup `5a3f7fbf...` versus bridge backup `382f249d...` shows the same broad differences. Runner job 042 records compile, GECK save, compiled-script caching, then bridge rebuild to `382f249d...`. Backup filenames were checked against file content hashes.

Commands run from public `bridge`: `tools/esp_diff.py <saved-backup> <bridge-build>`, plus read-only iteration with `geck_mcp.esp.codec.iter_records`. Private workshop sources and game installation were not modified.

## Runtime result

2Shay reported Salvatore's clicked in-game reference as `0A000813`. The matching plugin reference is `01000813`, so
the actual runtime index is 0A, not the historical assumption of 01. With the existing installed bridge-built plugin,
2Shay confirmed that `sqv 0A00080F` shows the quest variables. This demonstrates that its main quest is loaded and
resolves through the game console. No plugin swap or byte change was needed.

2Shay also confirmed that `startquest 0A000818` summons Salvatore without the original “Invalid info” error. Far and reset IDs would be
`0A000819` and `0A00081A` for this running load order. These prefixes are not portable to other load orders.

## Original diagnostic plan

1. 2Shay launches the current mod and loads the usual test save. Click the existing Salvatore actor in the console and record its full reference ID. If it begins with FF, it is a dynamic reference and does not identify the mod index.
2. With verified runtime prefix XX, test `sqv XX00080F` and record the exact result. Also test `sqv SalvatoreGanacciQuest`. Avoid changing quest state during this first check.
3. If current failure reproduces, close FNV, preserve the exact installed plugin under public gitignored diagnostic state, and record its hash. Prepare a GECK-saved comparison with the same records/scripts; check backup provenance and differences first. Explain the specific test build before installation.
4. Test that copy on the same clean save and runtime load index. Do not save over the player's original save. Restore the preserved current plugin when FNV is closed and verify its hash.
5. If GECK copy succeeds while bridge copy fails, isolate the necessary byte difference and add a regression test before changing writer behavior. If both fail, investigate runtime loading/console behavior instead of changing plugin bytes speculatively.

Steps 1–2 established the wrong load-index assumption and successful main-quest lookup; the corrected summon command
also passed. Steps 3–5 were unnecessary. No plugin swap occurred. Far/reset commands and vanilla EditorID lookup
were not retested; the result establishes resolution of the two originally reported numeric-ID failures.

## References

[GECK scripting tutorial](https://geckwiki.com/index.php/Scripting_for_Beginners) describes the leading FormID byte as the load-order position. [StartQuest](https://geckwiki.com/index.php?title=StartQuest) documents the quest argument. The game's displayed reference ID and command results remain the acceptance evidence.
