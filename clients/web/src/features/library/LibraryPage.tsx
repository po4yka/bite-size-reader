import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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

export default function LibraryPage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [cursor, setCursor] = useState(0);

  const summariesQuery = useSummariesList({
    limit: 100,
    offset: 0,
    isRead: filter === "HIGH" ? undefined : undefined,
    isFavorited: filter === "SAVED" ? true : undefined,
    sort: "created_at_desc",
  });

  const summaries: SummaryCompact[] = summariesQuery.data?.summaries ?? [];

  // Filter by HIGH SIGNAL: items with confidence >= 0.7
  const visible =
    filter === "HIGH"
      ? summaries.filter((s) => (s as SummaryCompact & { confidence?: number }).confidence !== undefined
          ? ((s as SummaryCompact & { confidence?: number }).confidence ?? 0) >= 0.7
          : true)
      : summaries;

  const total = summariesQuery.data?.pagination.total ?? visible.length;
  const pending = visible.filter((s) => !s.isRead).length;

  // Clamp cursor on data changes
  useEffect(() => {
    if (visible.length > 0) {
      setCursor((c) => Math.min(c, visible.length - 1));
    }
  }, [visible.length]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, visible.length - 1));
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
      } else if (e.key === "Enter" && visible[cursor]) {
        navigate(`/article/${visible[cursor].id}`);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [cursor, visible, navigate]);

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
        <ul className="queue" id="queue-list">
          {visible.map((item, idx) => {
            const conf = (item as SummaryCompact & { confidence?: number }).confidence ?? 0.5;
            const sig = sigClass(conf);
            const isCursor = idx === cursor;
            return (
              <li
                key={item.id}
                className={`row ${sig}${isCursor ? " cursor" : ""}`}
                data-id={item.id}
                data-idx={idx}
                onClick={() => navigate(`/article/${item.id}`)}
                onMouseEnter={() => setCursor(idx)}
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
