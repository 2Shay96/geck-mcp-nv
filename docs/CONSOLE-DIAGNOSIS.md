# Fix 7: game console form resolution

6 October 2026. Investigation in progress; no cause or implementation fix confirmed.

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

## Next runtime checks

1. 2Shay launches the current mod and loads the usual test save. Click the existing Salvatore actor in the console and record its full reference ID. If it begins with FF, it is a dynamic reference and does not identify the mod index.
2. With verified runtime prefix XX, test `sqv XX00080F` and record the exact result. Also test `sqv SalvatoreGanacciQuest`. Avoid changing quest state during this first check.
3. If current failure reproduces, close FNV, preserve the exact installed plugin under public gitignored diagnostic state, and record its hash. Prepare a GECK-saved comparison with the same records/scripts; check backup provenance and differences first. Explain the specific test build before installation.
4. Test that copy on the same clean save and runtime load index. Do not save over the player's original save. Restore the preserved current plugin when FNV is closed and verify its hash.
5. If GECK copy succeeds while bridge copy fails, isolate the necessary byte difference and add a regression test before changing writer behavior. If both fail, investigate runtime loading/console behavior instead of changing plugin bytes speculatively.

The first runtime question is pending. No plugin swap has occurred.

## References

[GECK scripting tutorial](https://geckwiki.com/index.php/Scripting_for_Beginners) describes the leading FormID byte as the load-order position. [StartQuest](https://geckwiki.com/index.php?title=StartQuest) documents the quest argument. The game's displayed reference ID and command results remain the acceptance evidence.
