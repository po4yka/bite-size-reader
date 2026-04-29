import { useMemo, useState } from "react";
import {
  DataTable,
  DataTableSkeleton,
  InlineNotification,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Tile,
} from "../../design";
import { HISTORY_PAGE_SIZE, useDigestHistory } from "../../hooks/useDigest";

export function HistoryTab() {
  const [page, setPage] = useState(1);

  const historyQuery = useDigestHistory(page);

  const rows = useMemo(
    () =>
      (historyQuery.data?.deliveries ?? []).map((entry) => ({
        id: String(entry.id),
        deliveredAt: new Date(entry.deliveredAt).toLocaleString(),
        postCount: entry.postCount,
        channelCount: entry.channelCount,
        digestType: entry.digestType,
      })),
    [historyQuery.data?.deliveries],
  );

  const headers = [
    { key: "deliveredAt", header: "Delivered" },
    { key: "postCount", header: "Posts" },
    { key: "channelCount", header: "Channels" },
    { key: "digestType", header: "Type" },
  ];
  const isHistoryInitialLoading = historyQuery.isLoading && !historyQuery.data;

  return (
    <div className="page-section">
      <Tile>
        <h3>Digest history</h3>

        {isHistoryInitialLoading && <DataTableSkeleton columnCount={headers.length} rowCount={6} showToolbar={false} />}

        {historyQuery.error && (
          <InlineNotification
            kind="error"
            title="Failed to load digest history"
            subtitle={historyQuery.error instanceof Error ? historyQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {!isHistoryInitialLoading && (
          <DataTable rows={rows} headers={headers}>
            {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
              <TableContainer title="Digest deliveries">
                <Table {...getTableProps()}>
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
                          <TableCell key={cell.id}>{String(cell.value)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DataTable>
        )}

        {historyQuery.data && (
          <Pagination
            page={page}
            pageSize={HISTORY_PAGE_SIZE}
            pageSizes={[HISTORY_PAGE_SIZE]}
            totalItems={historyQuery.data.total}
            onChange={(event) => setPage(event.page)}
          />
        )}
      </Tile>
    </div>
  );
}
