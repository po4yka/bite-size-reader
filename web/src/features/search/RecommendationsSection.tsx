import { useNavigate } from "react-router-dom";
import { InlineLoading, Tag, Tile } from "@carbon/react";
import { useRecommendations } from "../../hooks/useSummaries";

export function RecommendationsSection() {
  const navigate = useNavigate();
  const { data, isLoading } = useRecommendations();

  if (isLoading) {
    return <InlineLoading description="Loading recommendations..." />;
  }

  const items = data?.recommendations ?? [];
  if (items.length === 0) return null;

  return (
    <div>
      <h3 style={{ marginBottom: "0.5rem" }}>
        {data?.reason === "based_on_reading_history" ? "Recommended for you" : "Unread articles"}
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {items.map((item) => (
          <Tile
            key={item.id}
            style={{ cursor: "pointer" }}
            onClick={() => navigate(`/library/${item.id}`)}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>{item.title}</p>
                {item.tldr && (
                  <p style={{ fontSize: "0.875rem", color: "#525252", marginBottom: "0.5rem" }}>
                    {item.tldr}
                  </p>
                )}
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                  {(item.topicTags ?? []).slice(0, 3).map((tag: string) => (
                    <Tag key={tag} type="gray" size="sm">
                      {tag}
                    </Tag>
                  ))}
                </div>
              </div>
              {item.readingTimeMin != null && (
                <span style={{ fontSize: "0.75rem", color: "#6f6f6f", whiteSpace: "nowrap", marginLeft: "1rem" }}>
                  {item.readingTimeMin} min
                </span>
              )}
            </div>
          </Tile>
        ))}
      </div>
    </div>
  );
}
