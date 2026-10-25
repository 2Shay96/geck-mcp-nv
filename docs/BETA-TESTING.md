# v0.4.0 local beta feedback

This candidate is unpublished. Keep existing project source, state, backups and
accepted game artifacts. Use a profile copy to point at the extracted beta helper;
do not replace a running helper or assume package version identifies native code.

Start a fresh MCP server from the extracted run_mcp.py. geck_status.components
reports Python PID, executable, source root and startup source SHA256s, whether
those files have changed on disk, and the configured helper path/hash.
bridgeTransport.helperIdentity reports the actual worker PID, loaded executable
path/SHA256 and pointer size from its native startup handshake. Older helpers may
lack this proof: do not infer that they are current. Restart the client safely.
Tool discovery now contains 44; console DLL build identity is separately verified by
geck_console_readiness. Telemetry-only installations do not execute commands.

## Compile and load feedback

- Save title stars are advisory after durable Save intent. Checkpoint close uses
  EDID/full-source SHA256, plugin mutation, enabled state and normal Exit. Prompts
  remain visible; persisted source/bytecode/layout/reference proof is mandatory.
- Hidden retained script HWNDs are closed, including preparation, review and
  normal editor shutdown. Visible or unreadable dialogs remain blockers.
- NPC_ is accepted through the existing generic template/explicit-field writer;
  this does not add a high-level NPC schema or relax saved-record validation.
- Only engine PlayerRef 00000014 under first master FalloutNV.esm receives the
  explicit index exception. Other missing/remapped references still fail.
- Compression flag 00040000 is representation. Decoded fields, semantic flags,
  missing records/overrides and assets remain compared and protected.
- Semantic differences return exact subrecord bytes/flags and an exact
  roundtripReviewToken. Review is optional and must name that current token plus
  a review note: geck_compile_resume(reviewed_roundtrip=TOKEN, review_note=NOTE),
  or compile_scripts.py --operation-id ID --reviewed-roundtrip TOKEN --review-note NOTE.
  This explicitly retains the verified canonical SAVED plugin, releases ownership,
  and never installs the losing rebuild. It does not rewrite/adopt the spec;
  encode reviewed fields in the spec before any future rebuild. Missing overrides
  cannot be waived. No review can bypass source/bytecode/artifact/asset validation.
- live_load.py accepts --operation-id ID to resume polling, without redispatch.
  List-shaped transient evidence is not treated as a nested load result.
- A load reserves the editor across clients/profiles until completion/review.
  External plugin/session changes and bounded expiry require review; never start
  a second load because the first client disappeared. Original receipts survive.

Test two consecutive scripts (including player), an intentional syntax error,
client restart/resume and clean close. Record operation IDs, exact component
hashes, source lengths, phase, modal text/owner/control IDs and saved proof.
Keep actual compile errors distinct from failed input or source truncation.

## Runtime

Mapping, command execution and log collection are separate capabilities.
Console input requires explicit opt-in setup; see ../bridge/docs/CONSOLE-COMMANDS.md.
Configured-plugin GetModIndex has typed numeric result and live process/build/
context evidence. Generic console text is not captured by the actuator.
Use runtime_prepare/collect for quoted SCOF paths and fresh incremental log
checkpoints. Those collectors do not execute their batch automatically. Restart
or reconnect does not authorize truncating/replaying logs or commands.
xNVSE diagnostic tooling is optional and does not make it a mod dependency.

Beta feedback is required before publication. GECK large-source, reference/branch
variants and controlled Shadow foreground/minimized/disconnect gates remain
separate; successful beta smoke tests do not imply release approval.


24 October console v2: use decimal-string started unchanged; upgrade the old
companion once through geck_console_setup. Named plugin bindings resolve live
without per-plugin DLLs. Explicit coc and typed inventory/equipped condition
readback passed a disposable live smoke test; full rules and limitations are in
bridge/docs/CONSOLE-COMMANDS.md. Earlier 42-tool beta remains historical.

25 October feedback: real inventory/condition/replay checks passed; vanilla
TheFortCaesarTents coc failed before dispatch when its GetInCell expression
would not compile. Manual arrival is not an MCP pass. The correction requires a
destination CELL binding, verifies its type/EditorID/origin on disk, and compares
exact player parent-cell identity natively. See current STATUS.md for offline
checks and deployment state; do not assume the previous DLL contains this fix.
