import { useLocation, useNavigate } from "react-router-dom";

const TAB_ITEMS = [
  { label: "QUEUE", path: "/library" },
  { label: "DIGESTS", path: "/digest" },
  { label: "TOPICS", path: "/tags" },
  { label: "SETTINGS", path: "/preferences" },
] as const;

const tabBarCSS = `
  .frost-tab-bar {
    display: none;
  }
  @container main (max-width: 768px) {
    .frost-tab-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: var(--frost-tab-bar-height, 56px);
      background: var(--frost-page);
      border-top: 1px solid var(--frost-ink);
      display: flex;
      z-index: 200;
    }
  }
  .frost-tab-bar__item {
    flex: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-family: var(--frost-font-mono);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--frost-ink);
    text-decoration: none;
    padding: 12px 4px;
    opacity: 0.55;
    border-left: var(--frost-spark-mobile, 4px) solid transparent;
    box-sizing: border-box;
    transition: opacity 0.08s linear;
  }
  .frost-tab-bar__item--active {
    opacity: 1;
    border-left-color: var(--frost-spark);
  }
  @media (prefers-reduced-motion: reduce) {
    .frost-tab-bar__item {
      transition-duration: 0.001s !important;
    }
  }
`;

export function MobileTabBar() {
  const location = useLocation();
  const navigate = useNavigate();

  const activePath = (() => {
    const firstSegment = location.pathname.split("/")[1] ?? "library";
    return `/${firstSegment}`;
  })();

  return (
    <>
      <style>{tabBarCSS}</style>
      <nav className="frost-tab-bar" aria-label="Mobile navigation">
        {TAB_ITEMS.map((tab) => {
          const isActive = activePath === tab.path;
          return (
            <a
              key={tab.path}
              href={tab.path}
              className={[
                "frost-tab-bar__item",
                isActive ? "frost-tab-bar__item--active" : null,
              ]
                .filter(Boolean)
                .join(" ")}
              aria-current={isActive ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                navigate(tab.path);
              }}
            >
              {tab.label}
            </a>
          );
        })}
      </nav>
    </>
  );
}
