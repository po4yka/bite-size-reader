import { Tag } from "@carbon/react";

export interface TagPill {
  id: number;
  name: string;
  color: string | null;
  source?: string;
}

export interface TagPillsProps {
  tags: TagPill[];
  onRemove?: (tagId: number) => void;
}

export default function TagPills({ tags, onRemove }: TagPillsProps) {
  if (tags.length === 0) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
      {tags.map((tag) => (
        <Tag
          key={tag.id}
          type="cool-gray"
          size="sm"
          filter={Boolean(onRemove)}
          onClose={() => onRemove?.(tag.id)}
          style={
            tag.color
              ? { backgroundColor: tag.color, color: "#fff", borderColor: tag.color }
              : undefined
          }
        >
          {tag.name}
        </Tag>
      ))}
    </div>
  );
}
