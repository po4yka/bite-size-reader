import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { InlineLoading, InlineNotification } from "@carbon/react";
import { useAuth } from "./auth/AuthProvider";
import LoginPage from "./auth/LoginPage";
import { sanitizeRedirectPath } from "./auth/redirect";
import RouteGuard from "./auth/RouteGuard";
import AppShell from "./components/AppShell";
import ArticlePage from "./features/article/ArticlePage";
import ArticlesPage from "./features/articles/ArticlesPage";
import CollectionsPage from "./features/collections/CollectionsPage";
import DigestPage from "./features/digest/DigestPage";
import LibraryPage from "./features/library/LibraryPage";
import PreferencesPage from "./features/preferences/PreferencesPage";
import SearchPage from "./features/search/SearchPage";
import SubmitPage from "./features/submit/SubmitPage";
import { FEATURE_FLAGS } from "./routes/features";

function HomeRedirect() {
  return <Navigate to="/library" replace />;
}

function NotFoundPage() {
  return (
    <section className="page-section">
      <InlineNotification
        kind="warning"
        title="Page not found"
        subtitle="This route does not exist in Web V1."
        hideCloseButton
      />
    </section>
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
        <Route path="search" element={<SearchPage />} />
        <Route path="submit" element={<SubmitPage />} />
        <Route path="collections" element={<CollectionsPage />} />
        <Route path="collections/:id" element={<CollectionsPage />} />
        <Route path="digest" element={<DigestPage />} />
        <Route path="preferences" element={<PreferencesPage />} />
        {FEATURE_FLAGS.admin && <Route path="admin" element={<NotFoundPage />} />}
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
