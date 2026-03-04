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
    fn known_command_without_bot_mention_is_case_sensitive() {
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
    fn canonical_command_without_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn bare_canonical_command_without_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find".to_string(),
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
    fn canonical_command_with_empty_bot_mention_suffix_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find@ rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn bare_canonical_command_with_empty_bot_mention_suffix_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find@".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn bare_canonical_command_with_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find@mybot".to_string(),
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
    fn bare_canonical_command_with_mixed_case_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Find@MyBot".to_string(),
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
    fn bare_command_without_bot_mention_is_case_sensitive() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/Findonline".to_string(),
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

    #[test]
    fn command_like_text_without_leading_slash_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_only_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/ findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_tab_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\tfindonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_newline_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\nfindonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_carriage_return_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\rfindonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_form_feed_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\x0cfindonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_vertical_tab_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\x0bfindonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_non_breaking_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{00A0}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_narrow_no_break_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{202F}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_figure_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2007}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_thin_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2009}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_ideographic_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{3000}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_hair_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{200A}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_medium_mathematical_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{205F}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_punctuation_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2008}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_six_per_em_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2006}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_four_per_em_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2005}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_three_per_em_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2004}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_em_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2003}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_en_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2002}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_em_quad_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2001}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_en_quad_space_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2000}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_ogham_space_mark_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{1680}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_line_separator_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2028}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_paragraph_separator_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{2029}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_next_line_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0085}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_file_separator_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{001C}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_group_separator_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{001D}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_record_separator_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{001E}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_unit_separator_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{001F}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_delete_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{007F}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_padding_character_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0080}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_high_octet_preset_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0081}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_break_permitted_here_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0082}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_no_break_here_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0083}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_index_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0084}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_start_of_selected_area_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0086}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_end_of_selected_area_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0087}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_character_tabulation_set_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0088}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_character_tabulation_with_justification_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0089}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_line_tabulation_set_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{008A}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_partial_line_forward_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{008B}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_partial_line_backward_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{008C}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_reverse_line_feed_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{008D}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_single_shift_two_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{008E}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_single_shift_three_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{008F}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_device_control_string_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0090}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_private_use_one_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0091}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_private_use_two_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0092}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_set_transmit_state_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0093}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }

    #[test]
    fn slash_cancel_character_command_like_text_is_not_handled() {
        let decision = resolve_command_route(&TelegramCommandRouteInput {
            text: "/\u{0094}findonline rust".to_string(),
        });
        assert_eq!(decision.command, None);
        assert!(!decision.handled);
    }
}
