//! Explicit, read-only native-v2 import. Only host-granted files are accessed.
use serde_json::{json, Value};
use tezbar_extension_sdk::{read_store, update_store, CoreResult, ExtensionContext};
pub async fn import_native(ctx: &ExtensionContext) -> CoreResult {
    let current = read_store(ctx, crate::SLUG).await?;
    if current["nativeV2MigrationVersion"] == 1 {
        return Ok(current);
    }
    let source = if let Some(path) = ctx.migration_paths.get("native-v2-store") {
        let meta = tokio::fs::symlink_metadata(path)
            .await
            .map_err(|e| format!("Cannot inspect native-v2 migration: {e}"))?;
        if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > 16 * 1024 * 1024 {
            return Err("Invalid native-v2 migration file".into());
        }
        let bytes = tokio::fs::read(path).await.map_err(|e| e.to_string())?;
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|_| "Corrupt native-v2 store; original preserved")?;
        if !value.is_object() {
            return Err("Native-v2 store must be an object".into());
        }
        value
    } else {
        json!({})
    };
    update_store(ctx, crate::SLUG, move |store| {
        if store["nativeV2MigrationVersion"] == 1 {
            return Ok(());
        }
        let target = store.as_object_mut().ok_or("Invalid scoped store")?;
        for (key, value) in source.as_object().unwrap() {
            target.entry(key.clone()).or_insert_with(|| value.clone());
        }
        target.insert("nativeV2MigrationVersion".into(), json!(1));
        Ok(())
    })
    .await
}
