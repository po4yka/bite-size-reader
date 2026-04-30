import type { KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { BrutalistCard, SparkLoading, Tag } from "../../design";
import { useRecommendations } from "../../hooks/useSummaries";

export function RecommendationsSection() {
  const navigate = useNavigate();
  const { data, isLoading } = useRecommendations();

  function handleCardKeyDown(event: KeyboardEvent<HTMLDivElement>, id: number): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    navigate(`/library/${id}`);
  }

  if (isLoading) {
    return <SparkLoading description="Loading recommendations..." status="active" />;
  }

  const items = data?.recommendations ?? [];
  if (items.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-section)" }}>
      <p
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "var(--frost-type-mono-xs-size)",
          fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
          letterSpacing: "var(--frost-type-mono-emph-tracking)",
          textTransform: "uppercase",
          color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
          margin: 0,
        }}
      >
        §{" "}
        {data?.reason === "based_on_reading_history" ? "RECOMMENDED FOR YOU" : "UNREAD ARTICLES"}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--frost-gap-row)" }}>
        {items.map((item) => (
          <BrutalistCard
            key={item.id}
            style={{ cursor: "pointer" }}
            onClick={() => navigate(`/library/${item.id}`)}
            onKeyDown={(event) => handleCardKeyDown(event, item.id)}
            role="link"
            tabIndex={0}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-body-size)",
                    fontWeight: "var(--frost-type-mono-emph-weight)" as React.CSSProperties["fontWeight"],
                    color: "var(--frost-ink)",
                    margin: "0 0 var(--frost-gap-row) 0",
                  }}
                >
                  {item.title}
                </p>
                {item.tldr && (
                  <p
                    style={{
                      fontFamily: "var(--frost-font-mono)",
                      fontSize: "var(--frost-type-mono-body-size)",
                      color: "color-mix(in oklch, var(--frost-ink) 55%, transparent)",
                      margin: "0 0 var(--frost-gap-row) 0",
                    }}
                  >
                    {item.tldr}
                  </p>
                )}
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--frost-gap-inline)" }}>
                  {(item.topicTags ?? []).slice(0, 3).map((tag: string) => (
                    <Tag key={tag} type="gray" size="sm">
                      {tag}
                    </Tag>
                  ))}
                </div>
              </div>
              {item.readingTimeMin != null && (
                <span
                  style={{
                    fontFamily: "var(--frost-font-mono)",
                    fontSize: "var(--frost-type-mono-xs-size)",
                    color: "color-mix(in oklch, var(--frost-ink) 60%, transparent)",
                    whiteSpace: "nowrap",
                    marginLeft: "var(--frost-line)",
                  }}
                >
                  {item.readingTimeMin} min
                </span>
              )}
            </div>
          </BrutalistCard>
        ))}
      </div>
    </div>
  );
}
