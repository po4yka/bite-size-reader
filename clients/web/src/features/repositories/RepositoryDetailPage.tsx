import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BracketButton,
  BrutalistCard,
  BrutalistModal,
  BrutalistSkeletonText,
  StatusBadge,
} from "../../design";
import {
  fetchRepository,
  reanalyzeRepository,
  deleteRepository,
} from "../../api/repositories";
import type { RepositoryAnalysis, Maturity, HallucinationRisk } from "../../api/repositories";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

/* ─── style helpers ─────────────────────────────────────────────────── */

const sectionLabel: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "1px",
  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
  margin: "0 0 8px",
};

const monoBody: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "13px",
  fontWeight: 500,
  lineHeight: "130%",
  letterSpacing: "0.4px",
  color: "var(--frost-ink)",
};

const chip: React.CSSProperties = {
  fontFamily: "var(--frost-font-mono)",
  fontSize: "11px",
  fontWeight: 500,
  letterSpacing: "0.5px",
  border: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
  padding: "2px 8px",
};

/* ─── helpers ─────────────────────────────────────────────────────────── */

function maturitySeverity(m: Maturity): "info" | "warn" | "alarm" {
  if (m === "abandoned") return "alarm";
  if (m === "prototype" || m === "alpha") return "warn";
  return "info";
}

function hallucinationSeverity(r: HallucinationRisk): "info" | "warn" | "alarm" {
  if (r === "high") return "alarm";
  if (r === "medium") return "warn";
  return "info";
}

function confidenceSeverity(c: number): "info" | "warn" | "alarm" {
  if (c >= 0.7) return "info";
  if (c >= 0.4) return "warn";
  return "alarm";
}

function LanguagesBar({ languages }: { languages: Record<string, number> }) {
  const entries = Object.entries(languages);
  if (!entries.length) return null;
  const total = entries.reduce((s, [, v]) => s + v, 0);
  const sorted = [...entries].sort(([, a], [, b]) => b - a);

  return (
    <div>
      <p style={sectionLabel}>Languages</p>
      <div
        style={{
          display: "flex",
          height: "8px",
          border: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
          overflow: "hidden",
        }}
        role="img"
        aria-label="Language distribution"
      >
        {sorted.map(([lang, bytes], i) => (
          <div
            key={lang}
            title={`${lang}: ${((bytes / total) * 100).toFixed(1)}%`}
            style={{
              flex: bytes,
              background:
                i === 0
                  ? "var(--frost-ink)"
                  : `color-mix(in oklch, var(--frost-ink) ${70 - i * 12}%, transparent)`,
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px 16px",
          marginTop: "8px",
        }}
      >
        {sorted.slice(0, 6).map(([lang, bytes]) => (
          <span key={lang} style={{ ...monoBody, fontSize: "11px" }}>
            {lang}
            <span
              style={{
                marginLeft: "4px",
                color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
              }}
            >
              {((bytes / total) * 100).toFixed(1)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function AnalysisCard({ analysis }: { analysis: RepositoryAnalysis }) {
  const [archOpen, setArchOpen] = useState(false);
  const isLongArch = analysis.architecture_summary.length > 300;

  return (
    <BrutalistCard>
      <p style={sectionLabel}>Analysis</p>

      {/* Purpose */}
      <div style={{ marginBottom: "var(--frost-gap-section, 48px)" }}>
        <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "6px" }}>Purpose</p>
        <blockquote
          style={{
            ...monoBody,
            borderLeft: "2px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
            paddingLeft: "12px",
            margin: 0,
            fontStyle: "normal",
          }}
        >
          {analysis.purpose}
        </blockquote>
      </div>

      {/* Tech stack */}
      {analysis.tech_stack.length > 0 && (
        <div style={{ marginBottom: "var(--frost-gap-row, 8px)" }}>
          <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "6px" }}>Tech stack</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {analysis.tech_stack.map((t) => (
              <span key={t} style={chip}>{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* Architecture */}
      {analysis.architecture_summary && (
        <div style={{ marginBottom: "var(--frost-gap-row, 8px)", marginTop: "12px" }}>
          <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "6px" }}>Architecture</p>
          <div
            style={{
              ...monoBody,
              overflow: "hidden",
              maxHeight: !archOpen && isLongArch ? "4.5em" : "none",
              position: "relative",
            }}
          >
            {analysis.architecture_summary}
          </div>
          {isLongArch && (
            <button
              type="button"
              onClick={() => setArchOpen((o) => !o)}
              aria-expanded={archOpen}
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "11px",
                fontWeight: 800,
                letterSpacing: "1px",
                textTransform: "uppercase",
                background: "none",
                border: "none",
                color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)",
                cursor: "pointer",
                padding: "4px 0",
              }}
            >
              {archOpen ? "[ Show less ]" : "[ Show more ]"}
            </button>
          )}
        </div>
      )}

      {/* Key concepts */}
      {analysis.key_concepts.length > 0 && (
        <div style={{ marginBottom: "var(--frost-gap-row, 8px)", marginTop: "12px" }}>
          <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "6px" }}>Key concepts</p>
          <dl style={{ margin: 0, display: "flex", flexDirection: "column", gap: "6px" }}>
            {analysis.key_concepts.map(({ term, explanation }) => (
              <div key={term}>
                <dt
                  style={{
                    ...monoBody,
                    fontWeight: 800,
                    textTransform: "uppercase",
                    fontSize: "11px",
                    letterSpacing: "1px",
                    display: "inline",
                  }}
                >
                  {term}
                </dt>
                <dd
                  style={{
                    ...monoBody,
                    color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)",
                    margin: "0 0 0 1ch",
                    display: "inline",
                  }}
                >
                  — {explanation}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* Code patterns */}
      {analysis.code_patterns.length > 0 && (
        <div style={{ marginBottom: "var(--frost-gap-row, 8px)", marginTop: "12px" }}>
          <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "6px" }}>Code patterns</p>
          <ul style={{ margin: 0, padding: "0 0 0 16px" }}>
            {analysis.code_patterns.map(({ name, description }) => (
              <li key={name} style={{ ...monoBody, marginBottom: "4px" }}>
                <span style={{ fontWeight: 800 }}>{name}</span>
                {" — "}
                <span style={{ color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)" }}>
                  {description}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Use cases */}
      {analysis.use_cases.length > 0 && (
        <div style={{ marginBottom: "var(--frost-gap-row, 8px)", marginTop: "12px" }}>
          <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "6px" }}>Use cases</p>
          <ul style={{ margin: 0, padding: "0 0 0 16px" }}>
            {analysis.use_cases.map((u) => (
              <li key={u} style={monoBody}>{u}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Target audience */}
      {analysis.target_audience && (
        <div style={{ marginTop: "12px" }}>
          <p style={{ ...sectionLabel, fontSize: "10px", marginBottom: "4px" }}>Target audience</p>
          <p style={monoBody}>{analysis.target_audience}</p>
        </div>
      )}

      {/* Metadata badges */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
          marginTop: "16px",
          paddingTop: "16px",
          borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)",
        }}
      >
        <StatusBadge
          severity={maturitySeverity(analysis.maturity)}
          title={`Maturity: ${analysis.maturity}`}
        />
        <StatusBadge
          severity={hallucinationSeverity(analysis.hallucination_risk)}
          title={`Hallucination risk: ${analysis.hallucination_risk}`}
        />
        <StatusBadge
          severity={confidenceSeverity(analysis.confidence)}
          title={`Confidence: ${(analysis.confidence * 100).toFixed(0)}%`}
        />
      </div>
    </BrutalistCard>
  );
}

/* ─── main page ─────────────────────────────────────────────────────── */

export default function RepositoryDetailPage() {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [isReanalyzing, setIsReanalyzing] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [readmeOpen, setReadmeOpen] = useState(false);

  const id = Number(repositoryId);

  const repoQuery = useQuery({
    queryKey: ["repository", id],
    queryFn: () => fetchRepository(id),
    enabled: !Number.isNaN(id),
  });

  const repo = repoQuery.data;

  async function handleReanalyze() {
    if (!repo || isReanalyzing) return;
    setIsReanalyzing(true);
    try {
      await reanalyzeRepository(repo.id);
      await queryClient.invalidateQueries({ queryKey: ["repository", id] });
    } finally {
      setIsReanalyzing(false);
    }
  }

  async function handleDelete() {
    if (!repo || isDeleting) return;
    setIsDeleting(true);
    try {
      await deleteRepository(repo.id);
      await queryClient.invalidateQueries({ queryKey: ["repositories"] });
      navigate("/repositories");
    } finally {
      setIsDeleting(false);
      setDeleteOpen(false);
    }
  }

  if (repoQuery.isLoading) {
    return (
      <main
        style={{
          maxWidth: "var(--frost-strip-5, 880px)",
          padding: "var(--frost-pad-page, 32px)",
        }}
      >
        <BrutalistCard>
          <BrutalistSkeletonText heading width="50%" />
          <BrutalistSkeletonText paragraph lineCount={3} />
          <BrutalistSkeletonText paragraph lineCount={5} />
        </BrutalistCard>
      </main>
    );
  }

  if (repoQuery.error || !repo) {
    return (
      <main
        style={{
          maxWidth: "var(--frost-strip-5, 880px)",
          padding: "var(--frost-pad-page, 32px)",
        }}
      >
        <QueryErrorNotification
          error={repoQuery.error}
          title="Failed to load repository"
        />
      </main>
    );
  }

  return (
    <main
      style={{
        maxWidth: "var(--frost-strip-5, 880px)",
        padding: "0 var(--frost-pad-page, 32px) var(--frost-gap-page, 64px)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section, 48px)",
      }}
    >
      {/* Header */}
      <div
        style={{
          paddingTop: "var(--frost-pad-page, 32px)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--frost-half-line, 8px)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          <h1
            style={{
              fontFamily: "var(--frost-font-mono)",
              fontSize: "22px",
              fontWeight: 800,
              letterSpacing: "0.5px",
              textTransform: "none",
              margin: 0,
              wordBreak: "break-word",
            }}
          >
            {repo.full_name}
          </h1>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", flexShrink: 0 }}>
            <BracketButton
              size="sm"
              as="a"
              href={`https://github.com/${repo.full_name}`}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open on GitHub"
            >
              GitHub
            </BracketButton>
            <BracketButton
              size="sm"
              isLoading={isReanalyzing}
              onClick={() => void handleReanalyze()}
              aria-label="Re-analyze repository"
            >
              Re-analyze
            </BracketButton>
            <BracketButton
              size="sm"
              danger
              onClick={() => setDeleteOpen(true)}
              aria-label="Delete repository"
            >
              Delete
            </BracketButton>
          </div>
        </div>

        {/* Metadata strip */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px 16px",
            fontFamily: "var(--frost-font-mono)",
            fontSize: "12px",
            fontWeight: 500,
            letterSpacing: "0.4px",
            color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)",
          }}
        >
          <span>★ {repo.stars.toLocaleString()}</span>
          <span>{repo.forks.toLocaleString()} forks</span>
          {repo.watchers > 0 && <span>{repo.watchers.toLocaleString()} watchers</span>}
          {repo.primary_language && <span>{repo.primary_language}</span>}
          {repo.license_spdx && <span>{repo.license_spdx}</span>}
          {repo.is_archived && (
            <StatusBadge severity="warn" title="Archived" />
          )}
          {repo.is_fork && (
            <StatusBadge severity="info" title="Fork" />
          )}
          {repo.is_starred && (
            <span
              aria-label="Starred by you"
              style={{ fontSize: "12px" }}
            >
              Starred
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {repo.description && (
        <p
          style={{
            ...monoBody,
            color: "color-mix(in oklch, var(--frost-ink) 80%, transparent)",
            margin: 0,
          }}
        >
          {repo.description}
        </p>
      )}

      {/* Topics */}
      {repo.topics.length > 0 && (
        <div>
          <p style={sectionLabel}>Topics</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {repo.topics.map((t) => (
              <span key={t} style={chip}>#{t}</span>
            ))}
          </div>
        </div>
      )}

      {/* Languages bar */}
      {Object.keys(repo.languages).length > 0 && (
        <LanguagesBar languages={repo.languages} />
      )}

      {/* Analysis */}
      {repo.analysis ? (
        <AnalysisCard analysis={repo.analysis} />
      ) : repo.pending_analysis ? (
        <BrutalistCard>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              fontFamily: "var(--frost-font-mono)",
              fontSize: "13px",
              fontWeight: 500,
              letterSpacing: "0.4px",
              color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: "10px",
                height: "10px",
                border: "1px solid var(--frost-ink)",
                animation: "frost-blinker 0.8s steps(2, start) infinite",
              }}
              aria-hidden="true"
            />
            Indexing — analysis will be ready after the next sync.
          </div>
        </BrutalistCard>
      ) : null}

      {/* README excerpt */}
      {repo.readme_excerpt && (
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "8px",
            }}
          >
            <p style={sectionLabel}>README excerpt</p>
            <button
              type="button"
              onClick={() => setReadmeOpen((o) => !o)}
              aria-expanded={readmeOpen}
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "11px",
                fontWeight: 800,
                letterSpacing: "1px",
                textTransform: "uppercase",
                background: "none",
                border: "none",
                color: "color-mix(in oklch, var(--frost-ink) 70%, transparent)",
                cursor: "pointer",
                padding: 0,
              }}
            >
              {readmeOpen ? "[ Collapse ]" : "[ Expand ]"}
            </button>
          </div>
          {readmeOpen && (
            <div
              style={{
                maxHeight: "30vh",
                overflowY: "auto",
                border: "1px solid color-mix(in oklch, var(--frost-ink) 40%, transparent)",
                padding: "16px",
                fontFamily: "var(--frost-font-mono)",
                fontSize: "12px",
                fontWeight: 500,
                lineHeight: "150%",
                letterSpacing: "0.3px",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {repo.readme_excerpt}
            </div>
          )}
        </div>
      )}

      {/* Delete confirm dialog */}
      <BrutalistModal
        open={deleteOpen}
        size="sm"
        danger
        modalHeading="Delete repository"
        modalLabel="Confirm"
        primaryButtonText={isDeleting ? "Deleting…" : "Delete"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={isDeleting}
        onRequestSubmit={() => void handleDelete()}
        onRequestClose={() => setDeleteOpen(false)}
      >
        <p style={monoBody}>
          Remove <strong>{repo.full_name}</strong> from Ratatoskr? This cannot be undone.
        </p>
      </BrutalistModal>
    </main>
  );
}
