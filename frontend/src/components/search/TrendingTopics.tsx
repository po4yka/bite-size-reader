import type { TrendingTopic } from "../../types/api";

interface TrendingTopicsProps {
  topics: TrendingTopic[];
  onTopicClick: (tag: string) => void;
}

export default function TrendingTopics({ topics, onTopicClick }: TrendingTopicsProps) {
  return (
    <div className="trending-topics">
      <h3 className="trending-topics-title">Trending Topics</h3>
      <div className="trending-topics-grid">
        {topics.map((topic) => (
          <button
            key={topic.tag}
            className="topic-chip"
            onClick={() => onTopicClick(topic.tag)}
          >
            <span className="topic-chip-name">{topic.tag}</span>
            <span className="topic-chip-count">{topic.count}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
