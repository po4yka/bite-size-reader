import { useRef, useState } from "react";
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
  { value: "yellow", cssVar: "var(--bsr-highlight-yellow)", label: "Yellow" },
  { value: "green", cssVar: "var(--bsr-highlight-green)", label: "Green" },
  { value: "blue", cssVar: "var(--bsr-highlight-blue)", label: "Blue" },
  { value: "red", cssVar: "var(--bsr-highlight-red)", label: "Red" },
] as const;

type ColorValue = (typeof COLOR_OPTIONS)[number]["value"];

/** Resolve a color value to its CSS variable. Falls back to yellow for legacy hex values. */
function resolveColorCss(color: string | null): string {
  const match = COLOR_OPTIONS.find((opt) => opt.value === color);
  if (match) return match.cssVar;
  // Legacy hex fallback
  if (color === "#D1FAE5") return "var(--bsr-highlight-green)";
  if (color === "#DBEAFE") return "var(--bsr-highlight-blue)";
  if (color === "#FEE2E2") return "var(--bsr-highlight-red)";
  return "var(--bsr-highlight-yellow)";
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

interface ColorPickerProps {
  selected: string;
  onChange: (value: ColorValue) => void;
}

function ColorPicker({ selected, onChange }: ColorPickerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    const items = containerRef.current?.querySelectorAll<HTMLElement>("[role='radio']");
    if (!items || items.length === 0) return;

    const currentIndex = Array.from(items).findIndex(
      (el) => el.getAttribute("data-color") === selected,
    );

    let nextIndex: number;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      nextIndex = (currentIndex + 1) % items.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      nextIndex = (currentIndex - 1 + items.length) % items.length;
    } else if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      const target = event.target as HTMLElement;
      const color = target.getAttribute("data-color") as ColorValue | null;
      if (color) onChange(color);
      return;
    } else {
      return;
    }

    const nextColor = items[nextIndex].getAttribute("data-color") as ColorValue | null;
    if (nextColor) {
      onChange(nextColor);
      items[nextIndex].focus();
    }
  }

  return (
    <div
      ref={containerRef}
      className="highlight-color-picker"
      role="radiogroup"
      aria-label="Highlight color"
      onKeyDown={handleKeyDown}
    >
      {COLOR_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`highlight-color-swatch${selected === opt.value ? " highlight-color-swatch--selected" : ""}`}
          role="radio"
          aria-checked={selected === opt.value}
          aria-label={opt.label}
          data-color={opt.value}
          tabIndex={selected === opt.value ? 0 : -1}
          onClick={() => onChange(opt.value as ColorValue)}
        >
          <span
            className="highlight-color-swatch__circle"
            style={{ backgroundColor: opt.cssVar }}
          />
          {opt.label}
        </button>
      ))}
    </div>
  );
}

interface HighlightRowProps {
  highlight: Highlight;
  summaryId: number;
}

function HighlightRow({ highlight, summaryId }: HighlightRowProps) {
  const [editing, setEditing] = useState(false);
  const [editNote, setEditNote] = useState(highlight.note ?? "");
  const [editColor, setEditColor] = useState<string>(highlight.color ?? "yellow");

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
    setEditColor(highlight.color ?? "yellow");
    setEditing(false);
  }

  return (
    <div
      className="highlight-row"
      style={{ borderLeftColor: resolveColorCss(highlight.color) }}
    >
      <p className="highlight-text">{truncate(highlight.text, 100)}</p>

      {editing ? (
        <div className="highlight-edit-form">
          <TextInput
            id={`highlight-note-${highlight.id}`}
            labelText="Note"
            value={editNote}
            onChange={(e) => setEditNote(e.currentTarget.value)}
            size="sm"
          />
          <ColorPicker selected={editColor} onChange={setEditColor} />
          <div className="highlight-actions">
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
          {highlight.note && <p className="muted highlight-note">{highlight.note}</p>}
          <p className="muted highlight-date">{formatDate(highlight.createdAt)}</p>
          <div className="highlight-actions">
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
  const [newColor, setNewColor] = useState("yellow");

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
          setNewColor("yellow");
        },
      },
    );
  }

  return (
    <Tile>
      <h4 className="highlight-heading">Highlights</h4>

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

          <div className="highlight-add-section">
          <Accordion>
            <AccordionItem title="Add Highlight">
              <div className="highlight-edit-form">
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
