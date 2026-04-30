import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  BracketButton,
  BrutalistSkeletonText,
  SparkLoading,
  StatusBadge,
} from "../../design";
import { getSummaryAudioUrl, generateSummaryAudio } from "../../api/summaries";
import {
  useMarkRead,
  useSummaryContent,
  useSummaryDetail,
  useToggleFavorite,
} from "../../hooks/useSummaries";
import AddToCollectionModal from "../../components/AddToCollectionModal";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import HighlightsPanel from "./HighlightsPanel";

function useSummaryId(): number {
  const params = useParams();
  return Number(params.id ?? 0);
}

function splitParagraphs(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** Map 0–1 confidence to sig label. */
function sigLabel(conf: number): string {
  if (conf >= 0.9) return "CRITICAL";
  if (conf >= 0.7) return "HIGH";
  if (conf >= 0.3) return "MID";
  return "LOW";
}

export default function ArticlePage() {
  const summaryId = useSummaryId();
  const navigate = useNavigate();

  const [showContent, setShowContent] = useState(false);
  const [isCollectionModalOpen, setIsCollectionModalOpen] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "success" | "error">("idle");
  const [readProgress, setReadProgress] = useState(0);
  const [audioState, setAudioState] = useState<"idle" | "loading" | "playing" | "paused" | "error">("idle");
  const [audioError, setAudioError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const summaryQuery = useSummaryDetail(summaryId);
  const contentQuery = useSummaryContent(summaryId, showContent);
  const readMutation = useMarkRead(summaryId);
  const favoriteMutation = useToggleFavorite(summaryId);

  useEffect(() => {
    readMutation.reset();
    setCopyState("idle");
    setReadProgress(0);
    setAudioState("idle");
    setAudioError(null);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
  }, [summaryId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let rafId: number | null = null;
    const updateProgress = () => {
      rafId = null;
      const doc = document.documentElement;
      const scrollHeight = doc.scrollHeight - window.innerHeight;
      if (scrollHeight <= 0) { setReadProgress(0); return; }
      setReadProgress(Math.max(0, Math.min(100, Math.round((window.scrollY / scrollHeight) * 100))));
    };
    const onScroll = () => { if (rafId === null) rafId = requestAnimationFrame(updateProgress); };
    updateProgress();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", updateProgress);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", updateProgress);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [showContent, summaryId]);

  const detail = summaryQuery.data;

  const entityTags = useMemo(() => {
    if (!detail) return [];
    return detail.entities.slice(0, 12);
  }, [detail]);

  async function handleCopySummary(): Promise<void> {
    if (!detail) return;
    try {
      const payload = [detail.tldr, detail.summary250, detail.summary1000]
        .map((p) => p.trim()).filter(Boolean).join("\n\n");
      await navigator.clipboard.writeText(payload);
      setCopyState("success");
    } catch {
      setCopyState("error");
    }
  }

  async function handleListenToggle(): Promise<void> {
    if (audioState === "playing" && audioRef.current) {
      audioRef.current.pause();
      setAudioState("paused");
      return;
    }
    if (audioState === "paused" && audioRef.current) {
      void audioRef.current.play();
      setAudioState("playing");
      return;
    }
    setAudioState("loading");
    setAudioError(null);
    try {
      const result = await generateSummaryAudio(summaryId);
      if (result.status === "error") {
        setAudioState("error");
        setAudioError(result.error ?? "Audio generation failed");
        return;
      }
      const audio = new Audio(getSummaryAudioUrl(summaryId));
      audio.onended = () => setAudioState("idle");
      audio.onerror = () => { setAudioState("error"); setAudioError("Failed to play audio"); };
      audioRef.current = audio;
      await audio.play();
      setAudioState("playing");
    } catch (err) {
      setAudioState("error");
      setAudioError(err instanceof Error ? err.message : "Audio generation failed");
    }
  }

  function handleStopAudio(): void {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    setAudioState("idle");
  }

  async function handleShare(): Promise<void> {
    if (!detail?.url) return;
    try {
      if (navigator.share) {
        await navigator.share({ title: detail.title, text: detail.tldr || detail.summary250, url: detail.url });
        return;
      }
      await navigator.clipboard.writeText(detail.url);
      setCopyState("success");
    } catch {
      setCopyState("error");
    }
  }

  return (
    <main style={{ maxWidth: "var(--strip-5, var(--frost-strip-5))", padding: "0 calc(var(--char, 8px) * 4)" }}>
      {/* Back nav */}
      <div className="detail-back">
        <button onClick={() => navigate(-1)}>← QUEUE</button>
        {detail && (
          <>
            <span className="dot">∙</span>
            <span>ITEM {String(detail.id).padStart(4, "0")}</span>
          </>
        )}
      </div>

      {/* Loading */}
      {summaryQuery.isPending && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "var(--line, 16px) 0" }}>
          <BrutalistSkeletonText heading width="60%" />
          <BrutalistSkeletonText paragraph lineCount={1} width="40%" />
          <BrutalistSkeletonText paragraph lineCount={5} />
        </div>
      )}
      <QueryErrorNotification error={summaryQuery.error} title="Failed to load article" />

      {detail && (
        <article className="detail">
          {/* Left sidebar — meta */}
          <aside className="meta">
            <dl>
              <div>
                <dt>SIGNAL</dt>
                <dd>{detail.confidence.toFixed(3)} ∙ {sigLabel(detail.confidence)}</dd>
              </div>
              <div>
                <dt>SOURCE</dt>
                <dd>{detail.domain}</dd>
              </div>
              <div>
                <dt>TOPICS</dt>
                <dd>{detail.topicTags.join(" ∙ ")}</dd>
              </div>
              <div>
                <dt>READ TIME</dt>
                <dd>~{detail.readingTimeMin} MIN</dd>
              </div>
              <div>
                <dt>CONFIDENCE</dt>
                <dd>{(detail.confidence * 100).toFixed(0)}%</dd>
              </div>
              <div>
                <dt>RISK</dt>
                <dd>{detail.hallucinationRisk}</dd>
              </div>
              <div>
                <dt>PROGRESS</dt>
                <dd>{readProgress}%</dd>
              </div>
            </dl>
          </aside>

          {/* Anchors sidebar */}
          <aside className="anchors" aria-label="Section anchors">
            <ol>
              <li>I</li>
              <li>II</li>
              <li>III</li>
              {detail.summary1000 && <li>IV</li>}
            </ol>
          </aside>

          {/* Main body */}
          <div className="body">
            {/* Title — mono ExtraBold uppercase, font-variation "wght" 720 */}
            <h1>{detail.title}</h1>

            {/* Meta line — mono uppercase 11px alpha 0.55 */}
            <h2
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: "11px",
                fontVariationSettings: '"wght" 500',
                fontWeight: 500,
                letterSpacing: "1px",
                textTransform: "uppercase",
                opacity: 0.55,
                margin: "0 0 var(--line, 16px)",
                fontStyle: "normal",
              }}
            >
              {detail.domain}
              {detail.tldr ? ` ∙ ${detail.tldr.slice(0, 80)}…` : ""}
            </h2>

            {/* Summary body — Source Serif 4 italic at reader scale */}
            {splitParagraphs(detail.summary250).map((part) => (
              <p key={`s250-${part.slice(0, 32)}`}>{part}</p>
            ))}

            {detail.summary1000 && (
              <>
                <h2>Detailed Summary</h2>
                {splitParagraphs(detail.summary1000).map((part) => (
                  <p key={`s1000-${part.slice(0, 32)}`}>{part}</p>
                ))}
              </>
            )}

            {/* Key ideas */}
            {detail.keyIdeas.length > 0 && (
              <>
                <h2>Key Ideas</h2>
                {detail.keyIdeas.map((idea) => (
                  <p key={idea}>— {idea}</p>
                ))}
              </>
            )}

            {/* Highlights panel (high-confidence items get spark hairline via queue.css) */}
            <HighlightsPanel summaryId={summaryId} />

            {/* Entities */}
            {entityTags.length > 0 && (
              <>
                <h2>Entities</h2>
                <p style={{ fontStyle: "normal", opacity: 0.7 }}>
                  {entityTags.map((e) => `${e.name} (${e.type})`).join(" ∙ ")}
                </p>
              </>
            )}

            {/* Source content toggle */}
            {showContent && (
              <>
                <h2>Source Content</h2>
                {contentQuery.isFetching && <SparkLoading status="active" description="Loading source content…" />}
                <QueryErrorNotification error={contentQuery.error} title="Could not load source content" />
                {contentQuery.data?.content && (
                  <pre
                    style={{
                      fontStyle: "normal",
                      fontFamily: "var(--frost-font-mono)",
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      opacity: 0.85,
                    }}
                  >
                    {contentQuery.data.content}
                  </pre>
                )}
              </>
            )}
          </div>
        </article>
      )}

      {/* Audio error */}
      {audioState === "error" && audioError && (
        <StatusBadge
          severity="alarm"
          title="Audio error"
          subtitle={audioError}
          dismissible
          onDismiss={() => { setAudioState("idle"); setAudioError(null); }}
        />
      )}

      {/* Copy feedback */}
      {copyState === "success" && (
        <StatusBadge severity="info" title="Copied" subtitle="Summary text or URL copied to clipboard." />
      )}
      {copyState === "error" && (
        <StatusBadge severity="warn" title="Copy failed" subtitle="Clipboard access is blocked in this browser context." />
      )}

      {/* Action toolbar — prototype style: [ OPEN ] [ ARCHIVE ] [ TAG ] */}
      {detail && (
        <div className="detail-actions">
          <BracketButton
            kind="tertiary"
            size="sm"
            onClick={() => window.open(detail.url, "_blank", "noopener,noreferrer")}
          >
            OPEN SOURCE
          </BracketButton>
          <span className="dot">∙</span>
          <BracketButton
            kind="secondary"
            size="sm"
            disabled={readMutation.isSuccess || readMutation.isPending}
            onClick={() => readMutation.mutate()}
          >
            {readMutation.isSuccess ? "ARCHIVED" : "ARCHIVE"}
          </BracketButton>
          <span className="dot">∙</span>
          <BracketButton
            kind="secondary"
            size="sm"
            onClick={() => favoriteMutation.mutate(undefined)}
          >
            SAVE
          </BracketButton>
          <span className="dot">∙</span>
          <BracketButton
            kind="ghost"
            size="sm"
            onClick={() => setIsCollectionModalOpen(true)}
          >
            TAG
          </BracketButton>
          <span className="dot">∙</span>
          <BracketButton
            kind="ghost"
            size="sm"
            onClick={() => void handleCopySummary()}
          >
            COPY
          </BracketButton>
          <span className="dot">∙</span>
          <BracketButton
            kind="ghost"
            size="sm"
            onClick={() => void handleShare()}
          >
            SHARE
          </BracketButton>
          <span className="dot">∙</span>
          <BracketButton
            kind="ghost"
            size="sm"
            disabled={audioState === "loading"}
            onClick={() => void handleListenToggle()}
          >
            {audioState === "loading" ? "GENERATING…"
              : audioState === "playing" ? "PAUSE"
              : audioState === "paused" ? "RESUME"
              : "LISTEN"}
          </BracketButton>
          {(audioState === "playing" || audioState === "paused") && (
            <>
              <span className="dot">∙</span>
              <BracketButton kind="ghost" size="sm" onClick={handleStopAudio}>STOP</BracketButton>
            </>
          )}
          <span className="dot">∙</span>
          <BracketButton
            kind="ghost"
            size="sm"
            onClick={() => setShowContent((p) => !p)}
          >
            {showContent ? "HIDE SOURCE" : "SHOW SOURCE"}
          </BracketButton>
        </div>
      )}

      {detail && (
        <AddToCollectionModal
          open={isCollectionModalOpen}
          summaryId={summaryId}
          onClose={() => setIsCollectionModalOpen(false)}
        />
      )}
    </main>
  );
}
