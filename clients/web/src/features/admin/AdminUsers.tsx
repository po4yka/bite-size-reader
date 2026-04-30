import { useMemo } from "react";
import {
  DataTable,
  DataTableSkeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useAdminUsers } from "../../hooks/useAdmin";

const headers = [
  { key: "username", header: "Username" },
  { key: "isOwner", header: "Role" },
  { key: "summaryCount", header: "Summaries" },
  { key: "requestCount", header: "Requests" },
  { key: "tagCount", header: "Tags" },
  { key: "collectionCount", header: "Collections" },
  { key: "createdAt", header: "Created" },
];

export default function AdminUsers() {
  const { data, isLoading, error } = useAdminUsers();
  const rows = useMemo(
    () =>
      (data?.users ?? []).map((u) => ({
        id: String(u.userId),
        username: u.username ?? `User #${u.userId}`,
        isOwner: u.isOwner,
        summaryCount: String(u.summaryCount),
        requestCount: String(u.requestCount),
        tagCount: String(u.tagCount),
        collectionCount: String(u.collectionCount),
        createdAt: new Date(u.createdAt).toLocaleDateString(),
      })),
    [data],
  );

  if (isLoading) return <DataTableSkeleton columnCount={headers.length} rowCount={5} showToolbar={false} />;

  return (
    <>
      <QueryErrorNotification error={error} title="Failed to load users" />

      {rows.length === 0 && !error && <p>No users found.</p>}

      {rows.length > 0 && (
        <DataTable rows={rows} headers={headers}>
          {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title={`Users (${data?.totalUsers ?? 0})`}>
              <Table {...getTableProps()} size="lg">
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
                      {row.cells.map((cell) => {
                        if (cell.info.header === "isOwner") {
                          return (
                            <TableCell key={cell.id}>
                              {cell.value ? (
                                <Tag size="sm">
                                  Owner
                                </Tag>
                              ) : (
                                <Tag size="sm">
                                  User
                                </Tag>
                              )}
                            </TableCell>
                          );
                        }
                        return <TableCell key={cell.id}>{cell.value as string}</TableCell>;
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DataTable>
      )}
    </>
  );
}
