import {
  Button,
  DataTable,
  DataTableSkeleton,
  Tag,
  Tile,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from "@carbon/react";
import { useSessions, useDeleteSession } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import type { AuthSession } from "../../api/auth";

const headers = [
  { key: "clientId", header: "Client" },
  { key: "deviceInfo", header: "Device" },
  { key: "ipAddress", header: "IP" },
  { key: "lastUsedAt", header: "Last Used" },
  { key: "isCurrent", header: "Current" },
  { key: "actions", header: "Actions" },
];

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function SessionRow({
  session,
  isDeletePending,
  onDelete,
}: {
  session: AuthSession;
  isDeletePending: boolean;
  onDelete: (id: string) => void;
}) {
  return (
    <TableRow key={session.id}>
      <TableCell>{session.clientId}</TableCell>
      <TableCell>{session.deviceInfo ?? "-"}</TableCell>
      <TableCell>{session.ipAddress ?? "-"}</TableCell>
      <TableCell>{formatDate(session.lastUsedAt)}</TableCell>
      <TableCell>
        {session.isCurrent ? <Tag type="green">Current</Tag> : null}
      </TableCell>
      <TableCell>
        <Button
          kind="ghost"
          size="sm"
          disabled={session.isCurrent || isDeletePending}
          onClick={() => onDelete(session.id)}
        >
          Revoke
        </Button>
      </TableCell>
    </TableRow>
  );
}

export default function SessionsSection() {
  const sessionsQuery = useSessions();
  const deleteSession = useDeleteSession();

  return (
    <Tile>
      <h3 style={{ marginBottom: "1rem" }}>Active Sessions</h3>

      <QueryErrorNotification error={sessionsQuery.error} title="Failed to load sessions" />

      {sessionsQuery.isLoading && !sessionsQuery.data && (
        <DataTableSkeleton headers={headers} rowCount={3} />
      )}

      {sessionsQuery.data && (
        <DataTable rows={[]} headers={headers}>
          {() => (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    {headers.map((h) => (
                      <TableHeader key={h.key}>{h.header}</TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sessionsQuery.data.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={headers.length}>
                        No sessions found.
                      </TableCell>
                    </TableRow>
                  )}
                  {sessionsQuery.data.map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      isDeletePending={deleteSession.isPending}
                      onDelete={(id) => deleteSession.mutate(id)}
                    />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DataTable>
      )}
    </Tile>
  );
}
