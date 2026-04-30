import { useEffect, useMemo, useState } from "react";
import ErrorBoundary from "./ErrorBoundary";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Button,
  Content,
  Header,
  HeaderGlobalBar,
  HeaderGlobalAction,
  HeaderMenuButton,
  HeaderName,
  InlineNotification,
  SideNav,
  SideNavDivider,
  SideNavItems,
  SideNavLink,
  SkipToContent,
  Theme,
  Logout,
  Renew,
} from "../design";
import { useAuth } from "../auth/AuthProvider";
import { HOME_PATH, NAV_GROUPS, NAV_ROOT_PATHS } from "../routes/manifest";

type AppTheme = "light" | "dark";

function resolveAppTheme(mode: "telegram-webapp" | "jwt"): AppTheme {
  if (mode !== "telegram-webapp") {
    return "light";
  }
  const colorScheme =
    (window as Window & { __tgColorScheme?: string }).__tgColorScheme ??
    window.Telegram?.WebApp?.colorScheme;
  return colorScheme === "dark" ? "dark" : "light";
}

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { dismissError, error, logout, mode, reloadUser, user } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [isVerifyingSession, setIsVerifyingSession] = useState(false);
  const [theme, setTheme] = useState<AppTheme>(() => resolveAppTheme(mode));

  const activePath = useMemo(() => {
    const firstSegment = location.pathname.split("/")[1] ?? "library";
    return `/${firstSegment}`;
  }, [location.pathname]);

  const sessionLabel = mode === "telegram-webapp" ? "Telegram session" : "Web session";
  const shouldShowTelegramBackButton = useMemo(() => {
    if (mode !== "telegram-webapp") return false;
    return !NAV_ROOT_PATHS.has(location.pathname);
  }, [location.pathname, mode]);

  async function handleSessionVerify(): Promise<void> {
    try {
      setIsVerifyingSession(true);
      await reloadUser();
    } finally {
      setIsVerifyingSession(false);
    }
  }

  useEffect(() => {
    setTheme(resolveAppTheme(mode));

    if (mode !== "telegram-webapp") {
      return;
    }

    const webApp = window.Telegram?.WebApp;
    if (!webApp?.onEvent) {
      return;
    }

    const handleThemeChanged = () => {
      setTheme(resolveAppTheme(mode));
    };

    webApp.onEvent("themeChanged", handleThemeChanged);
    return () => {
      webApp.offEvent?.("themeChanged", handleThemeChanged);
    };
  }, [mode]);

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    const backButton = webApp?.BackButton;
    if (!backButton) {
      return;
    }

    if (!shouldShowTelegramBackButton) {
      backButton.hide?.();
      return;
    }

    const handleBackClick = () => {
      const historyIndex = Number(window.history.state?.idx ?? 0);
      if (historyIndex > 0) {
        navigate(-1);
        return;
      }
      navigate(HOME_PATH, { replace: true });
    };

    backButton.show?.();
    backButton.onClick?.(handleBackClick);

    return () => {
      backButton.offClick?.(handleBackClick);
      backButton.hide?.();
    };
  }, [navigate, shouldShowTelegramBackButton]);

  return (
    <Theme theme={theme}>
      <div className="app-shell">
        <SkipToContent />
        <Header aria-label="Ratatoskr Web">
          <HeaderMenuButton
            aria-label={expanded ? "Close navigation menu" : "Open navigation menu"}
            onClick={() => setExpanded((prev) => !prev)}
            isActive={expanded}
          />
          <HeaderName as={Link} to={HOME_PATH} prefix="">
            Ratatoskr
          </HeaderName>
          <HeaderGlobalBar>
            {user?.username && <span className="app-shell-user">@{user.username}</span>}
            <span className="app-shell-session">{sessionLabel}</span>
            <HeaderGlobalAction
              aria-label={isVerifyingSession ? "Verifying session" : "Verify session"}
              onClick={() => void handleSessionVerify()}
            >
              <Renew size={20} />
            </HeaderGlobalAction>
            <HeaderGlobalAction aria-label="Sign out" onClick={logout}>
              <Logout size={20} />
            </HeaderGlobalAction>
          </HeaderGlobalBar>
        </Header>

        <SideNav
          aria-label="Main navigation"
          expanded={expanded}
          onOverlayClick={() => setExpanded(false)}
          onSideNavBlur={() => setExpanded(false)}
          isFixedNav
        >
          <SideNavItems>
            {NAV_GROUPS.map((group, groupIndex) => (
              <span key={groupIndex}>
                {groupIndex > 0 && <SideNavDivider />}
                {group.map((item) => (
                  <SideNavLink
                    key={item.path}
                    href={`/web${item.path}`}
                    isActive={activePath === item.path}
                    aria-current={activePath === item.path ? "page" : undefined}
                    renderIcon={item.icon}
                    onClick={(event: React.MouseEvent) => {
                      event.preventDefault();
                      navigate(item.path);
                      setExpanded(false);
                    }}
                  >
                    {item.label}
                  </SideNavLink>
                ))}
              </span>
            ))}
          </SideNavItems>
        </SideNav>

        <Content id="main-content" className="app-content">
          {error && (
            <section className="app-session-alert">
              <InlineNotification
                kind="warning"
                title="Session requires attention"
                subtitle={error}
                onCloseButtonClick={() => dismissError()}
              />
              <div className="form-actions app-session-actions">
                <Button
                  kind="tertiary"
                  size="sm"
                  onClick={() => void handleSessionVerify()}
                  disabled={isVerifyingSession}
                >
                  {isVerifyingSession ? "Verifying…" : "Verify session"}
                </Button>
                <Button kind="ghost" size="sm" onClick={logout}>
                  Sign in again
                </Button>
              </div>
            </section>
          )}
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </Content>
      </div>
    </Theme>
  );
}
