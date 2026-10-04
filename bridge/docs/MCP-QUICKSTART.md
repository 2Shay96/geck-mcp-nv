# GECK MCP — local static-record prototype

> Actor photos (macOS only for now): [PHOTO.md](PHOTO.md). Persistent helper: [M1-FAST-BRIDGE.md](M1-FAST-BRIDGE.md).

This is a local stdio MCP server for the 32-bit Fallout New Vegas GECK. It was developed under CrossOver on macOS and is tested end to end on Windows 11 (`launcher: native`); the Linux (`launcher: wine`) path is untested. It loads configured plugins with exactly FalloutNV.esm as master and edits configured existing STAT model fields. Record creation, cell placement, animation checks, and gameplay checks remain unsupported.

## Helper transport

By default the server keeps one persistent helper (`Probe.Mcp.exe serve`) and falls back to one Wine launch per call if the handshake fails. Set `"transport": "oneshot"` in the project JSON or `GECK_MCP_TRANSPORT=oneshot` to force the legacy path. `geck_status` reports the active mode under `bridgeTransport`. See [M1-FAST-BRIDGE.md](M1-FAST-BRIDGE.md).

## Start the server

From this directory:

```sh
.venv/bin/python run_mcp.py --project projects/mcp-fixture.json
```

The server communicates over stdin/stdout; it is intended to be launched by an MCP client. Diagnostic output belongs on stderr. No network listener is opened. The server does not load a plugin or edit GECK at startup; it creates/opens its local operation journal.

A generic stdio client configuration uses:

```json
{
  "mcpServers": {
    "geck": {
      "command": "/path/to/bridge/.venv/bin/python",
      "args": [
        "/path/to/bridge/run_mcp.py",
        "--project",
        "/path/to/bridge/projects/hellowasteland.json"
      ]
    }
  }
}
```

On Windows use `.venv\Scripts\python.exe` and Windows paths. After changing the arguments, restart the MCP connection; a running server keeps the profile it loaded at startup.

## Project configuration

Copy a project JSON and set the launcher, plugin, game root, wine/bottle (not needed for `native`), helper and configured STAT identities. Relative paths resolve against the JSON file. Use a shared `state_dir` for all profiles targeting the same bottle so they share recovery barriers as well as the bottle lock. Do not change the project ID or state directory to bypass an unresolved operation.

The `projects/example-*.json` files show one profile per launcher (`crossover`, `wine`, `native`). Copy one to `projects/<project_id>.json` and edit the paths.

Dependencies are pinned in `requirements.lock.txt`; the current environment uses Python 3.12 and MCP SDK 2.2.0. On another installation, create a Python 3.12 virtual environment and install that lock file. Update absolute installation paths in the profiles.

## Normal workflow

1. Obtain `geck_status` and a disk `geck_record_read`. Call `geck_plugin_load` with the session, exact editor title, disk plugin hash, and fresh request key. The editor must be clean. Poll `geck_plugin_load_status` using the returned operation ID until `loaded_verified`; `loading` means only dispatch succeeded. Use `reload: true` only when intentionally reloading an already active plugin.
2. Call `geck_status`, then `geck_project_attach` with the returned `sessionId`.
3. Call `geck_record_read` with `source: disk` for the persisted record and plugin hash, then `source: editor` with the session for the current model field.
4. Call `geck_record_set_model` with the expected old model, expected plugin hash, session and a fresh request key. A successful edit is committed in GECK memory, not yet saved.
5. Open/close the identified preview. Preview existence is not visual verification.
6. Call `geck_plugin_save` with expected models, expected disk hash, session, another request key, and `save_entire_active_plugin: true`. This saves all pending edits in the active plugin.
7. Call `geck_plugin_validate` to independently verify supported disk fields.

Repeated identical mutation requests using the same request key return the original receipt. That receipt describes historical execution, not current editor state. A changed request using the same key is rejected. If a request was interrupted, the replay is an error with `outcome_unknown`; it is never dispatched again automatically.

## Diagnostics and recovery

Use `geck_inspect_windows` for a bounded read-only inventory, including modal text. It is available while the recovery barrier is active. Use `geck_operation_get` or `geck://operations/{operation_id}` for persisted step results and failures.

An unknown operation outcome blocks further editor work. Inspect the editor, disk and operation evidence, resolve any dialogs deliberately, then call `geck_recovery_acknowledge` with the current session/hash and an explanatory review note. Acknowledgment does not roll back or certify the original operation.

The lock coordinates cooperating bridge callers; it cannot prevent manual edits. Existing record dialogs block automated workflows. The bridge checks session, plugin, configured record identity and expected values, but live identity is currently established by the disk FormID plus the exact EditorID in a scoped Static dialog. Full live provenance/load-order verification remains future work.

## Tests

```sh
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s . -p test_esp_check.py -v
```

A live end-to-end smoke test against a disposable fixture plugin exists in the author's development tree but is not shipped in v0.1 (it depends on private test assets).

## Loading and recovery

The MCP helper reads GECK's actual list image indices for selected files and verifies the Active File column before dispatch. This avoids both false checkbox readbacks and toggling an already active file off. Only the rebuilt `Probe.Mcp.exe` is covered; the retained legacy `Probe.exe` is not updated. Rebuild with `.venv/bin/python build_helper.py` after changing C# source.

Pending loads block other editor workflows while status and inspection remain available. After an interrupted load, inspect current editor and disk state before recovery acknowledgment. A load can be acknowledged in a clean empty restarted editor; subsequent polling of an acknowledged load is rejected. Acknowledgment never certifies success.

GECK can take several minutes to load the master in this bottle. Transient control timeouts during loading are not evidence of a missing plugin or a corrupt mesh. Recheck status after loading; do not repeat mutations on timeout.

