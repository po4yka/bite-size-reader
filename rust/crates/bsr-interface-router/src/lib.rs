use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MobileRouteInput {
    pub method: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MobileRouteDecision {
    pub route_key: String,
    pub rate_limit_bucket: String,
    pub requires_auth: bool,
    pub handled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TelegramCommandInput {
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TelegramCommandDecision {
    pub command: Option<String>,
    pub handled: bool,
}

pub fn resolve_mobile_route(input: &MobileRouteInput) -> MobileRouteDecision {
    let method = input.method.trim().to_uppercase();
    let path = normalize_path(&input.path);

    if path == "/" {
        return MobileRouteDecision {
            route_key: "root".to_string(),
            rate_limit_bucket: "default".to_string(),
            requires_auth: false,
            handled: true,
        };
    }
    if path == "/health" {
        return MobileRouteDecision {
            route_key: "health".to_string(),
            rate_limit_bucket: "default".to_string(),
            requires_auth: false,
            handled: true,
        };
    }
    if path == "/metrics" {
        return MobileRouteDecision {
            route_key: "metrics".to_string(),
            rate_limit_bucket: "default".to_string(),
            requires_auth: false,
            handled: true,
        };
    }
    if path == "/docs"
        || path == "/redoc"
        || path == "/openapi.json"
        || path.starts_with("/static/")
    {
        return MobileRouteDecision {
            route_key: "docs".to_string(),
            rate_limit_bucket: "default".to_string(),
            requires_auth: false,
            handled: true,
        };
    }

    let mut route_key = "unknown".to_string();
    let mut bucket = "default".to_string();
    let mut handled = false;

    if matches_route_prefix(&path, "/v1/auth") {
        route_key = "auth".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/collections") {
        route_key = "collections".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/summaries") {
        route_key = "summaries".to_string();
        bucket = "summaries".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/articles") {
        route_key = "articles".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/requests") {
        route_key = "requests".to_string();
        bucket = "requests".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/search") {
        route_key = "search".to_string();
        bucket = "search".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/sync") {
        route_key = "sync".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/user") {
        route_key = "user".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/system") {
        route_key = "system".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/proxy") {
        route_key = "proxy".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/notifications") {
        route_key = "notifications".to_string();
        handled = true;
    } else if matches_route_prefix(&path, "/v1/digest") {
        route_key = "digest".to_string();
        handled = true;
    }

    let requires_auth = if route_key == "auth" {
        false
    } else {
        path.starts_with("/v1/")
    };

    let _ = method;
    MobileRouteDecision {
        route_key,
        rate_limit_bucket: bucket,
        requires_auth,
        handled,
    }
}

pub fn resolve_telegram_command(input: &TelegramCommandInput) -> TelegramCommandDecision {
    let text = input.text.as_str();
    if !text.starts_with('/') {
        return TelegramCommandDecision {
            command: None,
            handled: false,
        };
    }

    let Some(token) = text.split_whitespace().next() else {
        return TelegramCommandDecision {
            command: None,
            handled: false,
        };
    };
    let normalized = strip_bot_mention(token);

    let canonical = match normalized.as_str() {
        "/start" => Some("/start"),
        "/help" => Some("/help"),
        "/dbinfo" => Some("/dbinfo"),
        "/dbverify" => Some("/dbverify"),
        "/clearcache" => Some("/clearcache"),
        "/finddb" | "/findlocal" => Some("/finddb"),
        "/findweb" | "/findonline" | "/find" => Some("/find"),
        "/summarize_all" => Some("/summarize_all"),
        "/summarize" => Some("/summarize"),
        "/cancel" => Some("/cancel"),
        "/unread" => Some("/unread"),
        "/read" => Some("/read"),
        "/search" => Some("/search"),
        "/sync_karakeep" => Some("/sync_karakeep"),
        "/cdigest" => Some("/cdigest"),
        "/digest" => Some("/digest"),
        "/channels" => Some("/channels"),
        "/subscribe" => Some("/subscribe"),
        "/unsubscribe" => Some("/unsubscribe"),
        "/init_session" => Some("/init_session"),
        "/settings" => Some("/settings"),
        "/debug" => Some("/debug"),
        _ => None,
    };

    TelegramCommandDecision {
        command: canonical.map(str::to_string),
        handled: canonical.is_some(),
    }
}

fn normalize_path(path: &str) -> String {
    if path.is_empty() {
        return "/".to_string();
    }
    path.to_string()
}

fn matches_route_prefix(path: &str, prefix: &str) -> bool {
    if path == prefix {
        return true;
    }

    path.strip_prefix(prefix)
        .is_some_and(|rest| rest.starts_with('/') || rest.starts_with('?'))
}

fn strip_bot_mention(token: &str) -> String {
    let Some(stripped) = token.strip_prefix('/') else {
        return token.to_string();
    };
    let base = stripped.split('@').next().unwrap_or(stripped);
    format!("/{base}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mobile_route_summaries_bucket() {
        let decision = resolve_mobile_route(&MobileRouteInput {
            method: "GET".to_string(),
            path: "/v1/summaries".to_string(),
        });
        assert_eq!(decision.route_key, "summaries");
        assert_eq!(decision.rate_limit_bucket, "summaries");
        assert!(decision.requires_auth);
        assert!(decision.handled);
    }

    #[test]
    fn mobile_route_health_public() {
        let decision = resolve_mobile_route(&MobileRouteInput {
            method: "GET".to_string(),
            path: "/health".to_string(),
        });
        assert_eq!(decision.route_key, "health");
        assert_eq!(decision.rate_limit_bucket, "default");
        assert!(!decision.requires_auth);
        assert!(decision.handled);
    }

    #[test]
    fn mobile_route_articles_default_bucket() {
        let decision = resolve_mobile_route(&MobileRouteInput {
            method: "GET".to_string(),
            path: "/v1/articles".to_string(),
        });
        assert_eq!(decision.route_key, "articles");
        assert_eq!(decision.rate_limit_bucket, "default");
        assert!(decision.requires_auth);
        assert!(decision.handled);
    }

    #[test]
    fn mobile_route_rejects_partial_segment_overmatch() {
        let decision = resolve_mobile_route(&MobileRouteInput {
            method: "GET".to_string(),
            path: "/v1/summariesevil".to_string(),
        });
        assert_eq!(decision.route_key, "unknown");
        assert_eq!(decision.rate_limit_bucket, "default");
        assert!(decision.requires_auth);
        assert!(!decision.handled);
    }

    #[test]
    fn mobile_route_accepts_nested_segment_match() {
        let decision = resolve_mobile_route(&MobileRouteInput {
            method: "GET".to_string(),
            path: "/v1/summaries/123".to_string(),
        });
        assert_eq!(decision.route_key, "summaries");
        assert_eq!(decision.rate_limit_bucket, "summaries");
        assert!(decision.requires_auth);
        assert!(decision.handled);
    }

    #[test]
    fn telegram_command_alias_is_normalized() {
        let decision = resolve_telegram_command(&TelegramCommandInput {
            text: "/findonline rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn telegram_command_is_case_sensitive() {
        let decision = resolve_telegram_command(&TelegramCommandInput {
            text: "/Findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn telegram_command_requires_leading_slash_at_start() {
        let decision = resolve_telegram_command(&TelegramCommandInput {
            text: " /findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }
}
