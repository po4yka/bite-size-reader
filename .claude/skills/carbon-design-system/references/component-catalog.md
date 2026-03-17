# Carbon Component Catalog

All `@carbon/react` and `@carbon/icons-react` imports currently used in the project.
Update this file when adding new Carbon components.

## Components (`@carbon/react`)

| Component | Used In | Key Props / Notes |
|---|---|---|
| `Button` | AppShell, LoginPage, LibraryPage, ArticlePage, SearchPage, SubmitPage, DigestPage, AdminPage, PreferencesPage, CollectionsPage | `kind`: primary/secondary/danger/ghost/tertiary; `size`: sm/md/lg; `renderIcon` for icon+text |
| `ButtonSet` | ArticlePage | Groups 2-3 related buttons horizontally |
| `Content` | AppShell | Main page content wrapper; pairs with `Header + SideNav` |
| `ComposedModal` | DigestPage | Complex modal; composed with `ModalHeader`, `ModalBody`, `ModalFooter` |
| `DataTable` | LibraryPage, DigestPage, CollectionsPage, ArticlesPage | **Render prop required**; passes `rows`, `headers`, and table component props |
| `DataTableSkeleton` | LibraryPage, DigestPage, CollectionsPage, ArticlesPage | `columnCount`, `rowCount`, `showHeader`, `showToolbar` props |
| `Dropdown` | DigestPage | Single-select; `id`, `label`, `items`, `itemToString`, `onChange` |
| `Header` | AppShell | Top navigation bar; `aria-label` required |
| `HeaderGlobalAction` | AppShell | Icon button in global bar; `aria-label` required |
| `HeaderGlobalBar` | AppShell | Right-side action group in header |
| `HeaderMenuButton` | AppShell | Hamburger for SideNav toggle; `aria-label`, `isActive`, `onClick` |
| `HeaderName` | AppShell | App name/logo in header; `prefix` prop for brand name |
| `InlineLoading` | AppShell, AddToCollectionModal, SearchPage, SubmitPage, DigestPage, CollectionsPage, LoginPage | `status`: active/finished/error; `description` text |
| `InlineNotification` | (all pages) | `kind`: error/warning/success/info; `title`, `subtitle`; `lowContrast` for subtle style |
| `Modal` | AddToCollectionModal, CollectionsPage | `open`, `onRequestClose`, `primaryButtonText`, `secondaryButtonText`, `modalHeading` |
| `ModalBody` | DigestPage | Body slot for ComposedModal |
| `ModalFooter` | DigestPage | Footer slot with action buttons |
| `ModalHeader` | DigestPage | Header slot with title and close button |
| `MultiSelect` | SearchPage | `id`, `label`, `items`, `itemToString`, `onChange(selectedItems)` |
| `NumberInput` | SearchPage, DigestPage, PreferencesPage | `id`, `label`, `value`, `onChange`, `min`, `max`, `step` |
| `Pagination` | LibraryPage, SearchPage, DigestPage, ArticlesPage | `totalItems`, `pageSize`, `pageSizes`, `page`, `onChange({ page, pageSize })` |
| `ProgressBar` | ArticlePage | `value` (0-100), `max`, `label`, `helperText`, `status` |
| `Search` | SearchPage | `id`, `labelText`, `value`, `onChange`, `onClear` |
| `Select` | ArticlePage, SearchPage, SubmitPage, DigestPage, AdminPage (implicit), PreferencesPage, CollectionsPage, ArticlesPage | Wrap with `SelectItem` children; `id`, `labelText`, `onChange` |
| `SelectItem` | (with Select above) | `value`, `text` |
| `SideNav` | AppShell | `isRail` false by default; `expanded`, `onSideNavBlur`; wrap items in `SideNavItems` |
| `SideNavItems` | AppShell | Direct parent of `SideNavLink` components |
| `SideNavLink` | AppShell | `href` or use with `as={NavLink}` from react-router-dom; `renderIcon` |
| `SkeletonText` | SearchPage, AdminPage, PreferencesPage | `heading` for larger placeholder; `width`, `lineCount` |
| `SkipToContent` | AppShell | `href="#main-content"`; accessibility |
| `StructuredListBody` | AdminPage | Body of structured list |
| `StructuredListCell` | AdminPage | Cell within a structured list row |
| `StructuredListHead` | AdminPage | Header row of structured list |
| `StructuredListRow` | AdminPage | Row in structured list |
| `StructuredListWrapper` | AdminPage | Root container; `ariaLabel` required |
| `Tab` | ArticlePage, DigestPage | Tab item; `children` is label |
| `TabList` | ArticlePage, DigestPage | Tab bar container; `aria-label` required; `contained` for boxed style |
| `TabPanel` | ArticlePage, DigestPage | Content pane for each tab |
| `TabPanels` | ArticlePage, DigestPage | Container for all TabPanel children |
| `Tabs` | ArticlePage, DigestPage | Root; `selectedIndex` for controlled; `onChange` |
| `Tag` | LibraryPage, ArticlePage, SearchPage, DigestPage, ArticlesPage | `type`: blue/teal/cyan/gray/warm-gray/green/red/purple/cool-gray; `size`: sm/md; never override bg color |
| `TextInput` | AddToCollectionModal, SubmitPage, DigestPage, CollectionsPage | `id`, `labelText`, `value`, `onChange`, `invalid`, `invalidText` |
| `Theme` | AppShell | `theme`: "white" \| "g10" \| "g90" \| "g100"; wraps children |
| `Tile` | LoginPage, ArticlePage, SearchPage, SubmitPage, DigestPage, AdminPage, PreferencesPage | Default `<div>` surface; no interactive behavior by default |
| `TimePicker` | PreferencesPage | `id`, `labelText`, `value`, `onChange` |
| `TreeNode` | CollectionsPage | Leaf or branch; `id`, `label`, `value`, `renderIcon`, `isExpanded` |
| `TreeView` | CollectionsPage | `label` (accessible), `selected`, `active`, `onSelect` |
| `TableBatchAction` | DigestPage | Action button in batch actions bar; `renderIcon` |
| `TableBatchActions` | DigestPage | Bar shown on row selection; `totalSelected`, `onCancel` |
| `TableBody` | (all DataTable pages) | Wrap `TableRow` children |
| `TableCell` | (all DataTable pages) | Table cell; `children` |
| `TableContainer` | (all DataTable pages) | Outer wrapper; `title`, `description` |
| `TableExpandHeader` | DigestPage | Expand column header |
| `TableExpandRow` | DigestPage | Row with expand chevron; `isExpanded`, `onExpand` |
| `TableExpandedRow` | DigestPage | Content shown when row is expanded; `colSpan` matches column count |
| `TableHead` | (all DataTable pages) | Table header row container |
| `TableHeader` | (all DataTable pages) | Sortable column header; `isSortable`, `sortDirection`, `onClick` |
| `TableRow` | (all DataTable pages) | Standard table row |
| `TableSelectAll` | DigestPage | "Select all" checkbox in header |
| `TableSelectRow` | DigestPage | Per-row checkbox |
| `TableToolbar` | LibraryPage, DigestPage, ArticlesPage | Toolbar container above table |
| `TableToolbarContent` | LibraryPage, DigestPage, ArticlesPage | Right-aligned toolbar actions |
| `TableToolbarSearch` | LibraryPage, DigestPage, ArticlesPage | Inline search within toolbar |

## Icons (`@carbon/icons-react`)

| Icon | Used In | Notes |
|---|---|---|
| `Add` | AppShell | |
| `Book` | AppShell | Library and Articles nav items |
| `Catalog` | AppShell | (imported but check usage) |
| `Logout` | AppShell | |
| `Notification` | AppShell | |
| `Renew` | AppShell | Reload/refresh action |
| `Search` (as `SearchIcon`) | AppShell | Aliased to avoid conflict with `Search` component |
| `Settings` | AppShell | |
| `User` | AppShell | |
| `PauseFilled` | ArticlePage | Audio player pause |
| `Play` | ArticlePage | Audio player play |
| `StopFilled` | ArticlePage | Audio player stop |

## Notes

- Always pass `aria-label` to `HeaderGlobalAction` and icon-only buttons
- `DataTable` uses a render-prop pattern — the component provides `rows`, `headers`, and table sub-component props as function arguments
- `SideNavLink` should use `as={NavLink}` from `react-router-dom` to get active state styling
- `Theme` wrapper must be an ancestor of all components that read `--cds-*` tokens
