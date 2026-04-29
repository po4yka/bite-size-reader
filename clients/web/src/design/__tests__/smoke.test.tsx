import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import {
  Accordion,
  AccordionItem,
  Button,
  ButtonSet,
  Checkbox,
  CodeSnippet,
  ComposedModal,
  Content,
  ContentSwitcher,
  DataTable,
  DataTableSkeleton,
  DatePicker,
  DatePickerInput,
  Dropdown,
  FileUploader,
  FilterableMultiSelect,
  Header,
  HeaderGlobalAction,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderName,
  IconButton,
  InlineLoading,
  InlineNotification,
  Link,
  ListItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  MultiSelect,
  NumberInput,
  Pagination,
  ProgressBar,
  RadioButton,
  RadioButtonGroup,
  Search,
  Select,
  SelectItem,
  SideNav,
  SideNavDivider,
  SideNavItems,
  SideNavLink,
  SkeletonPlaceholder,
  SkeletonText,
  SkipToContent,
  StructuredListBody,
  StructuredListCell,
  StructuredListHead,
  StructuredListRow,
  StructuredListWrapper,
  Switch,
  Tab,
  Table,
  TableBatchAction,
  TableBatchActions,
  TableBody,
  TableCell,
  TableContainer,
  TableExpandHeader,
  TableExpandRow,
  TableExpandedRow,
  TableHead,
  TableHeader,
  TableRow,
  TableSelectAll,
  TableSelectRow,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Tag,
  TextArea,
  TextInput,
  Theme,
  Tile,
  TimePicker,
  Toggle,
  TreeNode,
  TreeView,
  UnorderedList,
  // icons
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
} from "../index";

describe("design layer smoke renders", () => {
  it("primitives mount without throwing", () => {
    const { unmount } = render(
      <>
        <Button>btn</Button>
        <ButtonSet>
          <Button>a</Button>
        </ButtonSet>
        <IconButton label="x">i</IconButton>
        <Tile>tile</Tile>
        <Tag type="teal">tag</Tag>
        <Link href="#">link</Link>
        <TextInput id="ti" labelText="L" />
        <TextArea id="ta" labelText="L" />
        <Select id="sel" labelText="L">
          <SelectItem value="a" text="A" />
        </Select>
        <NumberInput id="ni" label="L" />
        <Checkbox id="cb" labelText="L" />
        <RadioButtonGroup name="g" legendText="L">
          <RadioButton id="r1" labelText="A" value="a" />
          <RadioButton id="r2" labelText="B" value="b" />
        </RadioButtonGroup>
        <Toggle id="tg" labelText="L" />
        <Search id="search" />
        <InlineLoading status="active" description="loading" />
        <InlineNotification kind="info" title="hi" />
        <SkeletonText paragraph lineCount={2} />
        <SkeletonPlaceholder />
        <DataTableSkeleton columnCount={2} rowCount={2} />
        <ProgressBar label="p" value={50} />
        <CodeSnippet>code</CodeSnippet>
        <FileUploader buttonLabel="Pick" />
        <UnorderedList>
          <ListItem>x</ListItem>
        </UnorderedList>
        <Accordion>
          <AccordionItem title="t">body</AccordionItem>
        </Accordion>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("navigation primitives mount", () => {
    const { unmount } = render(
      <>
        <Tabs>
          <TabList>
            <Tab>One</Tab>
          </TabList>
          <TabPanels>
            <TabPanel>p1</TabPanel>
          </TabPanels>
        </Tabs>
        <Pagination page={1} pageSize={10} totalItems={10} />
        <TreeView label="tree" hideLabel>
          <TreeNode id="1" label="root">
            <TreeNode id="1.1" label="child" />
          </TreeNode>
        </TreeView>
        <ContentSwitcher>
          <Switch name="a" text="A" />
          <Switch name="b" text="B" />
        </ContentSwitcher>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("table primitives mount", () => {
    const headers = [
      { key: "name", header: "Name" },
      { key: "domain", header: "Domain" },
    ];
    const rows = [{ id: "r1", name: "n", domain: "d" }];
    const { unmount } = render(
      <>
        <DataTable rows={rows} headers={headers}>
          {({ rows: r, headers: h, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title="t">
              <TableToolbar>
                <TableToolbarContent>
                  <TableToolbarSearch />
                </TableToolbarContent>
              </TableToolbar>
              <Table {...getTableProps()}>
                <TableHead>
                  <TableRow>
                    <TableSelectAll />
                    <TableExpandHeader />
                    {h.map((header) => (
                      <TableHeader key={header.key} {...getHeaderProps({ header })}>
                        {header.header}
                      </TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {r.map((row) => (
                    <TableExpandRow key={row.id} {...getRowProps({ row })}>
                      <TableSelectRow id={`s-${row.id}`} />
                      {row.cells.map((cell) => (
                        <TableCell key={cell.id}>{String(cell.value)}</TableCell>
                      ))}
                    </TableExpandRow>
                  ))}
                  <TableExpandedRow colSpan={3}>x</TableExpandedRow>
                </TableBody>
              </Table>
              <TableBatchActions shouldShowBatchActions totalSelected={1} onCancel={() => {}}>
                <TableBatchAction>Do</TableBatchAction>
              </TableBatchActions>
            </TableContainer>
          )}
        </DataTable>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("modal primitives mount (closed)", () => {
    const { unmount } = render(
      <>
        <Modal open={false}>m</Modal>
        <ComposedModal open={false}>
          <ModalHeader title="t" />
          <ModalBody>b</ModalBody>
          <ModalFooter>f</ModalFooter>
        </ComposedModal>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("multiselect / dropdown / pickers mount", () => {
    const items = [{ id: "1", text: "One" }];
    const { unmount } = render(
      <>
        <MultiSelect
          id="ms"
          titleText="T"
          label="choose"
          items={items}
          itemToString={(it) => it?.text ?? ""}
        />
        <FilterableMultiSelect
          id="fms"
          titleText="T"
          label="choose"
          items={items}
          itemToString={(it) => it?.text ?? ""}
        />
        <Dropdown
          id="dd"
          titleText="T"
          label="choose"
          items={items}
          itemToString={(it) => it?.text ?? ""}
        />
        <DatePicker datePickerType="single">
          <DatePickerInput id="dpi" labelText="Date" placeholder="yyyy-mm-dd" />
        </DatePicker>
        <TimePicker id="tp" labelText="Time" />
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("structure / shell / theme primitives mount", () => {
    const { unmount } = render(
      <Theme theme="white">
        <Header aria-label="h">
          <SkipToContent />
          <HeaderMenuButton aria-label="menu" />
          <HeaderName href="#" prefix="R">
            App
          </HeaderName>
          <HeaderGlobalBar>
            <HeaderGlobalAction aria-label="x">
              <Add />
            </HeaderGlobalAction>
          </HeaderGlobalBar>
        </Header>
        <SideNav aria-label="s" expanded={false}>
          <SideNavItems>
            <SideNavLink href="#" renderIcon={Book}>
              Lib
            </SideNavLink>
            <SideNavDivider />
          </SideNavItems>
        </SideNav>
        <Content>
          <StructuredListWrapper>
            <StructuredListHead>
              <StructuredListRow head>
                <StructuredListCell head>H</StructuredListCell>
              </StructuredListRow>
            </StructuredListHead>
            <StructuredListBody>
              <StructuredListRow>
                <StructuredListCell>Body</StructuredListCell>
              </StructuredListRow>
            </StructuredListBody>
          </StructuredListWrapper>
        </Content>
      </Theme>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("icons render as svg", () => {
    const icons = [
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
    ];
    for (const Icon of icons) {
      const { container, unmount } = render(<Icon />);
      expect(container.querySelector("svg")).not.toBeNull();
      unmount();
    }
  });

  it("Theme writes data-theme on document root for legacy + new vocab", async () => {
    const { rerender, unmount } = render(<Theme theme="white">x</Theme>);
    // useEffect runs after render; flush microtasks
    await Promise.resolve();
    expect(document.documentElement.dataset.theme).toBe("light");
    rerender(<Theme theme="g100">x</Theme>);
    await Promise.resolve();
    expect(document.documentElement.dataset.theme).toBe("dark");
    rerender(<Theme theme="dark">x</Theme>);
    await Promise.resolve();
    expect(document.documentElement.dataset.theme).toBe("dark");
    rerender(<Theme theme="light">x</Theme>);
    await Promise.resolve();
    expect(document.documentElement.dataset.theme).toBe("light");
    unmount();
  });
});
