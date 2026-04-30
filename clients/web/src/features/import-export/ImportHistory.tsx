import { useMemo } from "react";
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
  Tag,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useImportJobs, useDeleteImportJob } from "../../hooks/useImportExport";
import type { ImportJob } from "../../api/importExport";

function statusTagType(status: string): "green" | "blue" | "red" | "warm-gray" {
  if (status === "completed") return "green";
  if (status === "processing") return "blue";
  if (status === "failed") return "red";
  return "warm-gray";
}

const HEADERS = [
  { key: "sourceFormat", header: "Format" },
  { key: "fileName", header: "File Name" },
  { key: "status", header: "Status" },
  { key: "totalItems", header: "Items" },
  { key: "counts", header: "Created/Skipped/Failed" },
  { key: "createdAt", header: "Date" },
  { key: "actions", header: "Actions" },
];

export default function ImportHistory() {
  const { data: jobs, isLoading, error } = useImportJobs();
  const deleteMutation = useDeleteImportJob();

  const rows = useMemo(
    () =>
      (jobs ?? []).map((job: ImportJob) => ({
        id: String(job.id),
        sourceFormat: job.sourceFormat,
        fileName: job.fileName ?? "-",
        status: job.status,
        totalItems: String(job.totalItems),
        counts: `${job.createdItems}/${job.skippedItems}/${job.failedItems}`,
        createdAt: new Date(job.createdAt).toLocaleString(),
        actions: job,
      })),
    [jobs],
  );

  if (isLoading) return <DataTableSkeleton columnCount={HEADERS.length} rowCount={3} showToolbar={false} />;
  if (error) return <QueryErrorNotification error={error} title="Failed to load import history" />;
  if (rows.length === 0) return <p className="rtk-label">No import history.</p>;

  return (
    <DataTable rows={rows} headers={HEADERS}>
      {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
        <TableContainer title="Import history">
          <Table {...getTableProps()} size="sm">
            <TableHead>
              <TableRow>
                {headers.map((header) => (
                  <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => {
                const job = row.cells.find((c) => c.info.header === "Actions")?.value as ImportJob;
                return (
                  <TableRow {...getRowProps({ row })}>
                    {row.cells.map((cell) => {
                      if (cell.info.header === "Status") {
                        const status = cell.value as string;
                        return (
                          <TableCell key={cell.id}>
                            <Tag type={statusTagType(status)} size="sm">
                              {status}
                            </Tag>
                          </TableCell>
                        );
                      }
                      if (cell.info.header === "Actions") {
                        return (
                          <TableCell key={cell.id}>
                            <Button
                              kind="danger--ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteMutation.mutate(job.id);
                              }}
                              disabled={deleteMutation.isPending}
                            >
                              Delete
                            </Button>
                          </TableCell>
                        );
                      }
                      return <TableCell key={cell.id}>{cell.value as string}</TableCell>;
                    })}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </DataTable>
  );
}
