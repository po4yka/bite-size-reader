import { Tab, TabList, TabPanel, TabPanels, Tabs } from "../../design";
import AdminUsers from "./AdminUsers";
import AdminJobs from "./AdminJobs";
import AdminHealth from "./AdminHealth";
import AdminMetrics from "./AdminMetrics";
import AdminAuditLog from "./AdminAuditLog";

export default function AdminPage() {
  return (
    <section className="page-section">
      <h1>Admin</h1>

      <Tabs>
        <TabList aria-label="Admin tabs">
          <Tab>Users</Tab>
          <Tab>Jobs</Tab>
          <Tab>Health</Tab>
          <Tab>Metrics</Tab>
          <Tab>Audit Log</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <AdminUsers />
          </TabPanel>
          <TabPanel>
            <AdminJobs />
          </TabPanel>
          <TabPanel>
            <AdminHealth />
          </TabPanel>
          <TabPanel>
            <AdminMetrics />
          </TabPanel>
          <TabPanel>
            <AdminAuditLog />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </section>
  );
}
