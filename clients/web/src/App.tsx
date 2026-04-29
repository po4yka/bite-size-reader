import { Suspense } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Button, InlineLoading, InlineNotification, Tile } from "./design";
import { useAuth } from "./auth/AuthProvider";
import LoginPage from "./auth/LoginPage";
import { sanitizeRedirectPath } from "./auth/redirect";
import RouteGuard from "./auth/RouteGuard";
import AppShell from "./components/AppShell";
import { ENABLED_APP_ROUTES, HOME_PATH } from "./routes/manifest";

function RouteLoader() {
  return (
    <section className="page-section">
      <InlineLoading description="Loading..." />
    </section>
  );
}

function HomeRedirect() {
  return <Navigate to={HOME_PATH} replace />;
}

function NotFoundPage() {
  return (
    <div className="login-page">
      <Tile className="login-card">
        <div className="page-heading-group">
          <h2>Page not found</h2>
          <p className="page-subtitle">This route does not exist.</p>
        </div>
        <div className="form-actions">
          <Button kind="primary" size="sm" as={Link} to={HOME_PATH}>
            Go to Library
          </Button>
        </div>
      </Tile>
    </div>
  );
}

function LoginRoute() {
  const location = useLocation();
  const { mode, status } = useAuth();
  const fromPath = sanitizeRedirectPath((location.state as { from?: string } | null)?.from);

  if (mode === "telegram-webapp") {
    if (status === "loading") {
      return (
        <section className="page-section">
          <InlineLoading description="Checking Telegram session…" />
        </section>
      );
    }
    if (status === "authenticated") {
      return <Navigate to={fromPath} replace />;
    }
    return (
      <section className="page-section">
        <InlineNotification
          kind="error"
          title="Telegram authentication failed"
          subtitle="Please reopen the Mini App from the bot and try again."
          hideCloseButton
        />
      </section>
    );
  }

  if (status === "authenticated") {
    return <Navigate to={fromPath} replace />;
  }

  return <LoginPage />;
}

export default function App() {
  const renderRouteElement = (route: (typeof ENABLED_APP_ROUTES)[number]) => {
    const Component = route.component;
    const element = <Component />;
    if (!route.lazy) {
      return element;
    }
    return <Suspense fallback={<RouteLoader />}>{element}</Suspense>;
  };

  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />

      <Route
        element={
          <RouteGuard>
            <AppShell />
          </RouteGuard>
        }
      >
        <Route index element={<HomeRedirect />} />
        {ENABLED_APP_ROUTES.map((route) => (
          <Route key={route.path} path={route.path} element={renderRouteElement(route)} />
        ))}
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
