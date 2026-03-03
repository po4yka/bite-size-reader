use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SummaryContract {
    pub summary_250: String,
    pub summary_1000: String,
    pub tldr: String,
}

#[derive(Debug, Error)]
pub enum SummaryValidationError {
    #[error("summary_250 exceeds 250 characters")]
    Summary250TooLong,
    #[error("summary_1000 exceeds 1000 characters")]
    Summary1000TooLong,
}

impl SummaryContract {
    pub fn validate(self) -> Result<Self, SummaryValidationError> {
        if self.summary_250.chars().count() > 250 {
            return Err(SummaryValidationError::Summary250TooLong);
        }
        if self.summary_1000.chars().count() > 1000 {
            return Err(SummaryValidationError::Summary1000TooLong);
        }
        Ok(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_valid_payload() {
        let contract = SummaryContract {
            summary_250: "small".to_string(),
            summary_1000: "long enough".to_string(),
            tldr: "brief".to_string(),
        };
        assert!(contract.validate().is_ok());
    }

    #[test]
    fn rejects_long_summary_250() {
        let contract = SummaryContract {
            summary_250: "a".repeat(251),
            summary_1000: "ok".to_string(),
            tldr: "brief".to_string(),
        };
        assert!(matches!(
            contract.validate(),
            Err(SummaryValidationError::Summary250TooLong)
        ));
    }
}
