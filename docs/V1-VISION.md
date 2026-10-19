# GECK MCP v1.0 vision

Recorded 19 October 2026 at the owner's request. This is a future product
direction for agents to reference, not a claim that these capabilities exist
today or authorization to start controlling the game.

## The intended experience

Describe a mod, build it, compile it, test it in the GECK and game, diagnose a
failure, fix it and repeat the same test. v1.0 should make that loop dependable
on Windows with a small amount of user setup and useful evidence at every step.

## Starting point: 0.3.0

The existing bridge exposes 31 tools. It builds plugins, compiles through the
GECK, performs guarded editor operations and offers shared CLI/MCP diagnostics.
Vanilla diagnostics use user-run console batches. The optional generated xNVSE
companion reads quest variables automatically on the validated native Windows
Steam runtime. In-game acceptance covered both diagnostics modes.

Automatic gameplay control and live game vision are future work. Existing
telemetry is a measurement foundation; it does not move the player. Retain its
freshness, process/build identity and truthful missing-output checks.

## Proposed v1.0 finish line

- **Easy setup:** one supported Windows installation path, dependency/path
  detection, project configuration, a useful doctor command and clear upgrades.
  Optional capabilities report their actual runtime availability. A fresh
  machine can follow the packaged instructions without a developer's local state.
- **Dependable editor work:** build, compile, install, load, inspect, verify and
  save with backups, readable failures and tested recovery. Shared CLI/MCP core
  and fresh-server tests keep both interfaces consistent.
- **Reusable runtime tests:** named saves/checkpoints, declarative expectations,
  comparisons and structured reports. Broaden measurements where supported
  (for example position, health and inventory), with explicit adapter coverage.
- **Controlled playtesting:** an explicitly enabled test mode can enter a known
  room/save, perform a short scenario and collect visual and numeric evidence.
  First deliver one reliable room test, then expand the supported scenarios.
- **Useful delivery:** a tested download, concise Windows instructions, clear
  support limits and a report an agent can use to reproduce and fix a failure.

## A playtest loop with vision

Keep three capabilities distinct and report which are available:

1. **Vision:** capture fresh images of the game window so an agent can examine
   the scene, objects, menus, visible clipping and other visual problems. Bind
   captures to the current game process and test step. Do not assume every MCP
   client can consume images.
2. **Bounded controls:** actions such as holding forward for a specified duration,
   turning, jumping or activating. Build this as an opt-in gameplay adapter;
   retain the existing companion's read-only purpose. Specify a duration/step
   limit, cancellation, input release on failure, and focus/modal handling.
   Never send input to an unrelated window or another agent's game session.
3. **Measurements:** use runtime telemetry for exact assertions where possible.
   Resolve runtime IDs from evidence, verify the running extender and plugin
   build, and reject stale/missing observations. Visual confidence and numeric
   assertions are separate results; an unavailable check stays unavailable.

A runner should execute a declared sequence, collect timestamps/screenshots and
measurements, then return pass/fail/unavailable for each check with provenance.
It must stop cleanly on a crash, lost game identity or unsafe control state.
Keep raw captures, player logs and saves in local ignored evidence directories.

## First demonstrator: the toy-car room

Use a disposable fixture project and known test save, with its starting state
recorded. Enter the garage, activate the cart, drive between two markers, stop
and reset. Check travel/arrival, expected speed, moving fuel consumption, zero
parked fuel consumption, and visible cart alignment. Use another observation
after movement has settled; same-frame readback is insufficient.

Seed a known fault, show that the test fails for the expected reason, fix it,
then rerun the same scenario successfully. Exercise failure cases too: missing
telemetry, wrong plugin build, xNVSE not running, lost focus and cancellation.
The acceptance report must distinguish user observations, vision assessments,
numeric assertions and unsupported checks. This is the first practical target
for autonomous room playtesting; broader gameplay coverage needs its own tests.

## v1.0 release presentation: explicit owner requirements

When v1.0 actually meets its acceptance criteria and publication is approved:

- **Remove the prototype/WIP warning from the Nexus page.** Audit the title,
  short description, full description, banner imagery and download notes so an
  old warning is not left behind. Remove equivalent prototype claims from
  current release documentation when the validated support level warrants it.
- **Present v1.0 as Windows-focused. Remove Linux/Proton and Mac/CrossOver
  references from the Nexus presentation and current user-facing setup/support
  material.** The owner requested this future presentation change. Preserve
  historical validation records, attribution and licence obligations; retiring
  platform code is a separate implementation decision.
- Keep a prominent GitHub source link and explain that GitHub receives newer
  development versions before packaged Nexus updates.
- Update version markers, release notes, download links and requirements to
  match the tested v1.0 package. Test the extracted download and the complete
  build/compile/playtest/fix loop before tagging or uploading it.

Do not apply the v1.0 presentation changes to 0.3.0. Its prototype warning and
documented limitations still describe the released software. Do not remove
specific unresolved limitations simply to make the release sound finished.

## Instruction for the next agent

Read the workspace rules, HANDOFF.md, MCPworkflow.md and newest STATUS.md first.
Treat this document as the agreed direction for future planning. Propose the
smallest concrete milestone toward the room-test demonstrator when asked to
continue v1.0 work; establish supported capture/control mechanisms before
promising live game vision. Implementation, game control and future release
publication must follow the user's active authorization and project safeguards.
