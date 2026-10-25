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
- Package-owned Swift sampler builds and ad-hoc codesigns as ARM64. Original Swift and PowerShell source retained.

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
