# Terminal progress implementation (maintainers only)

This page is excluded from consumer skill references. It records implementation
knowledge for setup UI; it grants no scan, target-build or release authority.

## Ownership and lifecycle

The interactive renderer reserves exactly two rows once, rests at column one of
the second row, moves up one row, erases and paints both rows on every frame.
Row one is labelled Overall setup for completed setup milestones, Downloading
for a known byte count, or size unknown for an indeterminate transfer.
Row two contains the rotating ASCII spinner, operation and actual stage.
Received byte counts precede the filename so narrow terminals retain useful data.
Stages/paths are clipped conservatively by display cells, with terminal controls
removed. Complex emoji may be clipped early; no external runtime width library
is required. Keep one spare column to prevent autowrap at the right edge.

A heartbeat changes spinner/time only. A lock serializes stage/transfer updates
and heartbeat draws. Close stops the worker, clears both rows, restores the
cursor and Windows console mode, then the caller prints a durable outcome.
Python suspend clears the region before any future confirmation prompt.
Bootstraps currently have no interactive prompts. Add suspension if that changes.

Python direct setup and generated POSIX bootstrap embed the same stdlib renderer.
PowerShell embeds a .NET renderer: its timer never invokes PowerShell from a
thread-pool thread, only the synchronized .NET display. It enables VT on stderr
when supported and restores the prior console mode. No elevation is requested.
Unsupported/redirected terminals receive at most 24 stage lines and an outcome.

## Source and generation

Authoritative templates are scripts/install.ps1 and scripts/install.sh.
tools/build_installer.py generates install/update variants with the corresponding
operation label. There are no independently maintained update templates.
The Python renderer is tools/install_progress.py; Windows uses
tools/bootstrap_progress.cs. A build expands the renderer marker before emitting
any script. Do not execute templates directly or edit generated assets.

The six generated artifacts are the verified bundle ZIP, its checksum, and all
four scripts. Bootstraps verify SHA256 and reject unsafe archive paths before
starting the trusted installer. Wheel installation remains offline in a private
venv, with the old launcher retained until the new CLI verifies.

The child uses --progress json, never a second console renderer. The established
JSON-lines fields remain type, percent, stage and elapsed; completion carries
state and errors carry stage/message. Shell consumers bound record sizes and
validate numeric percentages/stage strings; unexpected child failure is nonzero.
No scan/CI result envelope or analyzer output is changed.

## Verification and reusable checks

Install test dependencies pyte==0.8.2 and, on Windows, pywinpty==3.1.0.
The latter explicitly selects ConPTY, not WSL or a mocked Write-Progress sink.
Set DEVSIFT_TEST_TERMINAL_ARTIFACTS to an output folder to retain raw .ansi and
decoded .frames.json captures. Set DEVSIFT_TEST_INSTALLER_BUNDLE to an actual
generated ZIP for end-to-end wheel/skills tests in disposable homes.

Run the full unittest suite, plus test_install_progress.py,
test_windows_bootstrap.py, test_posix_bootstrap.py and test_installer_assets.py.
The installer-assets CI matrix uses native Windows, Linux and macOS runners.
Inspect each platform's actual job outcome before claiming it passed.

Check decoded screen state, cursor position/visibility and scroll history for
every completed repaint. Animation must keep exactly two active rows and add
no scrollback. Test 40, 48, 80 and 120 columns; known/unknown transfer, terminal
resize, checksum rejection, truncated transfer, malformed child events and child
failure; direct Python, JSON and redirected output; install and generated update.
Keep raw captures and screen assertions together: counting escape bytes alone
does not establish visual correctness. Durable summaries may wrap normally.

## Rollback

Before a release, rollback is a reviewed revert of the source change and a fresh
asset build; do not patch assets individually. CLI/plugin version remains
unchanged until separately authorized release preparation. After a published
update, keep the previous working environment and use the trusted installer
matching the intended version; do not point a launcher at an unverified wheel.
Marketplace plugins are updated/uninstalled through their host independently.
