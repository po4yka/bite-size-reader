import { lazy, Suspense, useEffect } from "react";
import { useTelegram } from "./hooks/useTelegram";
import { useRouter } from "./hooks/useRouter";
import { ToastContext, useToastState } from "./hooks/useToast";
import ErrorBoundary from "./components/common/ErrorBoundary";
import BottomNav from "./components/common/BottomNav";
import ToastContainer from "./components/common/Toast";
import LoadingSpinner from "./components/common/LoadingSpinner";
import LoadingSkeleton from "./components/common/LoadingSkeleton";

// Eagerly loaded (initial view)
import ArticleList from "./components/library/ArticleList";

// Lazy-loaded pages
const ArticleDetail = lazy(() => import("./components/library/ArticleDetail"));
const SearchPage = lazy(() => import("./components/search/SearchPage"));
const SubmitForm = lazy(() => import("./components/submit/SubmitForm"));
const CollectionTree = lazy(() => import("./components/collections/CollectionTree"));
const CollectionDetail = lazy(() => import("./components/collections/CollectionDetail"));
const MorePage = lazy(() => import("./components/more/MorePage"));

function AppContent() {
  const { user, webApp } = useTelegram();
  const { route, navigate, goBack, isSubPage } = useRouter();

  // Disable vertical swipes to prevent accidental close during scroll
  useEffect(() => {
    if (webApp?.isVersionAtLeast?.("7.7")) {
      webApp.disableVerticalSwipes();
    }
  }, [webApp]);

  // Dynamic header color based on navigation depth
  useEffect(() => {
    if (!webApp?.setHeaderColor) return;
    webApp.setHeaderColor(isSubPage ? "secondary_bg_color" : "bg_color");
  }, [isSubPage, webApp]);

  // SettingsButton -> Admin
  useEffect(() => {
    const btn = webApp?.SettingsButton;
    if (!btn) return;
    btn.show();
    const handler = () => navigate({ page: "more", sub: "admin" });
    btn.onClick(handler);
    return () => {
      btn.offClick(handler);
      btn.hide();
    };
  }, [webApp, navigate]);

  // Telegram BackButton integration
  useEffect(() => {
    const bb = webApp?.BackButton;
    if (!bb) return;
    if (isSubPage) {
      bb.show();
      bb.onClick(goBack);
      return () => { bb.offClick(goBack); bb.hide(); };
    } else {
      bb.hide();
    }
  }, [isSubPage, goBack, webApp]);

  if (!user) return <LoadingSpinner text="Connecting to Telegram..." />;

  const renderPage = () => {
    switch (route.page) {
      case "library":
        if (route.articleId)
          return <ArticleDetail articleId={route.articleId} onBack={goBack} />;
        return <ArticleList onArticleClick={(id) => navigate({ page: "library", articleId: id })} />;
      case "search":
        return <SearchPage onArticleClick={(id) => navigate({ page: "library", articleId: id })} />;
      case "submit":
        return <SubmitForm onViewArticle={(id) => navigate({ page: "library", articleId: id })} />;
      case "collections":
        if (route.collectionId)
          return <CollectionDetail collectionId={route.collectionId}
            onArticleClick={(id) => navigate({ page: "library", articleId: id })}
            onBack={goBack} />;
        return <CollectionTree onCollectionClick={(id) => navigate({ page: "collections", collectionId: id })} />;
      case "more":
        return <MorePage sub={route.sub} onNavigate={navigate} />;
      default:
        return <ArticleList onArticleClick={(id) => navigate({ page: "library", articleId: id })} />;
    }
  };

  return (
    <div className="app">
      <main className="content" aria-live="polite">
        <Suspense fallback={<LoadingSkeleton count={4} />}>
          {renderPage()}
        </Suspense>
      </main>
      <BottomNav activePage={route.page} onNavigate={navigate} />
    </div>
  );
}

export default function App() {
  const toast = useToastState();

  return (
    <ErrorBoundary>
      <ToastContext.Provider value={toast}>
        <AppContent />
        <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
      </ToastContext.Provider>
    </ErrorBoundary>
  );
}
