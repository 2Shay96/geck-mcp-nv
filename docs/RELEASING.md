# 0.3.0 upgrade and download checks

0.3.0 brings vanilla batch diagnostics and optional automatic xNVSE quest
diagnostics into the existing `geck` server (31 tools). There is no second MCP
server to register for runtime diagnostics. The experimental `windows/` server
is still a separate, optional port; its own package version remains 0.1.0.dev0.
Version 0.3.0 is published on [Nexus](https://www.nexusmods.com/newvegas/mods/99851?tab=files)
and [GitHub](https://github.com/2Shay96/geck-mcp-nv/releases/tag/v0.3.0).
GitHub main receives development updates before the next packaged Nexus release.

## Upgrade from 0.2.1

1. Keep your project profiles, specs, local state, backups and game files.
   Extract the new download into its own folder, then point your project profile's
   `helper` and the client's Python/server paths at the new installation.
   Keep the existing `state_dir` and game paths when upgrading the same project.
2. Follow [bridge setup](../bridge/README.md#setup): create a Python 3.12+
   environment, install `bridge/requirements.lock.txt`, and build `Probe.Mcp.exe`
   with `build_helper.py --project YOUR_PROFILE`. Source downloads contain no
   executables. The helper needs the .NET Framework 4 C# compiler on Windows.
3. Restart the MCP client so it loads the new server. Ask for version 0.3.0 and
   31 tools. `geck_status` can check the editor without changing it.
4. Use [vanilla diagnostics](../bridge/docs/MCP-QUICKSTART.md#runtime-diagnostics-29-bridge-tools)
   without any extender. Automatic readings are optional: follow
   [the companion instructions](../bridge/docs/AUTOMATIC-RUNTIME.md) to build a
   project-specific DLL with Zig 0.14.1 and install it while the game is closed.
   Launch native Steam FNV 1.4.0.525 through xNVSE 6.4.9 or newer 6.x.
   An installed extender alone is not proof that it is running.

No mod, companion DLL, game data, logs, saves or master index is bundled.
Missing/stale output remains an error; it never becomes a passing zero.

## Reproduce a source-only archive

From a Git checkout, with Python 3.12+ and Git:

```powershell
py -3.12 tools/package_release.py --revision YOUR_CHECKED_COMMIT --output ..\GECK-MCP-for-New-Vegas-0.3.0.zip
```

The script reads committed Git objects, ignoring working edits and untracked
files. It checks the bridge version markers, exports only source/documentation,
and writes a deterministic ZIP plus a SHA256/source-commit JSON manifest.
Existing output files are refused. Local coordination documents, executables,
game-derived fixture files and their five dependent test modules are omitted.
The Git checkout retains the complete regression suite; the download retains
synthetic runtime, service, protocol and other fixture-independent tests.

Before publication, extract into a fresh folder, check ZIP paths/CRC/hash, build
the extracted helper, run the extracted tests and exercise a fresh stdio client.
Run the generated DLL fake-host tests on Windows with `GECK_MCP_ZIG` set to the
absolute Zig path. Keep acceptance evidence outside the archive. Record test
counts separately for the checkout and the smaller download suite.

Preparing a ZIP or merging code does not publish a Nexus update. A version tag,
GitHub release and Nexus upload each require the owner's approval.
