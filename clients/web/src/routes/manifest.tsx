import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { FeatureFlag } from "./features";
import { isFeatureEnabled } from "./features";
import {
  Add,
  Book,
  Catalog,
  ConnectionSignal,
  DataBackup,
  DocumentImport,
  Lightning,
  Notification,
  Rss,
  SearchIcon,
  Settings,
  TagIcon,
  User,
} from "../design";
import ArticlePage from "../features/article/ArticlePage";
import ArticlesPage from "../features/articles/ArticlesPage";
import LibraryPage from "../features/library/LibraryPage";
import PreferencesPage from "../features/preferences/PreferencesPage";
import SubmitPage from "../features/submit/SubmitPage";

const CollectionsPage = lazy(() => import("../features/collections/CollectionsPage"));
const DigestPage = lazy(() => import("../features/digest/DigestPage"));
const CustomDigestViewPage = lazy(() => import("../features/digest/CustomDigestViewPage"));
const SearchPage = lazy(() => import("../features/search/SearchPage"));
const SignalsPage = lazy(() => import("../features/signals/SignalsPage"));
const TagManagementPage = lazy(() => import("../features/tags/TagManagementPage"));
const WebhooksPage = lazy(() => import("../features/webhooks/WebhooksPage"));
const RulesPage = lazy(() => import("../features/rules/RulesPage"));
const ImportExportPage = lazy(() => import("../features/import-export/ImportExportPage"));
const BackupsPage = lazy(() => import("../features/backups/BackupsPage"));
const FeedsPage = lazy(() => import("../features/feeds/FeedsPage"));
const AdminPage = lazy(() => import("../features/admin/AdminPage"));

type AppRouteComponent = ComponentType | LazyExoticComponent<ComponentType>;
type NavIcon = typeof Book;

export interface NavRouteItem {
  readonly path: string;
  readonly label: string;
  readonly icon: NavIcon;
}

interface AppRouteDefinition {
  readonly path: string;
  readonly component: AppRouteComponent;
  readonly lazy?: boolean;
  readonly featureFlag?: FeatureFlag;
  readonly nav?: {
    readonly label: string;
    readonly icon: NavIcon;
    readonly group: number;
  };
}

const APP_ROUTE_DEFINITIONS: readonly AppRouteDefinition[] = [
  {
    path: "library",
    component: LibraryPage,
    nav: { label: "Library", icon: Book, group: 0 },
  },
  {
    path: "library/:id",
    component: ArticlePage,
  },
  {
    path: "articles",
    component: ArticlesPage,
    nav: { label: "Articles", icon: Book, group: 0 },
  },
  {
    path: "submit",
    component: SubmitPage,
    nav: { label: "Submit", icon: Add, group: 0 },
  },
  {
    path: "preferences",
    component: PreferencesPage,
    nav: { label: "Preferences", icon: User, group: 3 },
  },
  {
    path: "search",
    component: SearchPage,
    lazy: true,
    nav: { label: "Search", icon: SearchIcon, group: 0 },
  },
  {
    path: "collections",
    component: CollectionsPage,
    lazy: true,
    nav: { label: "Collections", icon: Catalog, group: 1 },
  },
  {
    path: "collections/:id",
    component: CollectionsPage,
    lazy: true,
  },
  {
    path: "tags",
    component: TagManagementPage,
    lazy: true,
    nav: { label: "Tags", icon: TagIcon, group: 1 },
  },
  {
    path: "webhooks",
    component: WebhooksPage,
    lazy: true,
    nav: { label: "Webhooks", icon: ConnectionSignal, group: 2 },
  },
  {
    path: "rules",
    component: RulesPage,
    lazy: true,
    nav: { label: "Rules", icon: Lightning, group: 2 },
  },
  {
    path: "import-export",
    component: ImportExportPage,
    lazy: true,
    nav: { label: "Import/Export", icon: DocumentImport, group: 3 },
  },
  {
    path: "backups",
    component: BackupsPage,
    lazy: true,
    nav: { label: "Backups", icon: DataBackup, group: 3 },
  },
  {
    path: "feeds",
    component: FeedsPage,
    lazy: true,
    nav: { label: "Feeds", icon: Rss, group: 1 },
  },
  {
    path: "signals",
    component: SignalsPage,
    lazy: true,
    nav: { label: "Signals", icon: ConnectionSignal, group: 1 },
  },
  {
    path: "digest",
    component: DigestPage,
    lazy: true,
    featureFlag: "digest",
    nav: { label: "Digest", icon: Notification, group: 2 },
  },
  {
    path: "digest/custom/:id",
    component: CustomDigestViewPage,
    lazy: true,
    featureFlag: "digest",
  },
  {
    path: "admin",
    component: AdminPage,
    lazy: true,
    featureFlag: "admin",
    nav: { label: "Admin", icon: Settings, group: 4 },
  },
] as const;

export const HOME_PATH = "/library";

export function isRouteEnabled(route: AppRouteDefinition): boolean {
  return isFeatureEnabled(route.featureFlag);
}

export const ENABLED_APP_ROUTES = APP_ROUTE_DEFINITIONS.filter(isRouteEnabled);

const navRoutes = ENABLED_APP_ROUTES.filter(
  (route): route is AppRouteDefinition & { nav: NonNullable<AppRouteDefinition["nav"]> } =>
    route.nav !== undefined,
);

export const NAV_GROUPS: readonly (readonly NavRouteItem[])[] = Array.from(
  navRoutes.reduce((groups, route) => {
    const group = groups.get(route.nav.group) ?? [];
    group.push({
      path: `/${route.path}`,
      label: route.nav.label,
      icon: route.nav.icon,
    });
    groups.set(route.nav.group, group);
    return groups;
  }, new Map<number, NavRouteItem[]>()),
)
  .sort(([left], [right]) => left - right)
  .map(([, routes]) => routes);

export const NAV_ROOT_PATHS: ReadonlySet<string> = new Set(
  navRoutes.map((route) => `/${route.path}`),
);
