import { Navigate, Route, Routes } from "react-router-dom";
import { InlineNotification } from "@carbon/react";
import { useAuth } from "./auth/AuthProvider";
import LoginPage from "./auth/LoginPage";
import RouteGuard from "./auth/RouteGuard";
import AppShell from "./components/AppShell";
import ArticlePage from "./features/article/ArticlePage";
import CollectionsPage from "./features/collections/CollectionsPage";
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
  const { mode, status } = useAuth();

  if (mode === "telegram-webapp") {
    return <Navigate to="/library" replace />;
  }

  if (status === "authenticated") {
    return <Navigate to="/library" replace />;
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
        <Route path="search" element={<SearchPage />} />
        <Route path="submit" element={<SubmitPage />} />
        <Route path="collections" element={<CollectionsPage />} />
        <Route path="collections/:id" element={<CollectionsPage />} />
        <Route path="preferences" element={<PreferencesPage />} />

        {FEATURE_FLAGS.digest && <Route path="digest" element={<NotFoundPage />} />}
        {FEATURE_FLAGS.admin && <Route path="admin" element={<NotFoundPage />} />}
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
