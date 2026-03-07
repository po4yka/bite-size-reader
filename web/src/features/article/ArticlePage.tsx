import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  ButtonSet,
  InlineLoading,
  InlineNotification,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Tag,
  Tile,
} from "@carbon/react";
import { fetchSummary, fetchSummaryContent, markSummaryRead, toggleSummaryFavorite } from "../../api/summaries";
import AddToCollectionModal from "../../components/AddToCollectionModal";

function useSummaryId(): number {
  const params = useParams();
  return Number(params.id ?? 0);
}

export default function ArticlePage() {
  const summaryId = useSummaryId();
  const queryClient = useQueryClient();
  const [showContent, setShowContent] = useState(false);
  const [isCollectionModalOpen, setIsCollectionModalOpen] = useState(false);

  const summaryQuery = useQuery({
    queryKey: ["summary", summaryId],
    queryFn: () => fetchSummary(summaryId),
    enabled: Number.isFinite(summaryId) && summaryId > 0,
  });

  const contentQuery = useQuery({
    queryKey: ["summary-content", summaryId],
    queryFn: () => fetchSummaryContent(summaryId),
    enabled: showContent && Number.isFinite(summaryId) && summaryId > 0,
  });

  const readMutation = useMutation({
    mutationFn: () => markSummaryRead(summaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["summaries"] });
    },
  });

  const favoriteMutation = useMutation({
    mutationFn: () => toggleSummaryFavorite(summaryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["summaries"] });
      void queryClient.invalidateQueries({ queryKey: ["summary", summaryId] });
    },
  });

  const detail = summaryQuery.data;

  const entityTags = useMemo(() => {
    if (!detail) return [];
    return detail.entities.slice(0, 10);
  }, [detail]);

  return (
    <section className="page-section">
      {summaryQuery.isLoading && <InlineLoading description="Loading article..." />}
      {summaryQuery.error && (
        <InlineNotification
          kind="error"
          title="Failed to load article"
          subtitle={summaryQuery.error instanceof Error ? summaryQuery.error.message : "Unknown error"}
          hideCloseButton
        />
      )}

      {detail && (
        <>
          <h1>{detail.title}</h1>
          <p className="page-subtitle">
            {detail.domain} · {detail.readingTimeMin} min read
          </p>

          <ButtonSet>
            <Button kind="secondary" onClick={() => readMutation.mutate()}>
              Mark as read
            </Button>
            <Button kind="secondary" onClick={() => favoriteMutation.mutate()}>
              Toggle favorite
            </Button>
            <Button kind="secondary" onClick={() => setIsCollectionModalOpen(true)}>
              Add to collection
            </Button>
            <Button kind="tertiary" onClick={() => window.open(detail.url, "_blank", "noopener,noreferrer")}>
              Open original
            </Button>
            <Button kind="ghost" onClick={() => setShowContent((prev) => !prev)}>
              {showContent ? "Hide full content" : "Show full content"}
            </Button>
          </ButtonSet>

          <Tabs>
            <TabList aria-label="Article tabs" contained>
              <Tab>Summary</Tab>
              <Tab>Details</Tab>
              <Tab>Entities</Tab>
            </TabList>
            <TabPanels>
              <TabPanel>
                <Tile>
                  <p>{detail.summary250}</p>
                  {detail.summary1000 && (
                    <>
                      <h3>Detailed Summary</h3>
                      <p>{detail.summary1000}</p>
                    </>
                  )}
                  {showContent && contentQuery.data?.content && (
                    <>
                      <h3>Source Content</h3>
                      <pre className="content-preview">{contentQuery.data.content}</pre>
                    </>
                  )}
                </Tile>
              </TabPanel>
              <TabPanel>
                <Tile>
                  <p>
                    Confidence: <strong>{(detail.confidence * 100).toFixed(0)}%</strong>
                  </p>
                  <p>
                    Hallucination risk: <strong>{detail.hallucinationRisk}</strong>
                  </p>
                  <h3>Key ideas</h3>
                  <ul>
                    {detail.keyIdeas.map((idea) => (
                      <li key={idea}>{idea}</li>
                    ))}
                  </ul>
                  <h3>Key stats</h3>
                  <ul>
                    {detail.keyStats.map((stat) => (
                      <li key={`${stat.label}-${stat.value}`}>
                        {stat.label}: {stat.value}
                      </li>
                    ))}
                  </ul>
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
