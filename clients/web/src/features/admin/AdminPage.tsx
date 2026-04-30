import { BracketTab, BracketTabList, BracketTabPanel, BracketTabPanels, BracketTabs } from "../../design";
import AdminUsers from "./AdminUsers";
import AdminJobs from "./AdminJobs";
import AdminHealth from "./AdminHealth";
import AdminMetrics from "./AdminMetrics";
import AdminAuditLog from "./AdminAuditLog";

export default function AdminPage() {
  return (
    <section
      className="page-section admin-page"
      style={{
        maxWidth: "var(--frost-strip-7, 1232px)",
        padding: "var(--frost-pad-page, 32px)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section, 48px)",
      }}
    >
      <h1>Admin</h1>

      <BracketTabs>
        <BracketTabList aria-label="Admin tabs">
          <BracketTab>Users</BracketTab>
          <BracketTab>Jobs</BracketTab>
          <BracketTab>Health</BracketTab>
          <BracketTab>Metrics</BracketTab>
          <BracketTab>Audit Log</BracketTab>
        </BracketTabList>
        <BracketTabPanels>
          <BracketTabPanel>
            <AdminUsers />
          </BracketTabPanel>
          <BracketTabPanel>
            <AdminJobs />
          </BracketTabPanel>
          <BracketTabPanel>
            <AdminHealth />
          </BracketTabPanel>
          <BracketTabPanel>
            <AdminMetrics />
          </BracketTabPanel>
          <BracketTabPanel>
            <AdminAuditLog />
          </BracketTabPanel>
        </BracketTabPanels>
      </BracketTabs>
    </section>
  );
}
