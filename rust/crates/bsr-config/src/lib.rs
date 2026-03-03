use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RuntimeConfig {
    pub log_level: String,
    pub db_path: String,
    pub max_concurrent_calls: usize,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("invalid MAX_CONCURRENT_CALLS: {0}")]
    InvalidConcurrency(String),
}

impl RuntimeConfig {
    pub fn from_env() -> Result<Self, ConfigError> {
        let log_level = std::env::var("LOG_LEVEL").unwrap_or_else(|_| "INFO".to_string());
        let db_path = std::env::var("DB_PATH").unwrap_or_else(|_| "/data/app.db".to_string());
        let max_concurrent_calls = std::env::var("MAX_CONCURRENT_CALLS")
            .unwrap_or_else(|_| "4".to_string())
            .parse::<usize>()
            .map_err(|_| ConfigError::InvalidConcurrency("must be an integer".to_string()))?;

        Ok(Self {
            log_level,
            db_path,
            max_concurrent_calls,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_defaults() {
        std::env::remove_var("LOG_LEVEL");
        std::env::remove_var("DB_PATH");
        std::env::remove_var("MAX_CONCURRENT_CALLS");

        let config = RuntimeConfig::from_env().expect("default config should load");
        assert_eq!(config.log_level, "INFO");
        assert_eq!(config.db_path, "/data/app.db");
        assert_eq!(config.max_concurrent_calls, 4);
    }
}
