import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  DataTable,
  InlineLoading,
  InlineNotification,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@carbon/react";
import { useCustomDigests } from "../../hooks/useDigest";
import { CustomDigestCreateModal } from "./CustomDigestCreateModal";

const PAGE_SIZE = 20;

const TABLE_HEADERS = [
  { key: "title", header: "Title" },
  { key: "createdAt", header: "Created" },
  { key: "channelCount", header: "Channels" },
  { key: "postCount", header: "Posts" },
];

interface DigestTableRow {
  id: string;
  title: string;
  createdAt: string;
  channelCount: string;
  postCount: string;
  digestId: number;
}

export function CustomDigestTab() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);

  const { data, isLoading, error } = useCustomDigests(page);

  const rows: DigestTableRow[] = (data?.digests ?? []).map((d) => ({
    id: String(d.id),
    title: d.title,
    createdAt: new Date(d.createdAt).toLocaleString(),
    channelCount: String(d.channelCount),
    postCount: String(d.postCount),
    digestId: d.id,
  }));

  const totalItems = data?.total ?? 0;

  return (
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <Button onClick={() => setCreateOpen(true)}>Create Custom Digest</Button>
      </div>

      <CustomDigestCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
      />

      {isLoading && <InlineLoading description="Loading custom digests..." />}

      {error && (
        <InlineNotification
          kind="error"
          title="Failed to load custom digests"
          subtitle={error instanceof Error ? error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      {!isLoading && !error && (
        <DataTable rows={rows} headers={TABLE_HEADERS}>
          {({ rows: tableRows, headers, getTableProps, getHeaderProps, getRowProps }) => (
            <Table {...getTableProps()}>
              <TableHead>
                <TableRow>
                  {headers.map((header) => (
                    <TableHeader {...getHeaderProps({ header })} key={header.key}>
                      {header.header}
                    </TableHeader>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {tableRows.map((row) => {
                  const digestRow = rows.find((r) => r.id === row.id);
                  return (
                    <TableRow
                      {...getRowProps({ row })}
                      key={row.id}
                      style={{ cursor: "pointer" }}
                      onClick={() => {
                        if (digestRow) {
                          navigate(`/digest/custom/${digestRow.digestId}`);
                        }
                      }}
                    >
                      {row.cells.map((cell) => (
                        <TableCell key={cell.id}>{cell.value as string}</TableCell>
                      ))}
                    </TableRow>
                  );
                })}
                {tableRows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={TABLE_HEADERS.length}>
                      No custom digests yet. Create one to get started.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </DataTable>
      )}

      {totalItems > PAGE_SIZE && (
        <Pagination
          totalItems={totalItems}
          pageSize={PAGE_SIZE}
          pageSizes={[PAGE_SIZE]}
          page={page}
          onChange={({ page: newPage }) => setPage(newPage)}
        />
      )}
    </div>
  );
}
