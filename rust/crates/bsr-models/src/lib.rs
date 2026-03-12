use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MigrationHistoryEntry {
    pub migration_name: String,
    pub applied_at: Option<String>,
    pub rollback_sql: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MigrationStatusEntry {
    pub migration_name: String,
    pub applied: bool,
    pub applied_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MigrationStatusReport {
    pub total: usize,
    pub applied: usize,
    pub pending: usize,
    pub migrations: Vec<MigrationStatusEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TelemetryEvent {
    pub event_type: String,
    pub surface: String,
    pub correlation_id: Option<String>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}
