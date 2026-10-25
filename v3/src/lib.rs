mod domain;
mod migration;
pub use domain::COLOR_NAMER_LICENSE;
use serde_json::{json, Value};
use tezbar_extension_sdk::{BoxFuture, CoreResult, Extension, ExtensionContext};
const SLUG: &str = "color-picker";
#[derive(Default)]
pub struct Adapter {
    gate: tokio::sync::Mutex<()>,
}
impl Extension for Adapter {
    fn id(&self) -> &'static str {
        "com.tezbar.native.color-picker"
    }
    fn version(&self) -> &'static str {
        env!("CARGO_PKG_VERSION")
    }
    fn commands(&self) -> &'static [&'static str] {
        domain::commands()
    }
    fn initialize<'a>(&'a self, ctx: &'a ExtensionContext) -> BoxFuture<'a, CoreResult> {
        Box::pin(async move {
            migration::import_native(ctx).await?;
            Ok(json!({"ready":true}))
        })
    }
    fn handle<'a>(
        &'a self,
        ctx: &'a ExtensionContext,
        command: &'a str,
        operation: &'a str,
        payload: &'a Value,
        state: &'a mut Value,
    ) -> BoxFuture<'a, CoreResult> {
        Box::pin(async move {
            if operation == "extension:dispose-session" {
                domain::finish_cleanups().await;
                return Ok(tezbar_extension_sdk::unchanged());
            }
            let _guard = if operation == "extension:refresh-session" {
                match self.gate.try_lock() {
                    Ok(guard) => guard,
                    Err(_) => return Ok(tezbar_extension_sdk::unchanged()),
                }
            } else {
                self.gate.lock().await
            };
            domain::handle(ctx, command, operation, payload, state).await
        })
    }
    fn background_event<'a>(
        &'a self,
        ctx: &'a ExtensionContext,
        params: &'a Value,
    ) -> BoxFuture<'a, CoreResult> {
        Box::pin(async move {
            let _guard = self.gate.lock().await;
            domain::tray_event(ctx, params).await
        })
    }
    fn shutdown<'a>(&'a self, ctx: &'a ExtensionContext) -> BoxFuture<'a, CoreResult> {
        Box::pin(async move {
            domain::finish_cleanups().await;
            domain::cleanup_tray(ctx).await
        })
    }
}
