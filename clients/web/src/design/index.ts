/*
 * Project-owned design system. Re-exports primitives, navigation widgets,
 * tables, modals, and icons from this directory. Feature code imports from
 * `../design` exclusively — the shim implementations underneath are plain
 * HTML+CSS+TSX and contain no third-party design system dependencies.
 */

import "./fonts.css";
import "./tokens.css";
import "./base.css";
import "./mobile.css";

// ── In-place rewrites (Phase 2) — same filename, Frost shape ──────────────────

// Primitives
export { IconButton } from "./primitives/IconButton";
export type { IconButtonProps } from "./primitives/IconButton";
export { Tag } from "./primitives/Tag";
export type { TagProps, TagType, TagSize } from "./primitives/Tag";
export { Link } from "./primitives/Link";
export type { LinkProps } from "./primitives/Link";
export { NumberInput } from "./primitives/NumberInput";
export type { NumberInputProps } from "./primitives/NumberInput";
export { Checkbox } from "./primitives/Checkbox";
export type { CheckboxProps } from "./primitives/Checkbox";
export { RadioButton, RadioButtonGroup } from "./primitives/RadioButton";
export type {
  RadioButtonProps,
  RadioButtonGroupProps,
} from "./primitives/RadioButton";
export { Toggle } from "./primitives/Toggle";
export type { ToggleProps } from "./primitives/Toggle";
export { CodeSnippet } from "./primitives/CodeSnippet";
export type { CodeSnippetProps } from "./primitives/CodeSnippet";
export { FileUploader } from "./primitives/FileUploader";
export type { FileUploaderProps } from "./primitives/FileUploader";
export { UnorderedList, ListItem } from "./primitives/UnorderedList";
export type {
  UnorderedListProps,
  ListItemProps,
} from "./primitives/UnorderedList";
export { Accordion, AccordionItem } from "./primitives/Accordion";
export type { AccordionProps, AccordionItemProps } from "./primitives/Accordion";

// Navigation (in-place rewrites)
export { TreeView, TreeNode } from "./navigation/TreeView";
export type { TreeViewProps, TreeNodeProps } from "./navigation/TreeView";
export { ContentSwitcher, Switch } from "./navigation/ContentSwitcher";
export type {
  ContentSwitcherProps,
  SwitchProps,
} from "./navigation/ContentSwitcher";

// Table primitives (Table/TableContainer/TableHead/TableBody/TableRow/TableCell/
// TableHeader) — preserved because BrutalistTable's render-props API
// (getTableProps/getHeaderProps/getRowProps) composes with these sub-components
// throughout feature pages. Kept until BrutalistTable absorbs the lower-level
// composition or pages are rewritten to use a different pattern.
export {
  Table,
  TableContainer,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableHeader,
} from "./table/Table";
export type {
  TableProps,
  TableContainerProps,
  TableRowProps,
  TableCellProps,
  TableHeaderProps,
} from "./table/Table";

// Multiselect / Dropdown (in-place rewrites)
export { MultiSelect, FilterableMultiSelect } from "./multiselect/MultiSelect";
export type { MultiSelectProps } from "./multiselect/MultiSelect";
export { Dropdown } from "./multiselect/Dropdown";
export type { DropdownProps } from "./multiselect/Dropdown";

// Pickers (in-place rewrites)
export { DatePicker, DatePickerInput } from "./pickers/DatePicker";
export type {
  DatePickerProps,
  DatePickerInputProps,
  DatePickerType,
} from "./pickers/DatePicker";
export { TimePicker } from "./pickers/TimePicker";
export type { TimePickerProps } from "./pickers/TimePicker";

// Shell (in-place rewrites)
export { Content } from "./shell/AppContent";
export type { ContentProps } from "./shell/AppContent";
export { Theme } from "./shell/Theme";
export type { ThemeProps, ThemeName } from "./shell/Theme";

// Icons (re-exported from `./icons` as named symbols)
export {
  Add,
  Book,
  Catalog,
  Checkmark,
  Close,
  ConnectionSignal,
  DataBackup,
  DocumentImport,
  Edit,
  Lightning,
  Logout,
  Notification,
  PauseFilled,
  Play,
  Renew,
  Rss,
  SearchIcon,
  Settings,
  StopFilled,
  TagIcon,
  TrashCan,
  User,
} from "./icons";
export type { IconProps } from "./icons";

// =============================================================================
// Frost components (Phase 2 of the Frost migration)
// =============================================================================

// Frost primitives
export { BracketButton } from "./primitives/BracketButton";
export type {
  BracketButtonProps,
  BracketButtonKind,
  BracketButtonSize,
} from "./primitives/BracketButton";

export { BracketSearch } from "./primitives/BracketSearch";
export type { BracketSearchProps } from "./primitives/BracketSearch";

export { BrutalistCard } from "./primitives/BrutalistCard";
export type { BrutalistCardProps } from "./primitives/BrutalistCard";

export {
  BrutalistSkeleton,
  BrutalistSkeletonText,
  BrutalistSkeletonPlaceholder,
  BrutalistDataTableSkeleton,
} from "./primitives/BrutalistSkeleton";
export type {
  BrutalistSkeletonProps,
  BrutalistSkeletonTextProps,
  BrutalistSkeletonPlaceholderProps,
  BrutalistDataTableSkeletonProps,
} from "./primitives/BrutalistSkeleton";

export { MonoInput } from "./primitives/MonoInput";
export type { MonoInputProps } from "./primitives/MonoInput";

export { MonoProgressBar } from "./primitives/MonoProgressBar";
export type {
  MonoProgressBarProps,
  MonoProgressBarStatus,
} from "./primitives/MonoProgressBar";

export { MonoSelect, MonoSelectItem } from "./primitives/MonoSelect";
export type {
  MonoSelectProps,
  MonoSelectItemProps,
} from "./primitives/MonoSelect";

export { MonoTextArea } from "./primitives/MonoTextArea";
export type { MonoTextAreaProps } from "./primitives/MonoTextArea";

export { SparkLoading } from "./primitives/SparkLoading";
export type {
  SparkLoadingProps,
  SparkLoadingStatus,
} from "./primitives/SparkLoading";

export { StatusBadge } from "./primitives/StatusBadge";
export type {
  StatusBadgeProps,
  StatusBadgeSeverity,
} from "./primitives/StatusBadge";

export { Toast } from "./primitives/Toast";
export type {
  ToastProps,
  ToastSeverity,
  ToastPosition,
} from "./primitives/Toast";

// Frost navigation
export {
  BracketTabs,
  BracketTabList,
  BracketTab,
  BracketTabPanels,
  BracketTabPanel,
} from "./navigation/BracketTabs";
export type {
  BracketTabsProps,
  BracketTabListProps,
  BracketTabProps,
  BracketTabPanelsProps,
  BracketTabPanelProps,
} from "./navigation/BracketTabs";

export { BracketPagination } from "./navigation/BracketPagination";
export type {
  BracketPaginationProps,
  BracketPaginationChangeEvent,
} from "./navigation/BracketPagination";

// Frost table
export {
  DataTable as BrutalistTable,
  TableContainer as BrutalistTableContainer,
} from "./table/BrutalistTable";
export type {
  DataTableProps as BrutalistTableProps,
  DataTableHeader as BrutalistTableHeader,
  DataTableRow as BrutalistTableRow,
  DataTableRowInput as BrutalistTableRowInput,
  DataTableCell as BrutalistTableCell,
  DataTableRenderProps as BrutalistTableRenderProps,
  DataTableSortDirection as BrutalistTableSortDirection,
  TableContainerProps as BrutalistTableContainerProps,
} from "./table/BrutalistTable";

// Frost modal
export { BrutalistModal } from "./modal/BrutalistModal";
export type { BrutalistModalProps } from "./modal/BrutalistModal";
export {
  ModalHeader as BrutalistModalHeader,
  ModalBody as BrutalistModalBody,
  ModalFooter as BrutalistModalFooter,
} from "./modal/BrutalistModal";
export type {
  ModalHeaderProps as BrutalistModalHeaderProps,
  ModalBodyProps as BrutalistModalBodyProps,
  ModalFooterProps as BrutalistModalFooterProps,
} from "./modal/BrutalistModal";

// Frost structure
export {
  RowDigestWrapper,
  RowDigestHead,
  RowDigestBody,
  RowDigestRow,
  RowDigestCell,
} from "./structure/RowDigest";

// Frost shell
export {
  FrostHeader,
  FrostHeaderName,
  FrostHeaderMenuButton,
  FrostHeaderGlobalBar,
  FrostHeaderGlobalAction,
  FrostSkipToContent,
  // Back-compat alias: AppShell imports SkipToContent
  FrostSkipToContent as SkipToContent,
} from "./shell/FrostHeader";
export type {
  FrostHeaderProps,
  FrostHeaderNameProps,
  FrostHeaderMenuButtonProps,
  FrostHeaderGlobalBarProps,
  FrostHeaderGlobalActionProps,
} from "./shell/FrostHeader";

export {
  FrostSideNav,
  FrostSideNavItems,
  FrostSideNavLink,
  FrostSideNavDivider,
} from "./shell/FrostSideNav";
export type {
  FrostSideNavProps,
  FrostSideNavItemsProps,
  FrostSideNavLinkProps,
} from "./shell/FrostSideNav";

// =============================================================================
// Back-compat aliases — Phase 4b sweep
// Files that still use legacy names get these re-exports so we can migrate
// import sites file-by-file without touching every file in this commit.
// =============================================================================

// Button → BracketButton
export {
  BracketButton as Button,
} from "./primitives/BracketButton";

// Tile → BrutalistCard
export {
  BrutalistCard as Tile,
} from "./primitives/BrutalistCard";

// TextInput → MonoInput
export {
  MonoInput as TextInput,
} from "./primitives/MonoInput";

// TextArea → MonoTextArea
export {
  MonoTextArea as TextArea,
} from "./primitives/MonoTextArea";

// Select → MonoSelect, SelectItem → MonoSelectItem
export {
  MonoSelect as Select,
  MonoSelectItem as SelectItem,
} from "./primitives/MonoSelect";

// SkeletonText → BrutalistSkeletonText
export {
  BrutalistSkeletonText as SkeletonText,
} from "./primitives/BrutalistSkeleton";

// InlineLoading → SparkLoading (description prop is compatible)
export {
  SparkLoading as InlineLoading,
} from "./primitives/SparkLoading";

// DataTable → BrutalistTable (render-props API is identical)
export {
  DataTable as BrutalistTable2,
  DataTable,
} from "./table/BrutalistTable";
export type {
  DataTableProps,
  DataTableHeader,
  DataTableRow,
  DataTableRowInput,
  DataTableCell,
  DataTableRenderProps,
  DataTableSortDirection,
} from "./table/BrutalistTable";

// DataTableSkeleton → BrutalistDataTableSkeleton
export {
  BrutalistDataTableSkeleton as DataTableSkeleton,
} from "./primitives/BrutalistSkeleton";

// Pagination → BracketPagination
export {
  BracketPagination as Pagination,
} from "./navigation/BracketPagination";
export type {
  BracketPaginationChangeEvent as PaginationChangeEvent,
} from "./navigation/BracketPagination";

// Modal → BrutalistModal, ComposedModal → BrutalistModal
export {
  BrutalistModal as Modal,
  BrutalistModal as ComposedModal,
  ModalHeader as BrutalistModalHeader2,
  ModalHeader,
  ModalBody as BrutalistModalBody2,
  ModalBody,
  ModalFooter as BrutalistModalFooter2,
  ModalFooter,
} from "./modal/BrutalistModal";

// InlineNotification — thin shim mapping Carbon kind/subtitle to Frost severity/subtitle
export { InlineNotification } from "./primitives/InlineNotificationShim";
