---
name: carbon-design-system
description: >
  DEPRECATED: Carbon was removed from clients/web/ in favor of a project-owned
  design shim under clients/web/src/design/. This skill is retained for
  historical reference only — do not auto-trigger on new web work. For active
  web frontend guidance see the `developing-web-frontend` skill.
version: 1.2.0-deprecated
allowed-tools: Bash, Read, Grep
---

# Carbon Design System

Use IBM Carbon correctly in the `clients/web/` frontend. This skill covers component selection, theming, layout, motion rules, and accessibility patterns specific to this project.

## Dynamic Context

!cd clients/web && node -e "const p=JSON.parse(require('fs').readFileSync('package.json','utf8'));console.log('@carbon/react:',p.dependencies['@carbon/react'],'| @carbon/styles:',p.dependencies['@carbon/styles'],'| @carbon/icons-react:',p.dependencies['@carbon/icons-react'])"

See also: [references/component-catalog.md](references/component-catalog.md)

## Skill Precedence

When `emil-design-eng` and this skill conflict, **this skill wins for any `@carbon/react` component**. Emil's animation and interaction principles apply only to custom, non-Carbon UI elements.

## Import Conventions

| What | Import from | Notes |
|---|---|---|
| UI components | `@carbon/react` | Named imports only, no defaults |
| Icons | `@carbon/icons-react` | Named imports; icons accept `size` prop (16/20/24/32) |
| Global styles | `@carbon/styles/css/styles.css` | Imported once in `clients/web/src/main.tsx`; must precede project `styles.css` |

```tsx
import { Button, DataTable, Tile } from "@carbon/react";
import { Add, TrashCan } from "@carbon/icons-react";
```

## Theme System

Two themes are in use: `white` (light) and `g100` (dark Carbon gray-100).

**Runtime selection** in `clients/web/src/components/AppShell.tsx`:

- In `telegram-webapp` mode: follows `window.Telegram.WebApp.colorScheme` (`"dark"` -> `g100`, `"light"` -> `white`)
- In `jwt` mode: always `white`
- Listens to Telegram `themeChanged` events; updates dynamically

```tsx
<Theme theme={theme}>...</Theme>  // theme: "white" | "g100"
```

**Design tokens** — always use `--cds-*` CSS custom properties; never use raw hex/rgb:

| Token | Usage |
|---|---|
| `--cds-background` | Page background |
| `--cds-text-primary` | Primary body text |
| `--cds-text-secondary` | Muted/secondary text |
| `--cds-layer-accent-01` | Accent surface (cards, code blocks) |
| `--cds-border-subtle-01` | Light borders, dividers |
| `--cds-focus` | Focus rings on custom elements |
| `--cds-interactive` | Interactive element accents |
| `--cds-support-error` | Error states |
| `--cds-support-success` | Success states |
| `--cds-support-warning` | Warning states |

Token values differ between `white` and `g100` themes. Don't hardcode values.

## Layout System

- Page structure: `<Header>` + `<SideNav>` + `<Content>` — all wired in `clients/web/src/components/AppShell.tsx`
- Use `<Grid>` + `<Column>` from `@carbon/react` for multi-column page layouts
- Existing project pattern for feature pages: `<section className="page-section">` with CSS grid — maintain this
- Don't mix Carbon `<Grid>/<Column>` with CSS grid at the same layout level

## Spacing

Carbon spacing scale (use these values, not arbitrary px):

| Scale | Value | CSS var |
|---|---|---|
| `$spacing-01` | 2px | `--cds-spacing-01` |
| `$spacing-03` | 8px | `--cds-spacing-03` |
| `$spacing-05` | 16px | `--cds-spacing-05` |
| `$spacing-06` | 24px | `--cds-spacing-06` |
| `$spacing-07` | 32px | `--cds-spacing-07` |

## Component Selection Guide

| UI Pattern | Carbon Component | Notes |
|---|---|---|
| Paginated data list | `DataTable` + `Table*` family | Requires render prop pattern; see LibraryPage |
| Loading (table) | `DataTableSkeleton` | Match `columnCount` / `rowCount` to real table |
| Loading (inline) | `InlineLoading` | For buttons, small sections |
| Loading (text) | `SkeletonText` | For text placeholder blocks |
| Error/warning/info | `InlineNotification` | `kind`: error, warning, success, info |
| Card/container | `Tile` | Default surface container for forms, details |
| Tabs | `Tabs + TabList + Tab + TabPanels + TabPanel` | Use `contained` prop on `TabList` for page tabs |
| Pagination | `Pagination` | Standard; pairs with `DataTable` |
| Dropdown select | `Select + SelectItem` | Carbon-styled; prefer over native `<select>` |
| Multi-select | `MultiSelect` | Built-in filter; used in SearchPage |
| Dropdown menu | `Dropdown` | Single-select with label |
| Tag/chip | `Tag` | `type` controls color; never apply custom bg |
| Button group | `ButtonSet` | Horizontal bar; use `isExpressive` sparingly |
| Modal (simple) | `Modal` | For single action dialogs |
| Modal (complex) | `ComposedModal + ModalHeader + ModalBody + ModalFooter` | Full control; used in DigestPage |
| Search input | `Search` | Carbon-styled search field |
| Text input | `TextInput` | Standard Carbon text field |
| Number input | `NumberInput` | Stepper; used in preferences/search |
| Time picker | `TimePicker` | Used in PreferencesPage for delivery time |
| Shell layout | `Header + SideNav + SideNavItems + SideNavLink + Content` | Already in AppShell |
| Skip to content | `SkipToContent` | Accessibility; already in AppShell |
| Expandable rows | `TableExpandHeader + TableExpandRow + TableExpandedRow` | Used in DigestPage |
| Row select | `TableSelectAll + TableSelectRow` | Batch selection; used in DigestPage |
| Batch actions | `TableBatchActions + TableBatchAction` | Shows on row selection |
| Tree/hierarchy | `TreeView + TreeNode` | Used in CollectionsPage |
| Key-value list | `StructuredListWrapper + StructuredListHead + StructuredListBody + StructuredListRow + StructuredListCell` | Used in AdminPage for DB info |
| Progress indicator | `ProgressBar` | Linear; used in ArticlePage for audio |

## Motion and Animation Rules

Carbon owns animation for its components. Do not override it.

- Never apply `transition`, `animation`, or `:active { transform }` to Carbon components (`<Button>`, `<Tag>`, etc.) — they have built-in press feedback
- Don't use Framer Motion — this project has no animation library; use CSS transitions on custom elements
- For custom (non-Carbon) elements: `transition: transform 200ms ease-out` is the safe default
- Always add `@media (prefers-reduced-motion: reduce)` guards for custom animations
- Carbon handles reduced motion for its own components automatically

## Accessibility

- Carbon ships with correct ARIA attributes — never remove or override them
- Custom interactive elements need: `role`, `tabIndex={0}`, `aria-label`, `onKeyDown` handler
- Focus ring pattern for custom elements: `outline: 2px solid var(--cds-focus)`
- Existing clickable row pattern (LibraryPage): `role="link"` + `tabIndex={0}` + `onKeyDown` for Enter/Space
- Use `screen.getByRole` / `screen.getByText` in tests — not test IDs

## Common Pitfalls

- `DataTable` **requires a render prop** — it doesn't accept direct children
- `@carbon/styles/css/styles.css` must be imported **before** `clients/web/src/styles.css`
- Carbon tokens are theme-dependent — they resolve differently under `white` vs `g100`
- `Tag` type controls color; `type="blue"` for informational, `type="red"` for errors — never override with custom CSS backgrounds
- `VITE_` prefix required for env vars exposed to client code
- Theme wrapper (`<Theme>`) must be an ancestor of all Carbon components that use tokens

## Key Files

| File | Role |
|---|---|
| `clients/web/src/main.tsx` | Global Carbon styles import, Telegram theme sync bootstrap |
| `clients/web/src/components/AppShell.tsx` | Shell layout, theme switching, nav, BackButton |
| `clients/web/src/styles.css` | Custom CSS using `--cds-*` tokens and Telegram safe area vars |
| `clients/web/src/features/library/LibraryPage.tsx` | Reference: DataTable, Pagination, Tag, filter chips |
| `clients/web/src/features/article/ArticlePage.tsx` | Reference: Tabs, Tile, ProgressBar, Select, ButtonSet |
| `clients/web/src/features/digest/DigestPage.tsx` | Reference: ComposedModal, TableExpand, TableSelect, Dropdown |
| `clients/web/src/features/collections/CollectionsPage.tsx` | Reference: TreeView, TreeNode, Modal |
| `clients/web/src/features/admin/AdminPage.tsx` | Reference: StructuredList |
