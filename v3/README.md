# Color Picker — standalone Rust process

All nine commands and their original preferences are preserved. The existing
TypeScript fixture at the repository root is untouched; this `v3/` directory
contains the schema-3 executable package. No Node, Bun, Tauri, app crate, installed
Raycast bundle, or app-native resource directory is required by the executable.

The baseline's twelve color formats, CSS space math, naming palettes, history,
favorites, migrations, color wheel, bounded image decoding/median-cut extraction,
and AI prompt/strict JSON HEX parsing remain in Rust. Native screen sampling uses
this package's Swift/AppKit helper on macOS and PowerShell helper on Windows.
A generic host implements clipboard, selection, window/blur, AI, shell/settings,
tray, and background capabilities. AI remains user-configured in the host.

The menu uses component-safe background callbacks and a nondurable process lease.
It survives disposal of its command view and is removed/released on Hide or
process shutdown. Host-generation cleanup removes it after crash/disable. The
frozen flat tray menu API expresses Favorites/Recent groups as label prefixes.
Cross-extension callback launch options remain explicitly unsupported, as in the
baseline; a picker reports this before sampling or copying.

Build the package-owned sampler on a Mac with Xcode command-line tools:

```sh
cd v3
bash resources/sampler/build.sh
cargo test --locked -j 1 -- --test-threads=1
cargo build --release --locked -j 1
python3 scripts/package.py --target aarch64-apple-darwin --binary target/release/tezbar-color-picker
python3 scripts/smoke.py --target aarch64-apple-darwin --archive dist/color-picker-aarch64-apple-darwin.zip
```

Windows x64 builds use `cargo build --release --locked` on a native Windows
runner and package `target/release/tezbar-color-picker.exe` for
`x86_64-pc-windows-msvc`. Its sampler uses the included `resources/sampler/windows.ps1`.
macOS sampler permission, actual sampling, clipboard, AI service, and tray OS UI
still require a live host smoke; headless tests acknowledge generic host calls.

## Protocol and storage

`--protocol-info` and `--self-test` are headless. Normal invocation uses only
UTF-8 JSON-lines on stdin/stdout and logs errors to stderr. The real independent
`tezbar-extension-sdk` 0.1.0 handles protocol 1, sessions/cancellation, and host RPC.
`extension.json` preserves schema-3 commands/preferences and declares capabilities.
Storage is `<host-private-data-dir>/color-picker/storage.json`, updated atomically by
the SDK's shared transaction mutex. Malformed JSON is rejected without overwriting.
Only explicitly host-granted `migrationPaths` files are imported, read-only, once;
existing scoped values and unknown native-v2 keys are preserved. Preferences are
still supplied by the host per session and are never copied from global config.

Source baseline: `fe71ca87f21ac4ff31505010c228f8abda0f2a89`. See SOURCE.json and NOTICE.
The licenses describe source/data/artwork separately; no blanket ownership claim
is made for upstream assets or names.

## Packaging and publication

A target ZIP contains extension.json, bin/<executable>, resources/**, licenses/**,
LICENSE, NOTICE and README. Its `files` object hashes every file except its own
manifest. `scripts/package.py` validates native executable identity and emits a
separate artifact JSON with actual ZIP/executable SHA-256. Source artifacts remain
empty until parent publishes; no digest is invented and no user-machine Cargo
build is needed to install a published ZIP. `scripts/smoke.py` extracts/verifies
inventory and executes the real process against a headless host using OS-only PATH.

SDK is pinned to published immutable revision
`9f91afcc071c3f301414dc62b33cfeac7d89a0cf` from
https://github.com/almatkai/tezbar-extension-sdk-rust.git; Cargo.lock is delivered
with the executable source. CI enforces an immutable SDK revision. CI builds/tests/packages on native macOS ARM
and Windows x64; a workflow is not Windows validation evidence. Parent owns remote
repository creation, publication, final URLs/digests, signing, and catalog pinning.
See VALIDATION.md for actual local evidence and remaining integration checks.
