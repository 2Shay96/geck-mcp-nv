# Manual Nexus API publishing

The `Nexus release` GitHub Actions workflow has two explicit modes: `check`
(default, authenticated reads only) and `publish` (uploads an existing checked
GitHub release ZIP). Pushes, tags and GitHub releases do not trigger uploads.
The workflow runs only from main and serializes dispatches.

## One-time setup

1. On Nexus, open https://www.nexusmods.com/settings/api-keys to generate a personal API key.
   Handle this yourself: do not paste the key into chat, a source file or a log.
2. In GitHub repository `2Shay96/geck-mcp-nv`, Settings → Secrets and variables →
   Actions → New repository secret, name it `NEXUSMODS_API_KEY` and paste its value
   directly into GitHub. The agent can verify the secret name exists, not its value.
3. Once this workflow is reviewed and merged into main, open Actions → Nexus
   release → Run workflow → mode `check`. Leave publishing inputs empty.
   Successful reads prove the key can access the API targets; only a future
   authorized publication can verify write access end to end.

The existing page is `newvegas/mods/99851`. Its Unique Mod ID is `558345848331`
and current logical API File ID is `8079429`, copied from the 0.3.0 file's
Advanced dialog on 19 October 2026. These differ from legacy file ID
`1000183372`. Recheck Advanced if the file chain changes. No extra variables
are needed for the current target.

## Next authorized release

Use `$nexus-release` with the intended version. Follow `RELEASING.md` to build
and check the source-only ZIP, then publish the approved GitHub release asset.
Dispatch mode `publish` with the stable tag, approved SHA256 and prepared file
description. Enable `archive_previous` only when archiving the predecessor is
intended. The action adds a version to the existing file, disables mod-manager
downloads and updates the page version. This workflow does not edit the page
description or add a separate changelog; the skill handles those as needed.

The official Nexus action is pinned to source revision
`98532f7670c27cbecc78fae03fa3e278147827e2`, inspected 19 October 2026. It uses
multipart uploads, bounded state polling and the current file-version endpoint.
Keep step debug logging off; its debug implementation can log request details.
Review a pin update before adopting future API/action changes.

After dispatch, inspect the run summary, then verify public version, size,
manual-only download buttons and scan status. Upload availability does not
prove virus-scan completion. If a run fails after upload starts, inspect the
existing Nexus version/upload state before rerunning: the action does not
provide exactly-once publication or a resume mechanism.

Setup has not been tested until the `check` run passes. A local YAML check
does not authenticate and must not be described as successful API setup.
