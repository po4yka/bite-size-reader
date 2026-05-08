import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useSummariesList } from "../../hooks/useSummaries";
import type { SummaryCompact } from "../../api/types";

const FILTERS = [
  { key: "ALL", label: "ALL" },
  { key: "HIGH", label: "HIGH SIGNAL" },
  { key: "SAVED", label: "SAVED" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

/** Map a 0–1 confidence score to a sig-* class, mirroring the prototype's sigClass(). */
function sigClass(score: number): string {
  if (score >= 0.9) return "sig-critical";
  if (score >= 0.7) return "sig-high";
  if (score >= 0.3) return "sig-mid";
  return "sig-low";
}

/** Format ISO timestamp to short time string, e.g. "14:32" or "MON 09:15". */
function fmtTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `${hh}:${mm}`;
  const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  return `${days[d.getDay()]} ${hh}:${mm}`;
}

/** Estimated row height (px). Real height is measured by the virtualizer's
 * dynamic-measurement path, but a sane initial estimate keeps the scrollbar
 * stable on first paint. Matches the existing .queue li line-height in CSS. */
const ROW_ESTIMATE_PX = 28;

export default function LibraryPage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [cursor, setCursor] = useState(0);
  const parentRef = useRef<HTMLDivElement>(null);

  const summariesQuery = useSummariesList({
    limit: 100,
    offset: 0,
    isRead: undefined,
    isFavorited: filter === "SAVED" ? true : undefined,
    sort: "created_at_desc",
  });

  const summaries: SummaryCompact[] = summariesQuery.data?.summaries ?? [];

  // Filter by HIGH SIGNAL: items that have been favorited
  const visible =
    filter === "HIGH"
      ? summaries.filter((s) => s.isFavorited === true)
      : summaries;

  const total = summariesQuery.data?.pagination.total ?? visible.length;
  const pending = visible.filter((s) => !s.isRead).length;

  // React Compiler skips memoising components that touch useVirtualizer
  // because the hook returns functions; this is documented and intentional
  // (see TanStack Virtual issues). The advisory is a warning-only signal.
  // eslint-disable-next-line
  const rowVirtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_ESTIMATE_PX,
    overscan: 8,
  });

  // Clamp cursor on data changes
  useEffect(() => {
    if (visible.length > 0) {
      setCursor((c) => Math.min(c, visible.length - 1));
    }
  }, [visible.length]);

  // Keyboard navigation (disabled on mobile — no physical keyboard).
  // After cursor moves, scroll the active row into view via the virtualizer.
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (window.matchMedia("(max-width: 768px)").matches) return;
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        setCursor((c) => {
          const next = Math.min(c + 1, visible.length - 1);
          rowVirtualizer.scrollToIndex(next, { align: "auto" });
          return next;
        });
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        setCursor((c) => {
          const next = Math.max(c - 1, 0);
          rowVirtualizer.scrollToIndex(next, { align: "auto" });
          return next;
        });
      } else if (e.key === "Enter" && visible[cursor]) {
        navigate(`/library/${visible[cursor].id}`);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [cursor, visible, navigate, rowVirtualizer]);

  return (
    <main style={{ maxWidth: "var(--strip-7, var(--frost-strip-7))", padding: "0 calc(var(--char, 8px) * 4)" }}>
      {/* Toolbar */}
      <div className="queue-toolbar">
        <div className="meta">
          <span>INBOX</span>
          <span className="dot">∙</span>
          <span className="pending">{String(pending).padStart(3, " ").trim()} PENDING</span>
          <span className="dot">∙</span>
          <span>{total} TOTAL</span>
        </div>
        <div className="filters">
          {FILTERS.map((f, i) => (
            <span key={f.key} style={{ display: "contents" }}>
              {i > 0 && <span className="dot">∙</span>}
              <button
                className={filter === f.key ? "active" : undefined}
                onClick={() => {
                  setFilter(f.key);
                  setCursor(0);
                }}
              >
                {f.label}
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Column header */}
      <div className="queue-cols">
        <div>CAPTURED</div>
        <div></div>
        <div>SOURCE</div>
        <div></div>
        <div>TITLE</div>
        <div>TOPICS</div>
        <div>SIGNAL</div>
      </div>

      {/* Row list */}
      {summariesQuery.isLoading && !summariesQuery.data ? (
        <div style={{ padding: "var(--line, 16px) 0", opacity: 0.5, textTransform: "uppercase", letterSpacing: "1px" }}>
          LOADING…
        </div>
      ) : visible.length === 0 ? (
        <div style={{ padding: "var(--line, 16px) 0", opacity: 0.5, textTransform: "uppercase", letterSpacing: "1px" }}>
          INBOX ZERO
        </div>
      ) : (
        // Virtualized container: parentRef is the scroll element; the inner
        // <ul> is sized to the total list height so the native scrollbar tracks
        // the full dataset. Only the rows in `getVirtualItems()` mount in the
        // DOM (overscan keeps a few off-screen rows ready). Each row is
        // absolute-positioned at translateY(virtualRow.start) and shares the
        // same .row classNames + grid columns used by the (non-virtualized)
        // header above, so column alignment is preserved.
        <div
          ref={parentRef}
          id="queue-list"
          style={{ maxHeight: "70vh", overflow: "auto" }}
        >
          <ul
            className="queue"
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              position: "relative",
              margin: 0,
              padding: 0,
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const item = visible[virtualRow.index];
              if (!item) return null;
              const conf = (item as SummaryCompact & { confidence?: number }).confidence ?? 0.5;
              const sig = sigClass(conf);
              const isCursor = virtualRow.index === cursor;
              return (
                <li
                  key={item.id}
                  ref={rowVirtualizer.measureElement}
                  data-index={virtualRow.index}
                  className={`row ${sig}${isCursor ? " cursor" : ""}`}
                  data-id={item.id}
                  data-idx={virtualRow.index}
                  onClick={() => navigate(`/article/${item.id}`)}
                  onMouseEnter={() => setCursor(virtualRow.index)}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <span className="timestamp">{fmtTime(item.createdAt)}</span>
                  <span className="dot">∙</span>
                  <span className="source">{item.domain}</span>
                  <span className="dot">∙</span>
                  <span className="title">{item.title}</span>
                  <span className="topics">{item.topicTags.join(" ∙ ")}</span>
                  <span className="signal">{conf.toFixed(3)}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Ingest status */}
      <div className="ingest">
        <span>INGEST</span>
        <span className="dot">∙</span>
        <span className="pulse">SYNC ACTIVE</span>
        <span className="blink"></span>
      </div>
    </main>
  );
}
