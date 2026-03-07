import { useMemo, useState } from "react";
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
  Notification,
  User,
  Logout,
  Renew,
} from "@carbon/icons-react";
import { useAuth } from "../auth/AuthProvider";

const NAV_ITEMS = [
  { path: "/library", label: "Library", icon: Book },
  { path: "/articles", label: "Articles", icon: Book },
  { path: "/search", label: "Search", icon: SearchIcon },
  { path: "/submit", label: "Submit", icon: Add },
  { path: "/collections", label: "Collections", icon: Catalog },
  { path: "/digest", label: "Digest", icon: Notification },
  { path: "/preferences", label: "Preferences", icon: User },
] as const;

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { dismissError, error, logout, mode, reloadUser, user } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [isVerifyingSession, setIsVerifyingSession] = useState(false);

  const activePath = useMemo(() => {
    const firstSegment = location.pathname.split("/")[1] ?? "library";
    return `/${firstSegment}`;
  }, [location.pathname]);

  const sessionLabel = mode === "telegram-webapp" ? "Telegram session" : "Web session";

  async function handleSessionVerify(): Promise<void> {
    try {
      setIsVerifyingSession(true);
      await reloadUser();
    } finally {
      setIsVerifyingSession(false);
    }
  }

  return (
    <Theme theme="white">
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
                  {isVerifyingSession ? "Verifying..." : "Verify session"}
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
