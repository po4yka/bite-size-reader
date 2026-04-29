/*
 * Project-owned design system. Re-exports primitives, navigation widgets,
 * tables, modals, and icons from this directory. Feature code imports from
 * `../design` exclusively — the shim implementations underneath are plain
 * HTML+CSS+TSX and contain no third-party design system dependencies.
 */

import "./tokens.css";
import "./base.css";

// Primitives
export { Button } from "./primitives/Button";
export type { ButtonProps, ButtonKind, ButtonSize } from "./primitives/Button";
export { ButtonSet } from "./primitives/ButtonSet";
export type { ButtonSetProps } from "./primitives/ButtonSet";
export { IconButton } from "./primitives/IconButton";
export type { IconButtonProps } from "./primitives/IconButton";
export { Tile } from "./primitives/Tile";
export type { TileProps } from "./primitives/Tile";
export { Tag } from "./primitives/Tag";
export type { TagProps, TagType, TagSize } from "./primitives/Tag";
export { Link } from "./primitives/Link";
export type { LinkProps } from "./primitives/Link";
export { TextInput } from "./primitives/TextInput";
export type { TextInputProps } from "./primitives/TextInput";
export { TextArea } from "./primitives/TextArea";
export type { TextAreaProps } from "./primitives/TextArea";
export { Select, SelectItem } from "./primitives/Select";
export type { SelectProps, SelectItemProps } from "./primitives/Select";
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
export { Search } from "./primitives/Search";
export type { SearchProps } from "./primitives/Search";
export { InlineLoading } from "./primitives/InlineLoading";
export type {
  InlineLoadingProps,
  InlineLoadingStatus,
} from "./primitives/InlineLoading";
export { InlineNotification } from "./primitives/InlineNotification";
export type {
  InlineNotificationProps,
  NotificationKind,
} from "./primitives/InlineNotification";
export {
  SkeletonText,
  SkeletonPlaceholder,
  DataTableSkeleton,
} from "./primitives/Skeleton";
export type {
  SkeletonTextProps,
  SkeletonPlaceholderProps,
  DataTableSkeletonProps,
} from "./primitives/Skeleton";
export { ProgressBar } from "./primitives/ProgressBar";
export type {
  ProgressBarProps,
  ProgressBarStatus,
} from "./primitives/ProgressBar";
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

// Navigation
export {
  Tabs,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
} from "./navigation/Tabs";
export type {
  TabsProps,
  TabListProps,
  TabProps,
  TabPanelsProps,
  TabPanelProps,
} from "./navigation/Tabs";
export { Pagination } from "./navigation/Pagination";
export type {
  PaginationProps,
  PaginationChangeEvent,
} from "./navigation/Pagination";
export { TreeView, TreeNode } from "./navigation/TreeView";
export type { TreeViewProps, TreeNodeProps } from "./navigation/TreeView";
export { ContentSwitcher, Switch } from "./navigation/ContentSwitcher";
export type {
  ContentSwitcherProps,
  SwitchProps,
} from "./navigation/ContentSwitcher";

// Table
export { DataTable } from "./table/DataTable";
export type {
  DataTableProps,
  DataTableHeader,
  DataTableRow,
  DataTableRowInput,
  DataTableCell,
  DataTableRenderProps,
  DataTableSortDirection,
} from "./table/DataTable";
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
export {
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
} from "./table/TableToolbar";
export type {
  TableToolbarProps,
  TableToolbarContentProps,
  TableToolbarSearchProps,
} from "./table/TableToolbar";
export {
  TableExpandHeader,
  TableExpandRow,
  TableExpandedRow,
} from "./table/TableExpand";
export type {
  TableExpandHeaderProps,
  TableExpandRowProps,
  TableExpandedRowProps,
} from "./table/TableExpand";
export { TableSelectAll, TableSelectRow } from "./table/TableSelect";
export type {
  TableSelectAllProps,
  TableSelectRowProps,
} from "./table/TableSelect";
export { TableBatchActions, TableBatchAction } from "./table/TableBatch";
export type {
  TableBatchActionsProps,
  TableBatchActionProps,
} from "./table/TableBatch";

// Modal
export { Modal } from "./modal/Modal";
export type { ModalProps } from "./modal/Modal";
export {
  ComposedModal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "./modal/ComposedModal";
export type {
  ComposedModalProps,
  ModalHeaderProps,
  ModalBodyProps,
  ModalFooterProps,
} from "./modal/ComposedModal";

// Multiselect / Dropdown
export { MultiSelect, FilterableMultiSelect } from "./multiselect/MultiSelect";
export type { MultiSelectProps } from "./multiselect/MultiSelect";
export { Dropdown } from "./multiselect/Dropdown";
export type { DropdownProps } from "./multiselect/Dropdown";

// Pickers
export { DatePicker, DatePickerInput } from "./pickers/DatePicker";
export type {
  DatePickerProps,
  DatePickerInputProps,
  DatePickerType,
} from "./pickers/DatePicker";
export { TimePicker } from "./pickers/TimePicker";
export type { TimePickerProps } from "./pickers/TimePicker";

// Structure
export {
  StructuredListWrapper,
  StructuredListHead,
  StructuredListBody,
  StructuredListRow,
  StructuredListCell,
} from "./structure/StructuredList";
export type {
  StructuredListWrapperProps,
  StructuredListHeadProps,
  StructuredListBodyProps,
  StructuredListRowProps,
  StructuredListCellProps,
} from "./structure/StructuredList";

// Shell
export {
  Header,
  HeaderName,
  HeaderMenuButton,
  HeaderGlobalBar,
  HeaderGlobalAction,
  SkipToContent,
} from "./shell/AppHeader";
export type {
  HeaderProps,
  HeaderNameProps,
  HeaderMenuButtonProps,
  HeaderGlobalBarProps,
  HeaderGlobalActionProps,
  SkipToContentProps,
} from "./shell/AppHeader";
export {
  SideNav,
  SideNavItems,
  SideNavLink,
  SideNavDivider,
} from "./shell/AppSideNav";
export type {
  SideNavProps,
  SideNavItemsProps,
  SideNavLinkProps,
} from "./shell/AppSideNav";
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
