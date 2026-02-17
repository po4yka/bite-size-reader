import { useEffect } from "react";
import { useTelegram } from "./hooks/useTelegram";
import { useRouter } from "./hooks/useRouter";
import BottomNav from "./components/common/BottomNav";
import LoadingSpinner from "./components/common/LoadingSpinner";
import ArticleList from "./components/library/ArticleList";
import ArticleDetail from "./components/library/ArticleDetail";
import SearchPage from "./components/search/SearchPage";
import SubmitForm from "./components/submit/SubmitForm";
import CollectionTree from "./components/collections/CollectionTree";
import CollectionDetail from "./components/collections/CollectionDetail";
import MorePage from "./components/more/MorePage";

export default function App() {
  const { user } = useTelegram();
  const { route, navigate, goBack, isSubPage } = useRouter();

  // Telegram BackButton integration
  useEffect(() => {
    const bb = window.Telegram?.WebApp?.BackButton;
    if (!bb) return;

    if (isSubPage) {
      bb.show();
      bb.onClick(goBack);
      return () => {
        bb.offClick(goBack);
        bb.hide();
      };
    } else {
      bb.hide();
    }
  }, [isSubPage, goBack]);

  if (!user) {
    return <LoadingSpinner text="Connecting to Telegram..." />;
  }

  const renderPage = () => {
    switch (route.page) {
      case "library":
        if (route.articleId) {
          return <ArticleDetail articleId={route.articleId} onBack={goBack} />;
        }
        return <ArticleList onArticleClick={(id) => navigate({ page: "library", articleId: id })} />;

      case "search":
        return (
          <SearchPage
            onArticleClick={(id) => navigate({ page: "library", articleId: id })}
          />
        );

      case "submit":
        return (
          <SubmitForm
            onViewArticle={(id) => navigate({ page: "library", articleId: id })}
          />
        );

      case "collections":
        if (route.collectionId) {
          return (
            <CollectionDetail
              collectionId={route.collectionId}
              onArticleClick={(id) => navigate({ page: "library", articleId: id })}
              onBack={goBack}
            />
          );
        }
        return (
          <CollectionTree
            onCollectionClick={(id) => navigate({ page: "collections", collectionId: id })}
          />
        );

      case "more":
        return <MorePage sub={route.sub} onNavigate={navigate} />;

      default:
        return <ArticleList onArticleClick={(id) => navigate({ page: "library", articleId: id })} />;
    }
  };

  return (
    <div className="app">
      <main className="content">{renderPage()}</main>
      <BottomNav activePage={route.page} onNavigate={navigate} />
    </div>
  );
}
