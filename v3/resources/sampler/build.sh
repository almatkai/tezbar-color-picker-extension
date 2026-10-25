#!/usr/bin/env bash
set -euo pipefail
HELPER_DIR="$(cd "$(dirname "$0")" && pwd)"
swiftc "$HELPER_DIR/main.swift" -target arm64-apple-macos11.0 -O -framework AppKit -o "$HELPER_DIR/color-picker-helper"
codesign --force --sign - "$HELPER_DIR/color-picker-helper"
