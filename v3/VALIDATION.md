# Validation — 2026-10-25

Actual machine: macOS 26.3 (25D2125), ARM64; rustc 1.98.0.
Only this selected repository was changed, on `feat/native-process-rust`.
SDK uses published git revision `9f91afcc071c3f301414dc62b33cfeac7d89a0cf`;
Cargo.lock is regenerated. Entrypoint uses two Tokio worker threads.

Passed locally:

- `cargo fmt --check`.
- `cargo clippy --locked --all-targets -j1 -- -D warnings` (strict, no lint suppressions).
- `cargo test --locked -j 1 -- --test-threads=1`: 15 domain tests and one actual
  stdio executable regression test. All 15 inherited tests are retained.
- `cargo build --release --locked -j 1 --target aarch64-apple-darwin`.
- Real executable identity/protocol/session routing, reverse host RPC, dispose,
  shutdown and EOF. Clipboard/AI/selected-image/tray callbacks, migration, retained tray after disposal, temporary sampler success/cancel, helper termination and blur release.
- Frozen source pack matches `git show fe71ca87f21ac4ff31505010c228f8abda0f2a89`;
  all inherited test names, command IDs/preferences and original icons preserved.
- No app or Tauri Cargo dependency; SDK source is the immutable git dependency.
- Package-owned Swift sampler builds and ad-hoc codesigns as ARM64. Swift source retained; the PowerShell derivative retains the original sampler UI/capture implementation (see SOURCE.json).

Packaging uses actual native release executable bytes, a complete SHA-256 file
inventory and separate computed artifact metadata. Extracted-ZIP process smoke
uses OS-only PATH with a headless fixture host; no source/toolchain is needed by
the executable. See the matching `color-timers-*-package.log` and
`color-timers-*-package-smoke.log` under `/tmp/tezbar-external-rust` for results.

Not run: native Windows build/execution for this port; native CI is supplied but
has not been dispatched by this child. SDK native Windows CI evidence does not
constitute port validation. Live desktop sampler permissions, Finder/Explorer,
clipboard/paste, tray display, actual AI service, notifications and audible
playback are not exercised: fixture host acknowledges their typed RPC and timer
tests use silent audio. No clean-profile live Tezbar install was attempted here.

Parent owns publication, final repository/artifact URLs, dual-target CI, signing,
trusted catalog pins and clean-profile app smoke. No commits, pushes, repositories,
PRs or releases were created by this implementation child.

Native sampling permits 110 seconds and requires a compatible host callback
budget. The beta15 host candidate now uses a generic 120-second background-event
deadline; its real-pipe test verifies survival past 30 seconds and cancellation
after 120 seconds using virtual time. Live tray sampling remains unverified.

Focused finalization review (same date): package inventories now include SOURCE.json;
required runtime resources are explicit and validated before packaging. Color Picker
preserves executable sampler permissions through ZIP extraction and excludes a stale
Mac helper from Windows packages. Both packagers require their declared native OS/
architecture. CI uses macos-15 ARM and windows-2022, single-job locked tests/builds,
strict Clippy, and extracted-package process smoke. Windows Color Picker additionally
compiles its real PowerShell/C# sampler via -Check, before any DPI/capture/UI calls.
These are supplied CI checks, not claims that hosted Windows jobs have run.

Review fixes: explicit tray retain/set denials are rejected. A cancelled tray
creation holds ownership through cleanup, preventing an immediate reopen from being
removed by stale cleanup. Hide completes its owned removal/lease release if its
response is cancelled. Real-pipe tests cover denial, reopen ordering and cancelled
Hide, plus existing sampler cancellation and post-disposal callbacks. Legacy import
rejects nonfiles, symlinks and oversized files before reading. Windows PowerShell
resolves from the OS directory; temporary sampler termination is asserted on both
platforms by the supplied tests. No real desktop sampler was launched locally.

Final Mach-O inspection found and fixed a build-machine-dependent deployment floor:
the sampler had minos 26.0, while the Rust executable has minos 11.0. build.sh now
explicitly targets arm64-apple-macos11.0; package creation and extracted smoke parse
LC_BUILD_VERSION and require macOS 11.0. The rebuilt helper is ARM64/ad-hoc signed.
This establishes binary metadata compatibility, not execution on macOS 11 hardware.

Windows CI follow-up, 2026-10-25 (base 8c21123e): job 121157016913 in run
40189412683 passed sampler `-Check`, fmt, strict Clippy and all 15 domain tests,
then failed the temporary sampler PID wait in the actual stdio test. Its generic
`Condition deadline` did not establish whether PowerShell failed, the fixture
exited, or the PID file was missing/encoded unexpectedly.

A regression at the actual Python Host-to-Popen boundary reproduced loss of
`SYSTEMROOT`: Windows Python iterates uppercase environment keys, while the
fixture allowlist matched only `SystemRoot`. The allowlist now compares case
insensitively, preserves only the same four OS variables, and derives its OS-only
PATH from the preserved OS root. This is a confirmed fixture defect, **not yet a
confirmed root cause of the native Windows failure**. Rust production code, SDK
pin and the two Tokio workers are unchanged.

The unchanged six-second PID deadline now distinguishes an early sampler response
(including its error) from missing/unreadable/invalid PID data, showing at most 32
fixture-file bytes as hex. The real stdio suite also exercises a temporary helper
that intentionally exits with stderr before the existing PID cancellation and
synthetic color-success checks. Six focused Python regressions run automatically
inside the existing Rust stdio integration test; no inherited tests are removed.

Local macOS follow-up: focused regressions, actual stdio integration, fmt, strict
all-target Clippy and all 15 domain tests pass, serially with `-j1`. No PowerShell,
Windows runtime or live desktop effects were available/exercised. Parent must run
the updated native Windows job and extracted-package smoke before claiming a
Windows fix. Detailed evidence and follow-up instructions:
`/tmp/tezbar-external-rust/color-windows-fix.md`.

Windows PID evidence round (base f34767e7): job 121161491586 in run 40190899105
passed all 15 domain tests, the six focused Python tests and the actual helper's
intentional stderr/exit-23 assertion. The next helper still reached the unchanged
six-second startup deadline with no PID file and a live extension. WinError32
during temporary-directory removal then masked that assertion; the log does not
identify the process holding the directory. SYSTEMROOT preservation is retained,
but it did not by itself resolve this native failure.

A real-process macOS regression reproduced the fixture's abrupt-parent-cleanup
defect: after a deliberately failed PID-file wait, its proven-live owned helper
survived the old `finally: h.kill()`. Cleanup now gives the SDK a bounded graceful
shutdown, servicing reverse RPC; EOF is a bounded fallback before hard termination
of this exact Rust child. Needing a fallback still fails/reports cleanup. Process
and directory cleanup errors preserve the primary assertion and report both
errors (including on Python 3.9). The regression requires the helper dead after
failure cleanup; another actual-process case requires it dead after active EOF.
The existing session.dispose live-before/dead-after and blur-release checks remain.

Native Windows diagnosis is still pending. The original PID fixture keeps
`Set-Content` and `Start-Sleep`, now with `$ErrorActionPreference = 'Stop'` and a
try/catch that reports `sampler-fixture-pid:` plus the actual exception to stderr
and exits 24. Small .NET stage files distinguish entry before Set-Content from PID
publication before Start-Sleep; missing stage data explicitly leaves script entry
unconfirmed. An invalid-parent write exercises that same fatal fixture path on
Windows. Separate .NET-only real helpers exercise failure cleanup/EOF and quoted
paths without cmdlet/provider dependencies; they do not replace the failing
cmdlet fixture. No production sampler, SDK, runtime source or startup deadline
was changed.

Local verification: 12 focused Python tests, all 15 domain tests and actual macOS
stdio integration pass, with serial `-j1` Rust checks and strict all-target Clippy.
The added Windows script/error/handle paths have not run here. The parent must
review/push this diagnostic round and require the complete native Windows job,
including extracted-package smoke; a green Mac run is not a Windows resolution.
Evidence, hashes and next-run interpretation:
`/tmp/tezbar-external-rust/color-windows-pid-fix.md`.


Windows cmdlet differential round (base 0e873f73): parent-supplied native job
121165863741/run 40192358541 passes 15 domain tests, 12 focused tests, real .NET
failure-cleanup/active-EOF controls and intentional stderr/exit-23. The original
invalid-parent Set-Content fixture still times out at six seconds after its .NET
entry marker, without its catch stderr. This locates the interval, not its cause.
No module-autoload root cause or native fix is claimed.

A temporary Windows-only diagnostic matrix now runs after the .NET lifecycle
controls, before the unchanged original stdio suite. Eight serial cases compare
.NET valid/invalid writes, Get-Command resolution, ordinary Set-Content valid/
invalid writes, OS-owned absolute Management-module import (autoload disabled)
plus the same writes, and the unmodified real production sampler invoked with
-Check. All use the actual Rust PowerShell argv and unchanged filtered Host
environment; -Check exits before DPI/capture/forms. Each request has a six-second
bound. Nonsecret result, elapsed time, stage, exception type/error ID and numeric
PID bytes are bounded. All cases report before the original failure can abort;
collected probe failures remain failing gates at suite end. The original PID,
error, cancellation, disposal, EOF, blur and synthetic clipboard assertions stay.

Each probe Rust process is assigned to a private kill-on-close Windows Job Object
before requesting a helper, owning PowerShell and any Add-Type compiler child.
SDK shutdown/EOF cleanup remains first; closing that exact job contains leftover
descendants. No global PID termination or ambient environment expansion is used.
Four focused regressions exercise timeout continuation/ownership/cleanup,
production-check rejection, write-error identity and missing-write rejection; the last was red before
adding file/stage assertions. Local macOS: all 16 focused tests, real stdio and
fmt pass. New PowerShell/Win32 paths have NOT executed locally. This is an evidence
patch for one parent-owned native CI run, not a publication-ready Windows fix.
Full evidence, hashes, unconfirmed hypotheses and parent steps:
/tmp/tezbar-external-rust/color-windows-cmdlet-fix.md.


Windows deterministic module bootstrap (base 2b5f7979): parent-supplied native
run 40193740576/job 121170029128 passed 15 domain and 16 focused tests plus .NET
cleanup/EOF controls. Ordinary Get-Command/Set-Content and production -Check each
timed out after six seconds; absolute OS Management import with autoload disabled
completed valid/invalid Set-Content writes in 0.213/0.209 seconds. This supports
bypassing discovery, without proving which missing ambient input caused delay.
The app allows more profile variables than this fixture: identical production-app
failure has not been demonstrated.

The production PowerShell sampler now dot-sources packaged windows-modules.ps1
before Add-Type. This imports only Utility from an absolute PSHOME manifest;
the same bootstrap optionally imports Management for the real Set-Content fixture.
Autoload is disabled only in the helper's script/child scopes, with no parent
environment changes. No Join-Path or other unloaded-module cmdlet is needed to
bootstrap. No PSModulePath, USERPROFILE or secrets are inherited by the fixture.
The production UI/C# code and -Check exit before DPI/capture/forms are preserved.
SOURCE.json records these derivative source changes; package inventories require
and hash the new bootstrap on both targets, including extracted-ZIP smoke.

The exploratory eight-case matrix is replaced by three strict release regressions:
shared-bootstrap positive/negative Set-Content and actual package sampler -Check,
through unchanged Rust argv/filtered environment with six-second request bounds.
The intentionally broken old implicit-autoload route is no longer a mandatory
gate; its exact native timeout evidence remains in the external evidence log and
report. No timeout is accepted as success. Expected invalid writes require both
DirectoryNotFound/SetContentCommand identity and a marker after successful imports.
Failure cleanup and active EOF now use that same initialized cmdlet PID fixture;
the existing numeric-PID/live-before/dead-after disposal assertions remain and an
explicit protocol-cancel termination check is added. Graceful SDK cleanup, original
failure preservation and private kill-on-close Windows Job ownership of the
production-check PowerShell/compiler descendants remain mandatory.

Local macOS validation is recorded in the external report below. PowerShell,
Utility import, Windows Job APIs and MSVC execution have not run locally. The next
native Windows job must complete the three cases, PID/write/error/cancel/dispose/
EOF/failure-cleanup assertions, release packaging and extracted-package smoke.
No live desktop capture, clipboard, tray, AI, permissions or user-data mutation
was exercised. SDK pin/two Tokio workers and all Rust domain code are unchanged.
Exact patch, changed-file hashes, local results and remaining native/live gates:
/tmp/tezbar-external-rust/color-windows-module-bootstrap-fix.md.
