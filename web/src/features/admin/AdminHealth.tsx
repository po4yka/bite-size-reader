import { useMemo } from "react";
import {
  DataTable,
  DataTableSkeleton,
  SkeletonText,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Tile,
} from "@carbon/react";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useContentHealth } from "../../hooks/useAdmin";

const failureHeaders = [
  { key: "id", header: "Request ID" },
  { key: "url", header: "URL" },
  { key: "errorType", header: "Error Type" },
  { key: "errorMessage", header: "Error Message" },
  { key: "createdAt", header: "Created" },
];

export default function AdminHealth() {
  const { data, isLoading, error } = useContentHealth();

  const failureRows = useMemo(
    () =>
      (data?.recentFailures ?? []).map((f) => ({
        id: f.id,
        url: f.url,
        errorType: f.errorType ?? "unknown",
        errorMessage: f.errorMessage ?? "",
        createdAt: new Date(f.createdAt).toLocaleString(),
      })),
    [data],
  );

  if (isLoading) {
    return (
      <>
        <SkeletonText paragraph lineCount={2} />
        <DataTableSkeleton columnCount={failureHeaders.length} rowCount={5} showToolbar={false} />
      </>
    );
  }

  return (
    <>
      <QueryErrorNotification error={error} title="Failed to load content health" />

      {data && (
        <>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
            <Tile style={{ textAlign: "center", minWidth: 140 }}>
              <p className="cds--label">Total Requests</p>
              <p style={{ fontSize: "1.75rem", fontWeight: 600 }}>{data.totalRequests.toLocaleString()}</p>
            </Tile>
            <Tile style={{ textAlign: "center", minWidth: 140 }}>
              <p className="cds--label">Total Summaries</p>
              <p style={{ fontSize: "1.75rem", fontWeight: 600 }}>{data.totalSummaries.toLocaleString()}</p>
            </Tile>
            <Tile style={{ textAlign: "center", minWidth: 140 }}>
              <p className="cds--label">Failed Requests</p>
              <p style={{ fontSize: "1.75rem", fontWeight: 600, color: data.failedRequests > 0 ? "var(--cds-support-error)" : undefined }}>
                {data.failedRequests.toLocaleString()}
              </p>
            </Tile>
          </div>

          {Object.keys(data.failedByErrorType).length > 0 && (
            <Tile style={{ marginBottom: "1.5rem" }}>
              <h4 style={{ marginBottom: "0.5rem" }}>Failures by Error Type</h4>
              {Object.entries(data.failedByErrorType).map(([type, count]) => (
                <p key={type}>
                  <strong>{type}:</strong> {count}
                </p>
              ))}
            </Tile>
          )}

          {failureRows.length > 0 && (
            <DataTable rows={failureRows} headers={failureHeaders}>
              {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
                <TableContainer title="Recent Failures">
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
                            <TableCell key={cell.id}>{cell.value as string}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </DataTable>
          )}

          {failureRows.length === 0 && <p>No recent failures.</p>}
        </>
      )}
    </>
  );
}
