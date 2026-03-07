import { useMemo, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Content,
  Header,
  HeaderGlobalBar,
  HeaderGlobalAction,
  HeaderMenuButton,
  HeaderName,
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
  User,
  Logout,
} from "@carbon/icons-react";
import { useAuth } from "../auth/AuthProvider";

const NAV_ITEMS = [
  { path: "/library", label: "Library", icon: Book },
  { path: "/search", label: "Search", icon: SearchIcon },
  { path: "/submit", label: "Submit", icon: Add },
  { path: "/collections", label: "Collections", icon: Catalog },
  { path: "/preferences", label: "Preferences", icon: User },
] as const;

export default function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [expanded, setExpanded] = useState(false);

  const activePath = useMemo(() => {
    const firstSegment = location.pathname.split("/")[1] ?? "library";
    return `/${firstSegment}`;
  }, [location.pathname]);

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
          <Outlet />
        </Content>
      </div>
    </Theme>
  );
}
