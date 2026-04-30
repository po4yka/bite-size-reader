import { useMemo } from "react";
import {
  BrutalistCard,
  BrutalistDataTableSkeleton,
  BrutalistSkeletonText,
  BrutalistTable,
  BrutalistTableContainer,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useContentHealth } from "../../hooks/useAdmin";

const ALARM = "var(--frost-spark)";

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
        <BrutalistSkeletonText paragraph lineCount={2} />
        <BrutalistDataTableSkeleton columnCount={failureHeaders.length} rowCount={5} showToolbar={false} />
      </>
    );
  }

  return (
    <>
      <QueryErrorNotification error={error} title="Failed to load content health" />

      {data && (
        <>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
            <BrutalistCard style={{ textAlign: "center", minWidth: 140 }}>
              <p className="rtk-label">Total Requests</p>
              <p style={{ fontSize: "1.75rem", fontWeight: 600 }}>{data.totalRequests.toLocaleString()}</p>
            </BrutalistCard>
            <BrutalistCard style={{ textAlign: "center", minWidth: 140 }}>
              <p className="rtk-label">Total Summaries</p>
              <p style={{ fontSize: "1.75rem", fontWeight: 600 }}>{data.totalSummaries.toLocaleString()}</p>
            </BrutalistCard>
            <BrutalistCard style={{ textAlign: "center", minWidth: 140 }}>
              <p className="rtk-label">Failed Requests</p>
              <p
                style={{
                  fontSize: "1.75rem",
                  fontWeight: 600,
                  color: data.failedRequests > 0 ? ALARM : undefined,
                }}
              >
                {data.failedRequests.toLocaleString()}
              </p>
            </BrutalistCard>
          </div>

          {Object.keys(data.failedByErrorType).length > 0 && (
            <BrutalistCard style={{ marginBottom: "1.5rem" }}>
              <h4 style={{ marginBottom: "0.5rem" }}>Failures by Error Type</h4>
              {Object.entries(data.failedByErrorType).map(([type, count]) => (
                <p key={type}>
                  <strong>{type}:</strong> {count}
                </p>
              ))}
            </BrutalistCard>
          )}

          {failureRows.length > 0 && (
            <BrutalistTable rows={failureRows} headers={failureHeaders}>
              {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
                <BrutalistTableContainer title="Recent Failures">
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
                </BrutalistTableContainer>
              )}
            </BrutalistTable>
          )}

          {failureRows.length === 0 && <p>No recent failures.</p>}
        </>
      )}
    </>
  );
}
