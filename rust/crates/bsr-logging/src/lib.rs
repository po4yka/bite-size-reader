use tracing_subscriber::EnvFilter;

pub fn init_logging(default_level: &str) {
    let filter = EnvFilter::try_from_default_env()
        .or_else(|_| EnvFilter::try_new(default_level))
        .expect("valid log level");

    let _ = tracing_subscriber::fmt()
        .with_env_filter(filter)
        .json()
        .with_target(true)
        .try_init();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn init_is_idempotent() {
        init_logging("info");
        init_logging("info");
    }
}
