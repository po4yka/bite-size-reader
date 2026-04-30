import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import {
  Accordion,
  AccordionItem,
  Checkbox,
  CodeSnippet,
  Content,
  ContentSwitcher,
  DatePicker,
  DatePickerInput,
  Dropdown,
  FileUploader,
  FilterableMultiSelect,
  IconButton,
  Link,
  ListItem,
  MultiSelect,
  NumberInput,
  RadioButton,
  RadioButtonGroup,
  Switch,
  TableBatchAction,
  TableBatchActions,
  TableExpandHeader,
  TableExpandRow,
  TableExpandedRow,
  TableSelectAll,
  TableSelectRow,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  Tag,
  Theme,
  TimePicker,
  Toggle,
  TreeNode,
  TreeView,
  UnorderedList,
  // Frost components
  BracketButton,
  BracketPagination,
  BracketSearch,
  BracketTab,
  BracketTabList,
  BracketTabPanel,
  BracketTabPanels,
  BracketTabs,
  BrutalistCard,
  BrutalistDataTableSkeleton,
  BrutalistModal,
  BrutalistModalBody,
  BrutalistModalFooter,
  BrutalistModalHeader,
  BrutalistSkeleton,
  BrutalistSkeletonPlaceholder,
  BrutalistSkeletonText,
  BrutalistTable,
  BrutalistTableContainer,
  FrostHeader,
  FrostHeaderGlobalAction,
  FrostHeaderGlobalBar,
  FrostHeaderMenuButton,
  FrostHeaderName,
  FrostSideNav,
  FrostSideNavDivider,
  FrostSideNavItems,
  FrostSideNavLink,
  MonoInput,
  MonoProgressBar,
  MonoSelect,
  MonoSelectItem,
  MonoTextArea,
  RowDigestBody,
  RowDigestCell,
  RowDigestHead,
  RowDigestRow,
  RowDigestWrapper,
  SparkLoading,
  StatusBadge,
  Toast,
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
  it("in-place rewrite primitives mount without throwing", () => {
    const { unmount } = render(
      <>
        <IconButton label="x">i</IconButton>
        <Tag type="teal">tag</Tag>
        <Link href="#">link</Link>
        <NumberInput id="ni" label="L" />
        <Checkbox id="cb" labelText="L" />
        <RadioButtonGroup name="g" legendText="L">
          <RadioButton id="r1" labelText="A" value="a" />
          <RadioButton id="r2" labelText="B" value="b" />
        </RadioButtonGroup>
        <Toggle id="tg" labelText="L" />
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

  it("navigation in-place rewrites mount", () => {
    const { unmount } = render(
      <>
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

  it("legacy table sub-components mount (pending migration of digest pages)", () => {
    const headers = [
      { key: "name", header: "Name" },
      { key: "domain", header: "Domain" },
    ];
    const rows = [{ id: "r1", name: "n", domain: "d" }];
    const { unmount } = render(
      <>
        <BrutalistTable rows={rows} headers={headers}>
          {({ rows: r, headers: h, getHeaderProps, getRowProps, getTableProps }) => (
            <BrutalistTableContainer title="t">
              <TableToolbar>
                <TableToolbarContent>
                  <TableToolbarSearch />
                </TableToolbarContent>
              </TableToolbar>
              <table {...getTableProps()}>
                <thead>
                  <tr>
                    <TableSelectAll />
                    <TableExpandHeader />
                    {h.map((header) => (
                      <th key={header.key} {...getHeaderProps({ header })}>
                        {header.header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.map((row) => (
                    <TableExpandRow key={row.id} {...getRowProps({ row })}>
                      <TableSelectRow id={`s-${row.id}`} />
                      {row.cells.map((cell) => (
                        <td key={cell.id}>{String(cell.value)}</td>
                      ))}
                    </TableExpandRow>
                  ))}
                  <TableExpandedRow colSpan={3}>x</TableExpandedRow>
                </tbody>
              </table>
              <TableBatchActions shouldShowBatchActions totalSelected={1} onCancel={() => {}}>
                <TableBatchAction>Do</TableBatchAction>
              </TableBatchActions>
            </BrutalistTableContainer>
          )}
        </BrutalistTable>
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

  it("Frost primitives mount", () => {
    const { unmount } = render(
      <>
        <BracketButton>[ ACTION ]</BracketButton>
        <BracketSearch id="bs" />
        <BrutalistCard>card</BrutalistCard>
        <BrutalistSkeleton />
        <BrutalistSkeletonText />
        <BrutalistSkeletonPlaceholder />
        <BrutalistDataTableSkeleton columnCount={2} rowCount={2} />
        <MonoInput id="mi" labelText="L" />
        <MonoProgressBar label="p" value={50} />
        <MonoSelect id="msel" labelText="L">
          <MonoSelectItem value="a" text="A" />
        </MonoSelect>
        <MonoTextArea id="mta" labelText="L" />
        <SparkLoading status="active" description="loading" />
        <StatusBadge severity="info">INFO</StatusBadge>
        <Toast severity="info" title="t" />
        <BracketPagination page={1} pageSize={10} totalItems={10} />
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("Frost navigation mounts", () => {
    const { unmount } = render(
      <>
        <BracketTabs>
          <BracketTabList>
            <BracketTab>One</BracketTab>
          </BracketTabList>
          <BracketTabPanels>
            <BracketTabPanel>p1</BracketTabPanel>
          </BracketTabPanels>
        </BracketTabs>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("Frost modal mounts (closed)", () => {
    const { unmount } = render(
      <>
        <BrutalistModal open={false}>
          <BrutalistModalHeader title="t" />
          <BrutalistModalBody>b</BrutalistModalBody>
          <BrutalistModalFooter>f</BrutalistModalFooter>
        </BrutalistModal>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("Frost structure mounts", () => {
    const { unmount } = render(
      <>
        <RowDigestWrapper>
          <RowDigestHead>
            <RowDigestRow head>
              <RowDigestCell head>H</RowDigestCell>
            </RowDigestRow>
          </RowDigestHead>
          <RowDigestBody>
            <RowDigestRow>
              <RowDigestCell>Body</RowDigestCell>
            </RowDigestRow>
          </RowDigestBody>
        </RowDigestWrapper>
      </>,
    );
    expect(true).toBe(true);
    unmount();
  });

  it("Frost shell mounts", () => {
    const { unmount } = render(
      <Theme theme="white">
        <FrostHeader aria-label="h">
          <FrostHeaderMenuButton aria-label="menu" />
          <FrostHeaderName href="#" prefix="R">
            App
          </FrostHeaderName>
          <FrostHeaderGlobalBar>
            <FrostHeaderGlobalAction aria-label="x">
              <Add />
            </FrostHeaderGlobalAction>
          </FrostHeaderGlobalBar>
        </FrostHeader>
        <FrostSideNav aria-label="s" expanded={false}>
          <FrostSideNavItems>
            <FrostSideNavLink href="#" renderIcon={Book}>
              Lib
            </FrostSideNavLink>
            <FrostSideNavDivider />
          </FrostSideNavItems>
        </FrostSideNav>
        <Content>content</Content>
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
