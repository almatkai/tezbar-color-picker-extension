#[test]
fn actual_stdio_lifecycle_regressions() {
    let python = if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    };
    let focused = std::process::Command::new(python)
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .args([
            "-m",
            "unittest",
            "discover",
            "-s",
            "scripts",
            "-p",
            "test_protocol_host.py",
        ])
        .status()
        .expect("Python 3 fixture host regressions required");
    assert!(focused.success(), "Focused fixture host regressions failed");
    let status = std::process::Command::new(python)
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/scripts/protocol_test.py"
        ))
        .args([
            "--binary",
            env!("CARGO_BIN_EXE_tezbar-color-picker"),
            "--package",
            env!("CARGO_MANIFEST_DIR"),
            "--slug",
            "color-picker",
        ])
        .status()
        .expect("Python 3 fixture host required");
    assert!(status.success(), "Actual stdio regression fixture failed");
}
