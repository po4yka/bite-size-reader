import { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Button, InlineLoading, InlineNotification, Tile } from "@carbon/react";
import { useAuth } from "./auth/AuthProvider";
import LoginPage from "./auth/LoginPage";
import { sanitizeRedirectPath } from "./auth/redirect";
import RouteGuard from "./auth/RouteGuard";
import AppShell from "./components/AppShell";
import ArticlePage from "./features/article/ArticlePage";
import ArticlesPage from "./features/articles/ArticlesPage";
import LibraryPage from "./features/library/LibraryPage";
import PreferencesPage from "./features/preferences/PreferencesPage";
import SubmitPage from "./features/submit/SubmitPage";
import { FEATURE_FLAGS } from "./routes/features";

const CollectionsPage = lazy(() => import("./features/collections/CollectionsPage"));
const DigestPage = lazy(() => import("./features/digest/DigestPage"));
const CustomDigestViewPage = lazy(() => import("./features/digest/CustomDigestViewPage"));
const SearchPage = lazy(() => import("./features/search/SearchPage"));
const TagManagementPage = lazy(() => import("./features/tags/TagManagementPage"));
const WebhooksPage = lazy(() => import("./features/webhooks/WebhooksPage"));
const RulesPage = lazy(() => import("./features/rules/RulesPage"));
const ImportExportPage = lazy(() => import("./features/import-export/ImportExportPage"));
const BackupsPage = lazy(() => import("./features/backups/BackupsPage"));
const FeedsPage = lazy(() => import("./features/feeds/FeedsPage"));
const AdminPage = lazy(() => import("./features/admin/AdminPage"));

function RouteLoader() {
  return (
    <section className="page-section">
      <InlineLoading description="Loading..." />
    </section>
  );
}

function HomeRedirect() {
  return <Navigate to="/library" replace />;
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
          <Button kind="primary" size="sm" as={Link} to="/library">
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
        <Route path="library" element={<LibraryPage />} />
        <Route path="library/:id" element={<ArticlePage />} />
        <Route path="articles" element={<ArticlesPage />} />
        <Route path="submit" element={<SubmitPage />} />
        <Route path="preferences" element={<PreferencesPage />} />
        <Route
          path="search"
          element={<Suspense fallback={<RouteLoader />}><SearchPage /></Suspense>}
        />
        <Route
          path="collections"
          element={<Suspense fallback={<RouteLoader />}><CollectionsPage /></Suspense>}
        />
        <Route
          path="collections/:id"
          element={<Suspense fallback={<RouteLoader />}><CollectionsPage /></Suspense>}
        />
        <Route
          path="tags"
          element={<Suspense fallback={<RouteLoader />}><TagManagementPage /></Suspense>}
        />
        <Route
          path="webhooks"
          element={<Suspense fallback={<RouteLoader />}><WebhooksPage /></Suspense>}
        />
        <Route
          path="rules"
          element={<Suspense fallback={<RouteLoader />}><RulesPage /></Suspense>}
        />
        <Route
          path="import-export"
          element={<Suspense fallback={<RouteLoader />}><ImportExportPage /></Suspense>}
        />
        <Route
          path="backups"
          element={<Suspense fallback={<RouteLoader />}><BackupsPage /></Suspense>}
        />
        <Route
          path="feeds"
          element={<Suspense fallback={<RouteLoader />}><FeedsPage /></Suspense>}
        />
        <Route
          path="digest"
          element={<Suspense fallback={<RouteLoader />}><DigestPage /></Suspense>}
        />
        <Route
          path="digest/custom/:id"
          element={<Suspense fallback={<RouteLoader />}><CustomDigestViewPage /></Suspense>}
        />
        {FEATURE_FLAGS.admin && (
          <Route
            path="admin"
            element={<Suspense fallback={<RouteLoader />}><AdminPage /></Suspense>}
          />
        )}
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
