import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  BracketButton,
  BracketTab,
  BracketTabList,
  BracketTabPanel,
  BracketTabPanels,
  BracketTabs,
  BrutalistCard,
  BrutalistSkeletonText,
  MonoProgressBar,
  MonoSelect,
  MonoSelectItem,
  SparkLoading,
  StatusBadge,
  Tag,
  Play,
  PauseFilled,
  StopFilled,
} from "../../design";
import { getSummaryAudioUrl, generateSummaryAudio } from "../../api/summaries";
import {
  useExportSummaryPdf,
  useMarkRead,
  useSaveReadingPosition,
  useSummaryContent,
  useSummaryDetail,
  useToggleFavorite,
} from "../../hooks/useSummaries";
import AddToCollectionModal from "../../components/AddToCollectionModal";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";
import HighlightsPanel from "./HighlightsPanel";

type ReaderTextScale = "sm" | "md" | "lg";
type ReaderDensity = "compact" | "comfortable";

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

export default function ArticlePage() {
  const summaryId = useSummaryId();

  const [showContent, setShowContent] = useState(false);
  const [isCollectionModalOpen, setIsCollectionModalOpen] = useState(false);
  const [readerTextScale, setReaderTextScale] = useState<ReaderTextScale>("md");
  const [readerDensity, setReaderDensity] = useState<ReaderDensity>("comfortable");
  const [copyState, setCopyState] = useState<"idle" | "success" | "error">("idle");
  const [readProgress, setReadProgress] = useState(0);
  const [audioState, setAudioState] = useState<"idle" | "loading" | "playing" | "paused" | "error">("idle");
  const [audioError, setAudioError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const summaryQuery = useSummaryDetail(summaryId);
  const contentQuery = useSummaryContent(summaryId, showContent);
  const readMutation = useMarkRead(summaryId);
  const favoriteMutation = useToggleFavorite(summaryId);
  const savePositionMutation = useSaveReadingPosition();
  const exportPdfMutation = useExportSummaryPdf();

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
      if (scrollHeight <= 0) {
        setReadProgress(0);
        return;
      }
      const nextProgress = Math.round((window.scrollY / scrollHeight) * 100);
      setReadProgress(Math.max(0, Math.min(100, nextProgress)));
    };

    const onScroll = () => {
      if (rafId === null) {
        rafId = requestAnimationFrame(updateProgress);
      }
    };

    updateProgress();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", updateProgress);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", updateProgress);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [showContent, summaryId]);

  const restoredRef = useRef(false);
  useEffect(() => {
    const offset = summaryQuery.data?.lastReadOffset;
    if (!restoredRef.current && offset && offset > 100) {
      restoredRef.current = true;
      window.scrollTo({ top: offset, behavior: "instant" });
    }
  }, [summaryQuery.data?.lastReadOffset]);

  useEffect(() => {
    if (summaryId <= 0) return;
    const timer = setTimeout(() => {
      savePositionMutation.mutate({
        summaryId,
        progress: readProgress,
        lastReadOffset: Math.round(window.scrollY),
      });
    }, 500);
    return () => clearTimeout(timer);
  }, [readProgress, summaryId]); // eslint-disable-line react-hooks/exhaustive-deps

  const detail = summaryQuery.data;

  const entityTags = useMemo(() => {
    if (!detail) return [];
    return detail.entities.slice(0, 12);
  }, [detail]);

  async function handleCopySummary(): Promise<void> {
    if (!detail) return;
    try {
      const payload = [detail.tldr, detail.summary250, detail.summary1000]
        .map((part) => part.trim())
        .filter(Boolean)
        .join("\n\n");
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
      audio.onerror = () => {
        setAudioState("error");
        setAudioError("Failed to play audio");
      };
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
        await navigator.share({
          title: detail.title,
          text: detail.tldr || detail.summary250,
          url: detail.url,
        });
        return;
      }
      await navigator.clipboard.writeText(detail.url);
      setCopyState("success");
    } catch {
      setCopyState("error");
    }
  }

  return (
    <main
      style={{
        maxWidth: "var(--frost-strip-5)",
        padding: "0 var(--frost-pad-page)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--frost-gap-section)",
      }}
    >
      {summaryQuery.isPending && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <BrutalistSkeletonText heading width="60%" />
          <BrutalistSkeletonText paragraph lineCount={1} width="40%" />
          <BrutalistSkeletonText paragraph lineCount={5} />
          <BrutalistSkeletonText paragraph lineCount={5} />
        </div>
      )}
      <QueryErrorNotification error={summaryQuery.error} title="Failed to load article" />

      {detail && (
        <>
          {/* Title block */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-page)" }}>
            <div>
              <h1
                style={{
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "var(--frost-type-mono-emph-size)",
                  fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                  letterSpacing: "var(--frost-type-mono-emph-tracking)",
                  textTransform: "uppercase",
                  color: "var(--frost-ink)",
                  margin: "0 0 8px 0",
                }}
              >
                {detail.title}
              </h1>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  flexWrap: "wrap",
                  fontFamily: "var(--frost-font-mono)",
                  fontSize: "11px",
                  fontWeight: 500,
                  letterSpacing: "1px",
                  textTransform: "uppercase",
                  color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                }}
              >
                <span>{detail.domain}</span>
                <span aria-hidden>·</span>
                <span>{detail.readingTimeMin} min read</span>
                <span aria-hidden>·</span>
                <span>Confidence {(detail.confidence * 100).toFixed(0)}%</span>
                <span aria-hidden>·</span>
                <span>Risk {detail.hallucinationRisk}</span>
                <span aria-hidden>·</span>
                <span>{readProgress}% read</span>
              </div>
            </div>

            <MonoProgressBar
              label="Reading progress"
              value={readProgress}
              helperText={`${readProgress}% scrolled`}
            />
          </div>

          {/* Reader controls card */}
          <BrutalistCard>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "var(--frost-gap-row)",
              }}
            >
              <MonoSelect
                id="reader-text-scale"
                labelText="Text size"
                value={readerTextScale}
                onChange={(event) => setReaderTextScale(event.currentTarget.value as ReaderTextScale)}
              >
                <MonoSelectItem value="sm" text="Compact" />
                <MonoSelectItem value="md" text="Default" />
                <MonoSelectItem value="lg" text="Large" />
              </MonoSelect>
              <MonoSelect
                id="reader-density"
                labelText="Line density"
                value={readerDensity}
                onChange={(event) => setReaderDensity(event.currentTarget.value as ReaderDensity)}
              >
                <MonoSelectItem value="compact" text="Compact" />
                <MonoSelectItem value="comfortable" text="Comfortable" />
              </MonoSelect>
            </div>
            <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
              <BracketButton kind="ghost" size="sm" onClick={() => void handleCopySummary()}>
                Copy summary
              </BracketButton>
              <BracketButton kind="ghost" size="sm" onClick={() => void handleShare()}>
                Share
              </BracketButton>
            </div>
            {copyState === "success" && (
              <StatusBadge
                severity="info"
                title="✓ Copied"
                subtitle="Summary text or URL copied to clipboard."
              />
            )}
            {copyState === "error" && (
              <StatusBadge
                severity="warn"
                title="Copy failed"
                subtitle="Clipboard access is blocked in this browser context."
              />
            )}
          </BrutalistCard>

          {/* Action buttons */}
          <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
            <BracketButton
              kind="secondary"
              disabled={readMutation.isSuccess || readMutation.isPending}
              onClick={() => readMutation.mutate()}
            >
              {readMutation.isSuccess ? "Marked as read" : "Mark as read"}
            </BracketButton>
            <BracketButton kind="secondary" onClick={() => favoriteMutation.mutate(undefined)}>
              Toggle favorite
            </BracketButton>
            <BracketButton kind="secondary" onClick={() => setIsCollectionModalOpen(true)}>
              Add to collection
            </BracketButton>
            <BracketButton
              kind="secondary"
              renderIcon={audioState === "playing" ? PauseFilled : Play}
              disabled={audioState === "loading"}
              onClick={() => void handleListenToggle()}
            >
              {audioState === "loading"
                ? "Generating..."
                : audioState === "playing"
                  ? "Pause"
                  : audioState === "paused"
                    ? "Resume"
                    : "Listen"}
            </BracketButton>
            {(audioState === "playing" || audioState === "paused") && (
              <BracketButton kind="ghost" renderIcon={StopFilled} onClick={handleStopAudio}>
                Stop
              </BracketButton>
            )}
          </div>

          {/* Secondary actions */}
          <div style={{ display: "flex", gap: "var(--frost-gap-row)", flexWrap: "wrap" }}>
            <BracketButton
              kind="tertiary"
              size="sm"
              onClick={() => window.open(detail.url, "_blank", "noopener,noreferrer")}
            >
              Open original
            </BracketButton>
            <BracketButton
              kind="ghost"
              size="sm"
              onClick={() => setShowContent((prev) => !prev)}
            >
              {showContent ? "Hide full content" : "Show full content"}
            </BracketButton>
            {exportPdfMutation.isPending ? (
              <SparkLoading status="active" description="Exporting PDF…" />
            ) : (
              <BracketButton kind="ghost" size="sm" onClick={() => exportPdfMutation.mutate(summaryId)}>
                Export PDF
              </BracketButton>
            )}
          </div>

          {audioState === "error" && audioError && (
            <StatusBadge
              severity="alarm"
              title="Audio error"
              subtitle={audioError}
              dismissible
              onDismiss={() => {
                setAudioState("idle");
                setAudioError(null);
              }}
            />
          )}

          {/* Tabs */}
          <BracketTabs>
            <BracketTabList aria-label="Article tabs" contained>
              <BracketTab>Summary</BracketTab>
              <BracketTab>Details</BracketTab>
              <BracketTab>Entities</BracketTab>
              <BracketTab>Highlights</BracketTab>
            </BracketTabList>
            <BracketTabPanels>
              <BracketTabPanel>
                {/* Article body — Source Serif 4 italic, reader-size */}
                <article
                  className={`article-text-${readerTextScale} article-density-${readerDensity}`}
                  style={{
                    fontFamily: "var(--frost-font-serif)",
                    fontSize: "var(--frost-type-serif-reader-size, 16px)",
                    fontWeight: 500,
                    fontStyle: "italic",
                    lineHeight: 1.55,
                    color: "var(--frost-ink)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                  }}
                >
                  {splitParagraphs(detail.summary250).map((part) => (
                    <p key={`summary250-${part.slice(0, 32)}`} style={{ margin: 0 }}>{part}</p>
                  ))}
                  {detail.summary1000 && (
                    <>
                      <h3
                        style={{
                          fontFamily: "var(--frost-font-mono)",
                          fontSize: "var(--frost-type-mono-emph-size)",
                          fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                          textTransform: "uppercase",
                          letterSpacing: "var(--frost-type-mono-emph-tracking)",
                          color: "var(--frost-ink)",
                          fontStyle: "normal",
                          margin: 0,
                        }}
                      >
                        Detailed Summary
                      </h3>
                      {splitParagraphs(detail.summary1000).map((part) => (
                        <p key={`summary1000-${part.slice(0, 32)}`} style={{ margin: 0 }}>{part}</p>
                      ))}
                    </>
                  )}
                  {showContent && (
                    <>
                      <h3
                        style={{
                          fontFamily: "var(--frost-font-mono)",
                          fontSize: "var(--frost-type-mono-emph-size)",
                          fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                          textTransform: "uppercase",
                          letterSpacing: "var(--frost-type-mono-emph-tracking)",
                          color: "var(--frost-ink)",
                          fontStyle: "normal",
                          margin: 0,
                        }}
                      >
                        Source Content
                      </h3>
                      {contentQuery.isFetching && (
                        <SparkLoading status="active" description="Loading source content…" />
                      )}
                      <QueryErrorNotification error={contentQuery.error} title="Could not load source content" />
                      {contentQuery.data?.content && (
                        <pre
                          className={`content-preview article-content-preview article-text-${readerTextScale} article-density-${readerDensity}`}
                          style={{ fontStyle: "normal", fontFamily: "var(--frost-font-mono)", margin: 0 }}
                        >
                          {contentQuery.data.content}
                        </pre>
                      )}
                    </>
                  )}
                </article>
              </BracketTabPanel>

              <BracketTabPanel>
                <BrutalistCard>
                  <h3
                    style={{
                      fontFamily: "var(--frost-font-mono)",
                      fontSize: "var(--frost-type-mono-emph-size)",
                      fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                      textTransform: "uppercase",
                      letterSpacing: "var(--frost-type-mono-emph-tracking)",
                      color: "var(--frost-ink)",
                      margin: 0,
                    }}
                  >
                    Key ideas
                  </h3>
                  <ul style={{ margin: 0, paddingLeft: "1.2em" }}>
                    {detail.keyIdeas.map((idea) => (
                      <li
                        key={idea}
                        style={{
                          fontFamily: "var(--frost-font-mono)",
                          fontSize: "var(--frost-type-mono-body-size)",
                          color: "var(--frost-ink)",
                        }}
                      >
                        {idea}
                      </li>
                    ))}
                  </ul>

                  <h3
                    style={{
                      fontFamily: "var(--frost-font-mono)",
                      fontSize: "var(--frost-type-mono-emph-size)",
                      fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                      textTransform: "uppercase",
                      letterSpacing: "var(--frost-type-mono-emph-tracking)",
                      color: "var(--frost-ink)",
                      margin: 0,
                    }}
                  >
                    Key stats
                  </h3>
                  <div className="article-stats-grid">
                    {detail.keyStats.map((stat) => (
                      <article key={`${stat.label}-${stat.value}`} className="article-stat">
                        <p
                          style={{
                            fontFamily: "var(--frost-font-mono)",
                            fontSize: "11px",
                            color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                            margin: 0,
                          }}
                        >
                          {stat.label}
                        </p>
                        <p style={{ fontFamily: "var(--frost-font-mono)", margin: 0 }}>
                          <strong>{stat.value}</strong>
                        </p>
                        {stat.sourceExcerpt && (
                          <p
                            style={{
                              fontFamily: "var(--frost-font-mono)",
                              fontSize: "11px",
                              color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                              margin: 0,
                            }}
                          >
                            {stat.sourceExcerpt}
                          </p>
                        )}
                      </article>
                    ))}
                    {detail.keyStats.length === 0 && (
                      <p
                        style={{
                          fontFamily: "var(--frost-font-mono)",
                          color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                          margin: 0,
                        }}
                      >
                        No structured stats extracted.
                      </p>
                    )}
                  </div>
                </BrutalistCard>
              </BracketTabPanel>

              <BracketTabPanel>
                <BrutalistCard>
                  <div className="tag-row">
                    {detail.topicTags.map((topic) => (
                      <Tag key={topic} type="cyan">
                        {topic}
                      </Tag>
                    ))}
                  </div>
                  <div className="tag-row">
                    {entityTags.map((entity) => (
                      <Tag key={`${entity.type}-${entity.name}`} type="warm-gray">
                        {entity.name} ({entity.type})
                      </Tag>
                    ))}
                  </div>
                </BrutalistCard>
              </BracketTabPanel>

              <BracketTabPanel>
                <HighlightsPanel summaryId={summaryId} />
              </BracketTabPanel>
            </BracketTabPanels>
          </BracketTabs>

          <AddToCollectionModal
            open={isCollectionModalOpen}
            summaryId={summaryId}
            onClose={() => setIsCollectionModalOpen(false)}
          />
        </>
      )}
    </main>
  );
}
