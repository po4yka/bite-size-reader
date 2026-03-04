use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TelegramCommandRouteInput {
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TelegramCommandRouteDecision {
    pub command: Option<String>,
    pub handled: bool,
}

pub fn resolve_command_route(input: &TelegramCommandRouteInput) -> TelegramCommandRouteDecision {
    let text = input.text.as_str();
    if !text.starts_with('/') {
        return TelegramCommandRouteDecision {
            command: None,
            handled: false,
        };
    }

    let Some(token) = text.split_whitespace().next() else {
        return TelegramCommandRouteDecision {
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

    TelegramCommandRouteDecision {
        command: canonical.map(str::to_string),
        handled: canonical.is_some(),
    }
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
    fn command_alias_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn alias_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline@mybot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn bare_alias_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn alias_command_with_mixed_case_bot_username_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline@MyBot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn bare_alias_command_with_mixed_case_bot_username_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline@MyBot".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn bare_alias_command_with_empty_bot_mention_suffix_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline@".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn alias_command_with_empty_bot_mention_suffix_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findonline@ rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn legacy_alias_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findweb@mybot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn canonical_find_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/find@mybot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn canonical_find_command_with_mixed_case_bot_username_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/find@MyBot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn canonical_find_command_with_empty_bot_mention_suffix_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/find@ rust".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn bare_canonical_find_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/find@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn bare_canonical_find_command_with_mixed_case_bot_username_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/find@MyBot".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn bare_canonical_find_command_with_empty_bot_mention_suffix_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/find@".to_string(),
        });
        assert_eq!(decision.command, Some("/find".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn local_alias_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/findlocal@mybot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/finddb".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn canonical_local_search_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/finddb@mybot rust".to_string(),
        });
        assert_eq!(decision.command, Some("/finddb".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn summarize_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/summarize@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/summarize".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn cancel_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/cancel@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/cancel".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn search_command_with_bot_mention_and_arguments_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/search@mybot rust migration".to_string(),
        });
        assert_eq!(decision.command, Some("/search".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn start_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/start@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/start".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn help_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/help@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/help".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn dbinfo_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/dbinfo@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/dbinfo".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn dbverify_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/dbverify@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/dbverify".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn clearcache_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/clearcache@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/clearcache".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn summarize_all_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/summarize_all@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/summarize_all".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn unread_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unread@mybot 10".to_string(),
        });
        assert_eq!(decision.command, Some("/unread".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn read_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/read@mybot 10".to_string(),
        });
        assert_eq!(decision.command, Some("/read".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn sync_karakeep_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/sync_karakeep@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/sync_karakeep".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn cdigest_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/cdigest@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/cdigest".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn digest_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/digest@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/digest".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn channels_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/channels@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/channels".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn subscribe_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/subscribe@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/subscribe".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn unsubscribe_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unsubscribe@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/unsubscribe".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn init_session_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/init_session@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/init_session".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn settings_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/settings@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/settings".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn debug_command_with_bot_mention_is_normalized() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/debug@mybot".to_string(),
        });
        assert_eq!(decision.command, Some("/debug".to_string()));
        assert!(decision.handled);
    }

    #[test]
    fn unknown_command_with_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd@mybot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_bare_command_with_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd@mybot".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_bare_command_with_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd@mybot".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_command_with_mixed_case_bot_username_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd@MyBot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_bare_command_with_mixed_case_bot_username_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd@MyBot".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_command_with_empty_bot_mention_suffix_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd@ rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_bare_command_with_empty_bot_mention_suffix_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd@".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_command_with_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd@mybot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_command_with_mixed_case_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd@MyBot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_bare_command_with_mixed_case_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd@MyBot".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_command_with_empty_bot_mention_suffix_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd@ rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_bare_command_with_empty_bot_mention_suffix_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd@".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_command_without_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_bare_command_without_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/unknowncmd".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_command_without_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn unknown_mixed_case_bare_command_without_bot_mention_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Unknowncmd".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn command_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn command_with_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline@mybot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn canonical_command_with_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find@mybot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn canonical_command_with_mixed_case_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find@MyBot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn bare_command_with_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline@mybot".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn command_with_mixed_case_bot_username_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline@MyBot rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn bare_command_with_mixed_case_bot_username_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline@MyBot".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn command_with_empty_bot_mention_suffix_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline@ rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn bare_command_with_empty_bot_mention_suffix_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline@".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn command_requires_leading_slash_at_start() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: " /findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }
}
