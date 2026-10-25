# Install the source download with your AI agent

The GitHub release ZIP and Nexus download contain source and documentation only:
**no DLL, EXE, game files, saves, master indexes or personal project state**.
Extract outside the game's Data folder. This is a development toolkit, not a
Vortex install. Python 3.12+, GECK and an MCP client are required for editor work.

## Windows editor setup

From the extracted `bridge` directory:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item projects/example-windows.json projects/my-mod.windows.json
```

Have your agent edit the copied profile: set your actual game path, plugin/spec,
helper path and project state directory. Preserve existing project state when
upgrading. Then build the helper from this download, even if an older Git checkout
already contains `Probe.Mcp.exe`:

```powershell
.venv\Scripts\python.exe build_helper.py --project projects/my-mod.windows.json
```

This uses Windows' .NET Framework 4 C# compiler to create the local 32-bit helper.
Stop your old MCP server first so its helper is not locked. Preserve the old
installation while upgrading. Register this installation's `run_mcp.py` with
`--project` and the absolute copied profile path in your MCP client, then restart
the client. Expect bridge version 0.4.0 and **44 tools**. Begin with read-only
status/capabilities; do not discard unsaved GECK work. See
[bridge setup](../bridge/README.md#setup) for indexing and full client examples.

## Optional in-game console companion

Editor work needs no companion DLL. Console execution and typed inventory reads
require a DLL built locally for your installed project plugin. Supported live
configuration: native Windows, Steam FNV 1.4.0.525, xNVSE 6.4.9+ 6.x and a locally
provided [Zig 0.14.1](https://ziglang.org/download/0.14.1/) compiler. The tools do
not download a compiler or install xNVSE for you.

With the project plugin installed, ask your agent to hash that file and use:

1. `geck_console_setup(mode="preflight", expected_plugin_hash=HASH, request_key=KEY)`.
2. `mode="build"`, a new key and `zig=ABSOLUTE_ZIG_EXE`. Keep its returned build receipt.
3. Quit FNV normally. Use `mode="install"`, a new key and that `build_receipt`.
   Owned previous files are backed up; unresolved commands block installation.
4. Launch through xNVSE, load a disposable save, leave gameplay unpaused and
   require `geck_console_readiness` to report `ready` before commands.

Changing the anchor plugin requires a guarded rebuild/install/restart. Other
loaded plugins use explicit plugin/local_form/sha256 bindings without another DLL.
Keep `target.started` as a decimal string. Retain each operation ID, poll status,
and never retry an uncertain command automatically. A `coc` also needs explicit
authorization and a matching originating CELL binding. Verify interior/exterior
classification first: exact-cell proof does not establish collision-safe landing.
See the complete [console workflow](../bridge/docs/CONSOLE-COMMANDS.md).

The separate optional read-only quest telemetry companion has its own
[build/setup instructions](../bridge/docs/AUTOMATIC-RUNTIME.md).

## Prompt to give your agent

> Set up this source-only GECK MCP download using docs/SOURCE-SETUP.md. Keep my
> mod sources, profiles, state and game files. Create a profile copy for this
> installation, install the locked Python dependencies, compile the GECK helper
> locally and help register/restart my MCP client. Verify version 0.4.0 and 44
> bridge tools. Start with read-only checks. Explain the optional xNVSE console
> companion before building or installing it, and coordinate a normal game exit.
> Do not save over valued saves or replay uncertain operations.

## Beta limits

Windows editor and disposable in-game workflows have live evidence. Inventory,
66-percent condition, single interior teleport, context changes and replay guards
passed. Large-script/reference/branch workloads and controlled minimized or
disconnected Shadow sessions still need further live validation. Linux/Proton,
GECK Extender and non-English GECK are not claimed tested. See [testing](TESTING.md).
