import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Button,
  ButtonSet,
  InlineLoading,
  InlineNotification,
  ProgressBar,
  Select,
  SelectItem,
  SkeletonText,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Tag,
  Tile,
} from "@carbon/react";
import { Play, PauseFilled, StopFilled } from "@carbon/icons-react";
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

function riskTagType(risk: string): "green" | "red" | "gray" | "warm-gray" {
  if (risk === "low") return "green";
  if (risk === "medium") return "warm-gray";
  if (risk === "high") return "red";
  return "gray";
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
    // Cleanup audio on summary change
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

  // Restore scroll position from the last saved offset on initial load.
  const restoredRef = useRef(false);
  useEffect(() => {
    const offset = summaryQuery.data?.lastReadOffset;
    if (!restoredRef.current && offset && offset > 100) {
      restoredRef.current = true;
      window.scrollTo({ top: offset, behavior: "instant" });
    }
  }, [summaryQuery.data?.lastReadOffset]);

  // Debounce-save reading position 500ms after scroll stops.
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
    // Generate + play
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
    <section className="page-section article-reader-shell">
      {summaryQuery.isPending && (
        <div className="article-skeleton">
          <SkeletonText heading width="60%" />
          <SkeletonText paragraph lineCount={1} width="40%" />
          <SkeletonText paragraph lineCount={5} />
          <SkeletonText paragraph lineCount={5} />
        </div>
      )}
      <QueryErrorNotification error={summaryQuery.error} title="Failed to load article" />

      {detail && (
        <>
          <h1>{detail.title}</h1>
          <div className="article-meta-row">
            <p className="page-subtitle">
              {detail.domain} · {detail.readingTimeMin} min read
            </p>
            <Tag type="blue">Confidence {(detail.confidence * 100).toFixed(0)}%</Tag>
            <Tag type={riskTagType(detail.hallucinationRisk)}>Risk {detail.hallucinationRisk}</Tag>
            <Tag type="gray">{readProgress}% read</Tag>
          </div>

          <ProgressBar
            className="article-reader-progress"
            label="Reading progress"
            value={readProgress}
            helperText={`${readProgress}% scrolled`}
          />

          <Tile className="reader-controls">
            <div className="reader-control-grid">
              <Select
                id="reader-text-scale"
                labelText="Text size"
                value={readerTextScale}
                onChange={(event) => setReaderTextScale(event.currentTarget.value as ReaderTextScale)}
              >
                <SelectItem value="sm" text="Compact" />
                <SelectItem value="md" text="Default" />
                <SelectItem value="lg" text="Large" />
              </Select>
              <Select
                id="reader-density"
                labelText="Line density"
                value={readerDensity}
                onChange={(event) => setReaderDensity(event.currentTarget.value as ReaderDensity)}
              >
                <SelectItem value="compact" text="Compact" />
                <SelectItem value="comfortable" text="Comfortable" />
              </Select>
            </div>
            <div className="form-actions">
              <Button kind="ghost" size="sm" onClick={() => void handleCopySummary()}>
                Copy summary
              </Button>
              <Button kind="ghost" size="sm" onClick={() => void handleShare()}>
                Share
              </Button>
            </div>
            {copyState === "success" && (
              <InlineNotification
                kind="success"
                title="Copied"
                subtitle="Summary text or URL copied to clipboard."
                hideCloseButton
              />
            )}
            {copyState === "error" && (
              <InlineNotification
                kind="warning"
                title="Copy failed"
                subtitle="Clipboard access is blocked in this browser context."
                hideCloseButton
              />
            )}
          </Tile>

          <ButtonSet>
            <Button kind="secondary" disabled={readMutation.isSuccess || readMutation.isPending} onClick={() => readMutation.mutate()}>
              {readMutation.isSuccess ? "Marked as read" : "Mark as read"}
            </Button>
            <Button kind="secondary" onClick={() => favoriteMutation.mutate(undefined)}>
              Toggle favorite
            </Button>
            <Button kind="secondary" onClick={() => setIsCollectionModalOpen(true)}>
              Add to collection
            </Button>
            <Button
              kind="secondary"
              renderIcon={audioState === "playing" ? PauseFilled : audioState === "paused" ? Play : Play}
              disabled={audioState === "loading"}
              onClick={() => void handleListenToggle()}
            >
              {audioState === "loading" ? "Generating..." : audioState === "playing" ? "Pause" : audioState === "paused" ? "Resume" : "Listen"}
            </Button>
            {(audioState === "playing" || audioState === "paused") && (
              <Button kind="ghost" renderIcon={StopFilled} onClick={handleStopAudio}>
                Stop
              </Button>
            )}
          </ButtonSet>

          <div className="form-actions">
            <Button kind="tertiary" size="sm" onClick={() => window.open(detail.url, "_blank", "noopener,noreferrer")}>
              Open original
            </Button>
            <Button kind="ghost" size="sm" onClick={() => setShowContent((prev) => !prev)}>
              {showContent ? "Hide full content" : "Show full content"}
            </Button>
            {exportPdfMutation.isPending ? (
              <InlineLoading description="Exporting PDF…" />
            ) : (
              <Button kind="ghost" size="sm" onClick={() => exportPdfMutation.mutate(summaryId)}>
                Export PDF
              </Button>
            )}
          </div>

          {audioState === "error" && audioError && (
            <InlineNotification
              kind="error"
              title="Audio error"
              subtitle={audioError}
              onCloseButtonClick={() => { setAudioState("idle"); setAudioError(null); }}
            />
          )}

          <Tabs>
            <TabList aria-label="Article tabs" contained>
              <Tab>Summary</Tab>
              <Tab>Details</Tab>
              <Tab>Entities</Tab>
              <Tab>Highlights</Tab>
            </TabList>
            <TabPanels>
              <TabPanel>
                <Tile className={`article-summary-tile article-text-${readerTextScale} article-density-${readerDensity}`}>
                  {splitParagraphs(detail.summary250).map((part) => (
                    <p key={`summary250-${part.slice(0, 32)}`}>{part}</p>
                  ))}
                  {detail.summary1000 && (
                    <>
                      <h3>Detailed Summary</h3>
                      {splitParagraphs(detail.summary1000).map((part) => (
                        <p key={`summary1000-${part.slice(0, 32)}`}>{part}</p>
                      ))}
                    </>
                  )}
                  {showContent && (
                    <>
                      <h3>Source Content</h3>
                      {contentQuery.isFetching && <InlineLoading description="Loading source content…" />}
                      <QueryErrorNotification error={contentQuery.error} title="Could not load source content" />
                      {contentQuery.data?.content && (
                        <pre
                          className={`content-preview article-content-preview article-text-${readerTextScale} article-density-${readerDensity}`}
                        >
                          {contentQuery.data.content}
                        </pre>
                      )}
                    </>
                  )}
                </Tile>
              </TabPanel>
              <TabPanel>
                <Tile>
                  <h3>Key ideas</h3>
                  <ul>
                    {detail.keyIdeas.map((idea) => (
                      <li key={idea}>{idea}</li>
                    ))}
                  </ul>

                  <h3>Key stats</h3>
                  <div className="article-stats-grid">
                    {detail.keyStats.map((stat) => (
                      <article key={`${stat.label}-${stat.value}`} className="article-stat">
                        <p className="muted">{stat.label}</p>
                        <p>
                          <strong>{stat.value}</strong>
                        </p>
                        {stat.sourceExcerpt && <p className="muted">{stat.sourceExcerpt}</p>}
                      </article>
                    ))}
                    {detail.keyStats.length === 0 && <p className="muted">No structured stats extracted.</p>}
                  </div>
                </Tile>
              </TabPanel>
              <TabPanel>
                <Tile>
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
                </Tile>
              </TabPanel>
              <TabPanel>
                <HighlightsPanel summaryId={summaryId} />
              </TabPanel>
            </TabPanels>
          </Tabs>

          <AddToCollectionModal
            open={isCollectionModalOpen}
            summaryId={summaryId}
            onClose={() => setIsCollectionModalOpen(false)}
          />
        </>
      )}
    </section>
  );
}
