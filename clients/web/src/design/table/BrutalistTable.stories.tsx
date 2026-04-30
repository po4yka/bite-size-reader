import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  DataTable,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableExpandCell,
  TableExpandHeaderCell,
  TableHead,
  TableHeader,
  TableRow,
  TableSelectCell,
  TableSelectHeaderCell,
} from "./BrutalistTable";

const meta = {
  title: "Frost/BrutalistTable",
  component: DataTable,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof DataTable>;

export default meta;
type Story = StoryObj<typeof meta>;

const HEADERS = [
  { key: "name", header: "Name" },
  { key: "status", header: "Status" },
  { key: "date", header: "Date" },
];

const ROWS = [
  { id: "r1", name: "Andromeda Signal", status: "processed", date: "2025-04-28" },
  { id: "r2", name: "Boötes Void", status: "pending", date: "2025-04-29" },
  { id: "r3", name: "Cygnus X-1", status: "failed", date: "2025-04-30" },
];

function renderCells(row: { cells: Array<{ id: string; value: unknown }> }) {
  return row.cells.map((cell) => (
    <TableCell key={cell.id}>{String(cell.value ?? "")}</TableCell>
  ));
}

export const Default: Story = {
  args: {
    rows: ROWS,
    headers: HEADERS,
    children: ({ rows, headers, getTableProps, getHeaderProps, getRowProps }) => (
      <TableContainer>
        <Table {...(getTableProps() as object)}>
          <TableHead>
            <TableRow>
              {headers.map((h) => (
                <TableHeader key={h.key} {...(getHeaderProps({ header: h }) as object)}>
                  {h.header}
                </TableHeader>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id} {...(getRowProps({ row }) as object)}>
                {renderCells(row)}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    ),
  },
};

export const Variants: Story = {
  args: {
    rows: ROWS,
    headers: HEADERS,
    children: ({ rows, headers, getTableProps, getHeaderProps, getRowProps }) => (
      <TableContainer>
        <Table {...(getTableProps() as object)}>
          <TableHead>
            <TableRow>
              {headers.map((h) => (
                <TableHeader key={h.key} {...(getHeaderProps({ header: h }) as object)}>
                  {h.header}
                </TableHeader>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id} {...(getRowProps({ row }) as object)}>
                {renderCells(row)}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    ),
  },
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      {/* Sortable */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          SORTABLE
        </div>
        <DataTable rows={ROWS} headers={HEADERS} isSortable>
          {({ rows, headers, getTableProps, getHeaderProps, getRowProps }) => (
            <TableContainer>
              <Table {...(getTableProps() as object)}>
                <TableHead>
                  <TableRow>
                    {headers.map((h) => (
                      <TableHeader key={h.key} isSortable {...(getHeaderProps({ header: h, isSortable: true }) as object)}>
                        {h.header}
                      </TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.id} {...(getRowProps({ row }) as object)}>
                      {renderCells(row)}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DataTable>
      </section>

      {/* Selectable */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          SELECTABLE
        </div>
        <DataTable rows={ROWS} headers={HEADERS}>
          {({ rows, headers, getTableProps, getHeaderProps, getRowProps, getSelectionProps }) => {
            const allSel = getSelectionProps() as { checked: boolean; onSelect: () => void; id: string };
            return (
              <TableContainer>
                <Table {...(getTableProps() as object)}>
                  <TableHead>
                    <TableRow>
                      <TableSelectHeaderCell
                        checked={allSel.checked}
                        onSelect={allSel.onSelect}
                        id={allSel.id}
                      />
                      {headers.map((h) => (
                        <TableHeader key={h.key} {...(getHeaderProps({ header: h }) as object)}>
                          {h.header}
                        </TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => {
                      const sel = getSelectionProps({ row }) as { checked: boolean; onSelect: () => void; id: string };
                      return (
                        <TableRow key={row.id} {...(getRowProps({ row }) as object)}>
                          <TableSelectCell
                            checked={sel.checked}
                            onSelect={sel.onSelect}
                            id={sel.id}
                          />
                          {renderCells(row)}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            );
          }}
        </DataTable>
      </section>

      {/* Expandable */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          EXPANDABLE
        </div>
        <ExpandableDemo />
      </section>

      {/* With title + footer pagination placeholder */}
      <section>
        <div style={{ fontFamily: "var(--frost-font-mono)", fontSize: 11, fontWeight: 800, letterSpacing: "1px", textTransform: "uppercase", marginBottom: 8, opacity: 0.6 }}>
          TITLED + PAGINATION PLACEHOLDER
        </div>
        <DataTable rows={ROWS} headers={HEADERS}>
          {({ rows, headers, getTableProps, getHeaderProps, getRowProps }) => (
            <div>
              <TableContainer title="Signal log" description="Three most recent entries">
                <Table {...(getTableProps() as object)}>
                  <TableHead>
                    <TableRow>
                      {headers.map((h) => (
                        <TableHeader key={h.key} {...(getHeaderProps({ header: h }) as object)}>
                          {h.header}
                        </TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => (
                      <TableRow key={row.id} {...(getRowProps({ row }) as object)}>
                        {renderCells(row)}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <div style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: 11,
                padding: "8px 16px",
                borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 50%, transparent)",
                opacity: 0.55,
              }}>
                [ ‹ ]  PAGE 01 OF 01  [ › ]
              </div>
            </div>
          )}
        </DataTable>
      </section>
    </div>
  ),
};

function ExpandableDemo() {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            <TableExpandHeaderCell />
            <TableHeader>Name</TableHeader>
            <TableHeader>Status</TableHeader>
            <TableHeader>Date</TableHeader>
          </TableRow>
        </TableHead>
        <TableBody>
          {ROWS.map((row) => (
            <>
              <TableRow key={row.id}>
                <TableExpandCell
                  isExpanded={expanded.has(row.id)}
                  onToggle={() => toggle(row.id)}
                />
                <TableCell>{row.name}</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>{row.date}</TableCell>
              </TableRow>
              {expanded.has(row.id) && (
                <TableRow key={`${row.id}-expanded`}>
                  <TableCell />
                  <TableCell colSpan={3} style={{ opacity: 0.6, fontStyle: "italic" }}>
                    Expanded detail for {row.name}. Full signal metadata would appear here.
                  </TableCell>
                </TableRow>
              )}
            </>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
