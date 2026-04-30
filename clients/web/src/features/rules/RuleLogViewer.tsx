import {
  BrutalistTable,
  type BrutalistTableRenderProps,
  SparkLoading,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from "../../design";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import { useRuleLogs } from "../../hooks/useRules";
import type { RuleLog } from "../../api/rules";

interface LogRow {
  id: string;
  createdAt: string;
  matched: string;
  durationMs: string;
  actionsTaken: string;
  error: string;
  [key: string]: unknown;
}

export default function RuleLogViewer({ ruleId }: { ruleId: number }) {
  const { data, isLoading, error } = useRuleLogs(ruleId);
  const logs: RuleLog[] = data?.logs ?? [];

  if (isLoading) return <SparkLoading description="Loading logs..." />;
  if (error) return <QueryErrorNotification error={error} title="Failed to load rule logs" />;
  if (logs.length === 0) {
    return <p className="rtk-label">No execution logs yet.</p>;
  }

  const headers = [
    { key: "createdAt", header: "Time" },
    { key: "matched", header: "Matched" },
    { key: "durationMs", header: "Duration" },
    { key: "actionsTaken", header: "Actions Taken" },
    { key: "error", header: "Error" },
  ];

  const rows: LogRow[] = logs.map((log) => ({
    id: String(log.id),
    createdAt: new Date(log.createdAt).toLocaleString(),
    matched: log.matched ? "Yes" : "No",
    durationMs: log.durationMs != null ? `${log.durationMs}ms` : "-",
    actionsTaken: Array.isArray(log.actionsTaken) ? JSON.stringify(log.actionsTaken) : "-",
    error: log.error ?? "",
  }));

  return (
    <BrutalistTable<LogRow> rows={rows} headers={headers}>
      {({
        rows: rRows,
        headers: rHeaders,
        getHeaderProps,
        getRowProps,
        getTableProps,
      }: BrutalistTableRenderProps<LogRow>) => (
        <TableContainer title="Execution logs">
          <Table {...getTableProps()} size="sm">
            <TableHead>
              <TableRow>
                {rHeaders.map((header) => (
                  <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rRows.map((row) => (
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
    </BrutalistTable>
  );
}
