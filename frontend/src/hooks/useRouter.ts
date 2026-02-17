import { useCallback, useEffect, useState } from "react";

export type Route =
  | { page: "library"; articleId?: number }
  | { page: "search" }
  | { page: "submit" }
  | { page: "collections"; collectionId?: number }
  | { page: "more"; sub?: "digest" | "profile" | "stats" | "preferences" | "admin" };

function parseHash(): Route {
  const hash = window.location.hash.slice(1) || "library";
  const parts = hash.split("/");
  const page = parts[0];

  switch (page) {
    case "library":
      return parts[1] ? { page: "library", articleId: Number(parts[1]) } : { page: "library" };
    case "search":
      return { page: "search" };
    case "submit":
      return { page: "submit" };
    case "collections":
      return parts[1]
        ? { page: "collections", collectionId: Number(parts[1]) }
        : { page: "collections" };
    case "more": {
      const sub = (parts[1] || undefined) as "digest" | "profile" | "stats" | "preferences" | "admin" | undefined;
      return { page: "more", sub };
    }
    default:
      return { page: "library" };
  }
}

function routeToHash(route: Route): string {
  switch (route.page) {
    case "library":
      return route.articleId ? `library/${route.articleId}` : "library";
    case "search":
      return "search";
    case "submit":
      return "submit";
    case "collections":
      return route.collectionId ? `collections/${route.collectionId}` : "collections";
    case "more":
      return route.sub ? `more/${route.sub}` : "more";
  }
}

export function useRouter() {
  const [route, setRouteState] = useState<Route>(parseHash);

  useEffect(() => {
    const onHashChange = () => setRouteState(parseHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((r: Route) => {
    window.location.hash = routeToHash(r);
  }, []);

  const goBack = useCallback(() => {
    // Navigate to parent level
    if (route.page === "library" && route.articleId) {
      navigate({ page: "library" });
    } else if (route.page === "collections" && route.collectionId) {
      navigate({ page: "collections" });
    } else if (route.page === "more" && route.sub) {
      navigate({ page: "more" });
    } else {
      navigate({ page: "library" });
    }
  }, [route, navigate]);

  const isSubPage =
    (route.page === "library" && !!route.articleId) ||
    (route.page === "collections" && !!route.collectionId) ||
    (route.page === "more" && !!route.sub);

  return { route, navigate, goBack, isSubPage };
}
