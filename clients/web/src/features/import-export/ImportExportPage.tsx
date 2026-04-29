import { useCallback, useState } from "react";
import {
  Button,
  Checkbox,
  FileUploader,
  InlineNotification,
  NumberInput,
  RadioButton,
  RadioButtonGroup,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  TextInput,
} from "../../design";
import { useImportFile } from "../../hooks/useImportExport";
import { getExportUrl } from "../../api/importExport";
import ImportJobStatus from "./ImportJobStatus";
import ImportHistory from "./ImportHistory";

function detectFormat(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "json") return "JSON";
  if (ext === "csv") return "CSV";
  if (ext === "html" || ext === "htm") return "Netscape HTML";
  return "Unknown";
}

export default function ImportExportPage() {
  // --- Import state ---
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [detectedFormat, setDetectedFormat] = useState<string>("");
  const [summarize, setSummarize] = useState(false);
  const [createTags, setCreateTags] = useState(true);
  const [collectionId, setCollectionId] = useState<number | undefined>(undefined);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  const importMutation = useImportFile();

  // --- Export state ---
  const [exportFormat, setExportFormat] = useState("json");
  const [exportTag, setExportTag] = useState("");
  const [exportCollectionId, setExportCollectionId] = useState<number | undefined>(undefined);

  const handleFileChange = useCallback(
    (_event: React.SyntheticEvent<HTMLElement>) => {
      const input = _event.target as HTMLInputElement;
      const file = input.files?.[0] ?? null;
      setSelectedFile(file);
      setDetectedFormat(file ? detectFormat(file.name) : "");
    },
    [],
  );

  function handleImport(): void {
    if (!selectedFile) return;
    importMutation.mutate(
      {
        file: selectedFile,
        options: {
          summarize,
          createTags,
          collectionId,
        },
      },
      {
        onSuccess: (job) => {
          setActiveJobId(job.id);
          setSelectedFile(null);
          setDetectedFormat("");
        },
      },
    );
  }

  function handleExport(): void {
    const url = getExportUrl(
      exportFormat,
      exportTag || undefined,
      exportCollectionId,
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  const mutationError = importMutation.error;

  return (
    <section className="page-section">
      <h1 style={{ marginBottom: "1rem" }}>Import / Export</h1>

      {mutationError && (
        <InlineNotification
          kind="error"
          title="Import failed"
          subtitle={(mutationError as Error).message}
          hideCloseButton
          style={{ marginBottom: "1rem" }}
        />
      )}

      <Tabs>
        <TabList aria-label="Import/Export tabs">
          <Tab>Import</Tab>
          <Tab>Export</Tab>
        </TabList>
        <TabPanels>
          {/* --- Import Tab --- */}
          <TabPanel>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: "32rem" }}>
              <FileUploader
                accept={[".html", ".json", ".csv"]}
                buttonLabel="Choose file"
                filenameStatus="edit"
                labelDescription="Supported formats: JSON, CSV, Netscape HTML"
                labelTitle="Upload bookmarks file"
                onChange={handleFileChange}
                onDelete={() => {
                  setSelectedFile(null);
                  setDetectedFormat("");
                }}
              />

              {detectedFormat && (
                <p className="cds--label">
                  Detected format: <strong>{detectedFormat}</strong>
                </p>
              )}

              <Checkbox
                id="import-summarize"
                labelText="Summarize content"
                checked={summarize}
                onChange={(_event: React.ChangeEvent<HTMLInputElement>, { checked }: { checked: boolean }) =>
                  setSummarize(checked)
                }
              />

              <Checkbox
                id="import-create-tags"
                labelText="Create tags from imported tags"
                checked={createTags}
                onChange={(_event: React.ChangeEvent<HTMLInputElement>, { checked }: { checked: boolean }) =>
                  setCreateTags(checked)
                }
              />

              <NumberInput
                id="import-collection-id"
                label="Target collection ID (optional)"
                min={1}
                value={collectionId ?? ""}
                onChange={(_event: unknown, { value }: { value: number | string }) => {
                  const num = typeof value === "number" ? value : parseInt(String(value), 10);
                  setCollectionId(Number.isNaN(num) ? undefined : num);
                }}
                allowEmpty
              />

              <Button
                kind="primary"
                onClick={handleImport}
                disabled={!selectedFile || importMutation.isPending}
              >
                {importMutation.isPending ? "Importing..." : "Import"}
              </Button>
            </div>

            {activeJobId != null && (
              <ImportJobStatus jobId={activeJobId} />
            )}

            <div style={{ marginTop: "2rem" }}>
              <ImportHistory />
            </div>
          </TabPanel>

          {/* --- Export Tab --- */}
          <TabPanel>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: "32rem" }}>
              <RadioButtonGroup
                legendText="Export format"
                name="export-format"
                valueSelected={exportFormat}
                onChange={(value) => setExportFormat(String(value ?? "json"))}
              >
                <RadioButton id="export-json" labelText="JSON" value="json" />
                <RadioButton id="export-csv" labelText="CSV" value="csv" />
                <RadioButton id="export-html" labelText="Netscape HTML" value="html" />
              </RadioButtonGroup>

              <TextInput
                id="export-tag"
                labelText="Filter by tag (optional)"
                value={exportTag}
                onChange={(e) => setExportTag(e.currentTarget.value)}
                placeholder="e.g. programming"
              />

              <NumberInput
                id="export-collection-id"
                label="Filter by collection ID (optional)"
                min={1}
                value={exportCollectionId ?? ""}
                onChange={(_event: unknown, { value }: { value: number | string }) => {
                  const num = typeof value === "number" ? value : parseInt(String(value), 10);
                  setExportCollectionId(Number.isNaN(num) ? undefined : num);
                }}
                allowEmpty
              />

              <Button kind="primary" onClick={handleExport}>
                Download
              </Button>
            </div>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </section>
  );
}
