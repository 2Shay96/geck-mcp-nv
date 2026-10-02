# Milestone 1: fast bridge (persistent worker), 2026-09-29

> Development log from the original macOS/CrossOver build. Paths under `evidence/` refer to the author's private test records and are not shipped.

Author: Claude (Cowork). Live-verified inside the Steam bottle against the running
GECK (no plugin loaded). The macOS-side Python -> `wine` stdio path is tested
with a fake worker only. **Codex must run the checks at the bottom.**

## What changed

- `Probe.cs` has a new `serve` mode. It is one long-lived helper process that reads one JSON
  request per line on stdin and writes one JSON response per line on stdout.
  - Request: `{"id":..,"args":["status"],"env":{"GECK_BRIDGE_SESSION":..}}`.
    Each request carries its full `GECK_BRIDGE_*` env. Serve mode never falls back to
    the process env, so a stale session guard cannot leak between requests.
  - `{"id":..,"batch":[{"args":[..]},..],"stopOnError":true}` runs up to 16 steps in
    one round trip. Control ops: `ping`, `invalidate`, `shutdown`.
  - Caches, each validated before reuse:
    - GECK PID: start time is re-checked every request; a full process scan runs every 5 s.
    - GECK exe path: `Process.MainModule` costs ~100-120 ms under Wine and was the
      real cost of `status`.
    - Menu command IDs.
    - Window inventory: reused only for read-only ops (`status`, `filter.set`,
      `category.select`, `objects.find`, `object.select`, `cell.find`, `data.state`,
      `plugin.inspect`, `menus.resources`). Reuse also requires an identical
      top-level window fingerprint (handle, visibility, enabled state, class, title)
      and every cached handle to pass `IsWindow`. Any other op, or any failure,
      invalidates the cache.
  - Every result now carries a `worker` object (discovery cached/full, per-phase ms).
    `status` also carries `timingMs`.
  - One-shot mode is unchanged apart from these extra fields. `J()` now escapes
    non-ASCII characters so the protocol is pure ASCII.
- `geck_mcp/worker.py`:
  - `PersistentTransport` has the same `call()` contract as `Transport`, plus `batch()`.
  - `AutoTransport` (the default) uses the worker when the handshake (hello +
    ping) succeeds, and otherwise falls back to one-shot launches. No editor op is
    ever dispatched during the handshake.
  - Timeouts, and worker death after a request is delivered, raise `OUTCOME_UNKNOWN`
    (uncertain), kill the worker, and are never replayed. A request is retried on a
    fresh worker only if it was provably never delivered.
- `config.py` adds `transport: auto|persistent|oneshot` (default `auto`).
  `GECK_MCP_TRANSPORT=oneshot` forces the legacy path.
- `service.py`:
  - `select()` (category -> filter -> find) is one batch round trip, journaled as one step.
  - `call_batch` refuses mutating ops.
  - `geck_status` data includes `bridgeTransport`.
  - The server closes the worker on exit.
- `Probe.Mcp.exe` is rebuilt from this `Probe.cs`. The previous binary is at
  `evidence/Probe.Mcp.before-worker.exe` and the previous source at
  `evidence/Probe.before-worker.cs`.
- New tools, which run inside the bottle through CrossOver > Run Command, so no shell is needed:
  - `tools/CompileCheck.exe <src> <out.exe> <report.txt>` compiles with CodeDom and writes diagnostics to a file.
  - `tools/WorkerHarness.exe <helper> <requests.jsonl> <report.txt> [n]` compares one-shot
    and persistent runs over stdin/stdout, with timeouts.
- Tests: `tests/test_worker.py` (17 tests, using fake worker `tests/fake_worker.py`).
  42 service+worker tests pass under Python 3.11. `test_protocol.py` was not run
  because the `mcp` package was unavailable to Claude.

## Live results (evidence/worker-harness-4.txt; GECK idle, no plugin)

| operation | one-shot, in-bottle process | persistent worker |
|---|---|---|
| status | 1117-1482 ms | first 384 ms, then **2-4 ms** (cached) |
| objects.find, 58 rows | - | 35-87 ms |
| batch status+objects.find | - | 36 ms, one round trip |
| worker start (hello) | - | 733 ms, once |

Also verified live:
- Stale session rejected in 2 ms.
- MCP-disabled `object.place` refused.
- `invalidate` forces a full rediscovery.
- Malformed JSON gets `PROTOCOL_ERROR`.
- Clean `shutdown`, exit 0.

One-shot timings exclude the macOS -> `wine` launcher overhead, which the real MCP path pays on top.

## Not verified yet (Codex, please run on macOS)

```sh
cd work/geck-bridge
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v      # expect all pass, incl. test_protocol
.venv/bin/python bench_bridge.py --project projects/salvatore.json --repeat 5
```

`bench_bridge.py` is read-only (`status`, `objects.find`). It proves stdin reaches the
worker through CrossOver's `wine --cx-app` wrapper, and records one-shot vs
persistent timings from Python in `evidence/bench-*.json`. If `workerError` is
`WORKER_UNSUPPORTED`, the wrapper is not forwarding stdin. `AutoTransport` then
falls back to one-shot safely. Report the error rather than working around it.

After that, restart the registered `geck` MCP server (restart the Codex app) and
confirm `geck_status` shows `bridgeTransport.mode == "persistent"`. Then run the
existing `mcp_live_smoke.py --edit-fixture` on the fixture plugin to exercise the
mutation path through the worker.

## Not done in M1

- Worker lifetime: the worker lives for the MCP server's lifetime. There is no idle timeout.
- `serve --input/--output` file mode exists but was not verified live.
- The stray CrossOver launch attempt left `_to_delete/runner-unused/`. It is inert; delete it.
