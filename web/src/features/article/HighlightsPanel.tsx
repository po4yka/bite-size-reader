import { useState } from "react";
import {
  Accordion,
  AccordionItem,
  Button,
  IconButton,
  InlineNotification,
  NumberInput,
  Select,
  SelectItem,
  SkeletonText,
  Tag,
  TextArea,
  TextInput,
  Tile,
} from "@carbon/react";
import { Checkmark, Close, Edit, TrashCan } from "@carbon/icons-react";
import {
  useHighlights,
  useCreateHighlight,
  useUpdateHighlight,
  useDeleteHighlight,
} from "../../hooks/useSummaries";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import type { Highlight } from "../../api/types";

interface HighlightsPanelProps {
  summaryId: number;
}

const COLOR_OPTIONS = [
  { value: "#FEF3C7", label: "Yellow" },
  { value: "#D1FAE5", label: "Green" },
  { value: "#DBEAFE", label: "Blue" },
  { value: "#FEE2E2", label: "Red" },
] as const;

type ColorValue = (typeof COLOR_OPTIONS)[number]["value"];

function colorTagType(color: string | null): "warm-gray" | "green" | "blue" | "red" {
  if (color === "#D1FAE5") return "green";
  if (color === "#DBEAFE") return "blue";
  if (color === "#FEE2E2") return "red";
  return "warm-gray";
}

function truncate(text: string, maxLen: number): string {
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

function formatDate(isoString: string): string {
  if (!isoString) return "";
  try {
    return new Date(isoString).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return isoString;
  }
}

interface HighlightRowProps {
  highlight: Highlight;
  summaryId: number;
}

function HighlightRow({ highlight, summaryId }: HighlightRowProps) {
  const [editing, setEditing] = useState(false);
  const [editNote, setEditNote] = useState(highlight.note ?? "");
  const [editColor, setEditColor] = useState<string>(highlight.color ?? "#FEF3C7");

  const updateMutation = useUpdateHighlight(summaryId);
  const deleteMutation = useDeleteHighlight(summaryId);

  function handleSave(): void {
    updateMutation.mutate(
      {
        highlightId: highlight.id,
        payload: {
          note: editNote || undefined,
          color: editColor || undefined,
        },
      },
      {
        onSuccess: () => setEditing(false),
      },
    );
  }

  function handleCancel(): void {
    setEditNote(highlight.note ?? "");
    setEditColor(highlight.color ?? "#FEF3C7");
    setEditing(false);
  }

  return (
    <div
      className="highlight-row"
      style={{
        borderLeft: `4px solid ${highlight.color ?? "#FEF3C7"}`,
        paddingLeft: "0.75rem",
        marginBottom: "1rem",
      }}
    >
      <p style={{ margin: "0 0 0.25rem" }}>{truncate(highlight.text, 100)}</p>

      {editing ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <TextInput
            id={`highlight-note-${highlight.id}`}
            labelText="Note"
            value={editNote}
            onChange={(e) => setEditNote(e.currentTarget.value)}
            size="sm"
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {COLOR_OPTIONS.map((opt) => (
              <Tag
                key={opt.value}
                type={colorTagType(opt.value)}
                style={{
                  cursor: "pointer",
                  outline: editColor === opt.value ? "2px solid #0f62fe" : "none",
                }}
                onClick={() => setEditColor(opt.value as ColorValue)}
              >
                {opt.label}
              </Tag>
            ))}
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <IconButton
              label="Save"
              size="sm"
              disabled={updateMutation.isPending}
              onClick={handleSave}
            >
              <Checkmark />
            </IconButton>
            <IconButton label="Cancel" size="sm" kind="ghost" onClick={handleCancel}>
              <Close />
            </IconButton>
          </div>
          <QueryErrorNotification error={updateMutation.error} title="Update failed" />
        </div>
      ) : (
        <>
          {highlight.note && <p className="muted" style={{ margin: "0 0 0.25rem", fontSize: "0.875rem" }}>{highlight.note}</p>}
          <p className="muted" style={{ margin: "0 0 0.25rem", fontSize: "0.75rem" }}>{formatDate(highlight.createdAt)}</p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <IconButton
              label="Edit"
              size="sm"
              kind="ghost"
              onClick={() => setEditing(true)}
            >
              <Edit />
            </IconButton>
            <IconButton
              label="Delete"
              size="sm"
              kind="ghost"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(highlight.id)}
            >
              <TrashCan />
            </IconButton>
          </div>
          <QueryErrorNotification error={deleteMutation.error} title="Delete failed" />
        </>
      )}
    </div>
  );
}

export default function HighlightsPanel({ summaryId }: HighlightsPanelProps) {
  const highlightsQuery = useHighlights(summaryId);
  const createMutation = useCreateHighlight(summaryId);

  const [newText, setNewText] = useState("");
  const [newStartOffset, setNewStartOffset] = useState(0);
  const [newEndOffset, setNewEndOffset] = useState(0);
  const [newNote, setNewNote] = useState("");
  const [newColor, setNewColor] = useState("#FEF3C7");

  function handleSaveNew(): void {
    if (!newText.trim()) return;
    createMutation.mutate(
      {
        text: newText.trim(),
        startOffset: newStartOffset,
        endOffset: newEndOffset,
        note: newNote.trim() || undefined,
        color: newColor || undefined,
      },
      {
        onSuccess: () => {
          setNewText("");
          setNewStartOffset(0);
          setNewEndOffset(0);
          setNewNote("");
          setNewColor("#FEF3C7");
        },
      },
    );
  }

  return (
    <Tile>
      <h4 style={{ marginTop: 0, marginBottom: "1rem" }}>Highlights</h4>

      {highlightsQuery.isLoading && <SkeletonText paragraph lineCount={3} />}
      <QueryErrorNotification error={highlightsQuery.error} title="Failed to load highlights" />

      {!highlightsQuery.isLoading && !highlightsQuery.error && (
        <>
          {(highlightsQuery.data?.length ?? 0) === 0 ? (
            <InlineNotification
              kind="info"
              title="No highlights yet."
              subtitle="Select text in the article to highlight it."
              hideCloseButton
            />
          ) : (
            <div>
              {highlightsQuery.data?.map((highlight) => (
                <HighlightRow key={highlight.id} highlight={highlight} summaryId={summaryId} />
              ))}
            </div>
          )}

          <div style={{ marginTop: "1rem" }}>
          <Accordion>
            <AccordionItem title="Add Highlight">
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <TextArea
                  id="new-highlight-text"
                  labelText="Highlighted text"
                  value={newText}
                  onChange={(e) => setNewText(e.currentTarget.value)}
                  rows={3}
                />
                <NumberInput
                  id="new-highlight-start"
                  label="Start offset"
                  value={newStartOffset}
                  min={0}
                  onChange={(_e, { value }) => {
                    if (typeof value === "number") setNewStartOffset(value);
                  }}
                />
                <NumberInput
                  id="new-highlight-end"
                  label="End offset"
                  value={newEndOffset}
                  min={0}
                  onChange={(_e, { value }) => {
                    if (typeof value === "number") setNewEndOffset(value);
                  }}
                />
                <TextInput
                  id="new-highlight-note"
                  labelText="Note (optional)"
                  value={newNote}
                  onChange={(e) => setNewNote(e.currentTarget.value)}
                />
                <Select
                  id="new-highlight-color"
                  labelText="Color"
                  value={newColor}
                  onChange={(e) => setNewColor(e.currentTarget.value)}
                >
                  {COLOR_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} text={opt.label} />
                  ))}
                </Select>
                <Button
                  size="sm"
                  disabled={createMutation.isPending || !newText.trim()}
                  onClick={handleSaveNew}
                >
                  {createMutation.isPending ? "Saving..." : "Save Highlight"}
                </Button>
                <QueryErrorNotification error={createMutation.error} title="Failed to create highlight" />
              </div>
            </AccordionItem>
          </Accordion>
          </div>
        </>
      )}
    </Tile>
  );
}
