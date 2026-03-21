import { useEffect, useMemo, useState } from "react";
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
  SideNavItems,
  SideNavLink,
  SkipToContent,
  Theme,
} from "@carbon/react";
import {
  Book,
  Catalog,
  Search as SearchIcon,
  Add,
  Tag,
  Notification,
  Settings,
  User,
  Logout,
  Renew,
  ConnectionSignal,
} from "@carbon/icons-react";
import { useAuth } from "../auth/AuthProvider";
import { FEATURE_FLAGS } from "../routes/features";

const NAV_ITEMS = [
  { path: "/library", label: "Library", icon: Book },
  { path: "/articles", label: "Articles", icon: Book },
  { path: "/search", label: "Search", icon: SearchIcon },
  { path: "/submit", label: "Submit", icon: Add },
  { path: "/collections", label: "Collections", icon: Catalog },
  { path: "/tags", label: "Tags", icon: Tag },
  { path: "/digest", label: "Digest", icon: Notification },
  { path: "/webhooks", label: "Webhooks", icon: ConnectionSignal },
  { path: "/preferences", label: "Preferences", icon: User },
] as const;

const ADMIN_NAV_ITEM = { path: "/admin", label: "Admin", icon: Settings } as const;

const NAV_ROOT_PATHS: ReadonlySet<string> = new Set(NAV_ITEMS.map((item) => item.path));

type CarbonTheme = "white" | "g100";

function resolveCarbonTheme(mode: "telegram-webapp" | "jwt"): CarbonTheme {
  if (mode !== "telegram-webapp") {
    return "white";
  }
  const colorScheme =
    (window as Window & { __tgColorScheme?: string }).__tgColorScheme ??
    window.Telegram?.WebApp?.colorScheme;
  return colorScheme === "dark" ? "g100" : "white";
}

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { dismissError, error, logout, mode, reloadUser, user } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [isVerifyingSession, setIsVerifyingSession] = useState(false);
  const [theme, setTheme] = useState<CarbonTheme>(() => resolveCarbonTheme(mode));

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
    setTheme(resolveCarbonTheme(mode));

    if (mode !== "telegram-webapp") {
      return;
    }

    const webApp = window.Telegram?.WebApp;
    if (!webApp?.onEvent) {
      return;
    }

    const handleThemeChanged = () => {
      setTheme(resolveCarbonTheme(mode));
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
      navigate("/library", { replace: true });
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
        <Header aria-label="Bite-Size Reader Web">
          <HeaderMenuButton
            aria-label={expanded ? "Close navigation menu" : "Open navigation menu"}
            onClick={() => setExpanded((prev) => !prev)}
            isActive={expanded}
          />
          <HeaderName as={Link} to="/library" prefix="Bite-Size">
            Reader
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
            {NAV_ITEMS.map((item) => (
              <SideNavLink
                key={item.path}
                href={`/web${item.path}`}
                isActive={activePath === item.path}
                renderIcon={item.icon}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(item.path);
                  setExpanded(false);
                }}
              >
                {item.label}
              </SideNavLink>
            ))}
            {FEATURE_FLAGS.admin && (
              <SideNavLink
                href={`/web${ADMIN_NAV_ITEM.path}`}
                isActive={activePath === ADMIN_NAV_ITEM.path}
                renderIcon={ADMIN_NAV_ITEM.icon}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(ADMIN_NAV_ITEM.path);
                  setExpanded(false);
                }}
              >
                {ADMIN_NAV_ITEM.label}
              </SideNavLink>
            )}
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
          <Outlet />
        </Content>
      </div>
    </Theme>
  );
}
