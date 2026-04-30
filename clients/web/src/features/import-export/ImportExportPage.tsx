import { useCallback, useState } from "react";
import {
  BracketButton,
  BracketTab,
  BracketTabList,
  BracketTabPanel,
  BracketTabPanels,
  BracketTabs,
  Checkbox,
  FileUploader,
  MonoInput,
  NumberInput,
  RadioButton,
  RadioButtonGroup,
  StatusBadge,
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

const sectionLabelStyle: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase" as const,
  letterSpacing: "1px",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: 0,
};

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
    <main
      style={{
        maxWidth: "var(--frost-strip-7)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section)",
      }}
    >
      <h1
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-emph-size)",
          fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
          letterSpacing: "var(--frost-type-mono-emph-tracking)",
          textTransform: "uppercase",
          color: "var(--frost-ink)",
          margin: 0,
        }}
      >
        Import / Export
      </h1>

      {mutationError && (
        <StatusBadge
          severity="alarm"
          title="Import failed"
          subtitle={(mutationError as Error).message}
        />
      )}

      <BracketTabs>
        <BracketTabList aria-label="Import/Export tabs" className="import-export-tab-list">
          <BracketTab>Import</BracketTab>
          <BracketTab>Export</BracketTab>
        </BracketTabList>
        <BracketTabPanels>
          {/* --- Import Tab --- */}
          <BracketTabPanel>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--frost-gap-section)",
                paddingTop: "var(--frost-gap-row)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--frost-gap-row)",
                  maxWidth: "var(--frost-strip-4)",
                }}
              >
                <p style={sectionLabelStyle}>§ UPLOAD FILE</p>
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
                  <p
                    style={{
                      fontFamily: "var(--frost-font-mono)",
                      fontSize: "var(--frost-type-mono-xs-size)",
                      color: "var(--frost-ink)",
                      margin: 0,
                    }}
                  >
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

                <BracketButton
                  onClick={handleImport}
                  disabled={!selectedFile || importMutation.isPending}
                >
                  {importMutation.isPending ? "Importing..." : "Import"}
                </BracketButton>
              </div>

              {activeJobId != null && (
                <ImportJobStatus jobId={activeJobId} />
              )}

              <div>
                <ImportHistory />
              </div>
            </div>
          </BracketTabPanel>

          {/* --- Export Tab --- */}
          <BracketTabPanel>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--frost-gap-row)",
                maxWidth: "var(--frost-strip-4)",
                paddingTop: "var(--frost-gap-row)",
              }}
            >
              <p style={sectionLabelStyle}>§ EXPORT OPTIONS</p>
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

              <MonoInput
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

              <BracketButton onClick={handleExport}>
                Download
              </BracketButton>
            </div>
          </BracketTabPanel>
        </BracketTabPanels>
      </BracketTabs>
    </main>
  );
}
