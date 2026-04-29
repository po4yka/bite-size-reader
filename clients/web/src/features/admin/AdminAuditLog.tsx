import { useMemo, useState } from "react";
import {
  Button,
  DataTable,
  DataTableSkeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TextInput,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useAuditLog } from "../../hooks/useAdmin";

const PAGE_SIZE = 50;

const headers = [
  { key: "timestamp", header: "Timestamp" },
  { key: "level", header: "Level" },
  { key: "event", header: "Event" },
  { key: "details", header: "Details" },
];

export default function AdminAuditLog() {
  const [actionFilter, setActionFilter] = useState("");
  const [page, setPage] = useState(0);

  const params = useMemo(
    () => ({
      action: actionFilter.trim() || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    [actionFilter, page],
  );

  const { data, isLoading, error } = useAuditLog(params);

  const rows = useMemo(
    () =>
      (data?.logs ?? []).map((entry) => ({
        id: String(entry.id),
        timestamp: new Date(entry.timestamp).toLocaleString(),
        level: entry.level,
        event: entry.event,
        details: entry.details ? JSON.stringify(entry.details) : "",
      })),
    [data],
  );

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <div style={{ display: "flex", gap: "1rem", alignItems: "flex-end", marginBottom: "1rem", flexWrap: "wrap" }}>
        <TextInput
          id="audit-action-filter"
          labelText="Filter by action"
          placeholder="e.g. admin.list_users"
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.currentTarget.value);
            setPage(0);
          }}
          size="sm"
          style={{ maxWidth: 280 }}
        />
      </div>

      <QueryErrorNotification error={error} title="Failed to load audit log" />

      {isLoading && <DataTableSkeleton columnCount={headers.length} rowCount={8} showToolbar={false} />}

      {!isLoading && rows.length === 0 && !error && <p>No audit log entries found.</p>}

      {!isLoading && rows.length > 0 && (
        <>
          <DataTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <TableContainer title={`Audit Log (${total} total)`}>
                <Table {...getTableProps()} size="sm">
                  <TableHead>
                    <TableRow>
                      {headers.map((header) => (
                        <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => (
                      <TableRow {...getRowProps({ row })}>
                        {row.cells.map((cell) => (
                          <TableCell key={cell.id}>
                            {cell.info.header === "details" ? (
                              <code style={{ fontSize: "0.75rem", wordBreak: "break-all" }}>{cell.value as string}</code>
                            ) : (
                              (cell.value as string)
                            )}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DataTable>

          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "1rem", justifyContent: "center" }}>
            <Button kind="ghost" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="cds--label" style={{ margin: 0 }}>
              Page {page + 1} of {totalPages}
            </span>
            <Button kind="ghost" size="sm" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </>
      )}
    </>
  );
}
