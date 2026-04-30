import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { BracketPagination } from "./BracketPagination";

const meta = {
  title: "Navigation/BracketPagination",
  component: BracketPagination,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof BracketPagination>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    page: 2,
    pageSize: 10,
    totalItems: 140,
    pageSizes: [10, 20, 50],
  },
  render: (args) => {
    const [page, setPage] = useState(args.page ?? 2);
    const [pageSize, setPageSize] = useState(args.pageSize ?? 10);
    return (
      <BracketPagination
        {...args}
        page={page}
        pageSize={pageSize}
        onChange={({ page: p, pageSize: ps }) => {
          setPage(p);
          setPageSize(ps);
        }}
      />
    );
  },
};

export const FirstPage: Story = {
  render: () => (
    <BracketPagination
      page={1}
      pageSize={10}
      totalItems={140}
    />
  ),
};

export const LastPage: Story = {
  render: () => (
    <BracketPagination
      page={14}
      pageSize={10}
      totalItems={140}
    />
  ),
};

export const SinglePage: Story = {
  render: () => (
    <BracketPagination
      page={1}
      pageSize={10}
      totalItems={7}
    />
  ),
};

export const Disabled: Story = {
  render: () => (
    <BracketPagination
      page={3}
      pageSize={10}
      totalItems={100}
      disabled
    />
  ),
};

export const WithLabel: Story = {
  render: () => {
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);
    return (
      <BracketPagination
        page={page}
        pageSize={pageSize}
        pageSizes={[10, 20, 50]}
        totalItems={320}
        itemsPerPageText="Show"
        onChange={({ page: p, pageSize: ps }) => {
          setPage(p);
          setPageSize(ps);
        }}
      />
    );
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 32 }}>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Middle page</p>
        <BracketPagination page={5} pageSize={10} totalItems={140} />
      </div>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>First page (prev disabled)</p>
        <BracketPagination page={1} pageSize={10} totalItems={140} />
      </div>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Last page (next disabled)</p>
        <BracketPagination page={14} pageSize={10} totalItems={140} />
      </div>
      <div>
        <p style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, opacity: 0.55, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>With page-size selector</p>
        <BracketPagination page={2} pageSize={20} pageSizes={[10, 20, 50]} totalItems={200} itemsPerPageText="Show" />
      </div>
    </div>
  ),
};
