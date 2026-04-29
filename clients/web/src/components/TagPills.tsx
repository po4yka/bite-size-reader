import { Tag } from "../design";

type CarbonTagType =
  | "blue"
  | "red"
  | "green"
  | "purple"
  | "cyan"
  | "teal"
  | "magenta"
  | "gray"
  | "warm-gray"
  | "cool-gray"
  | "high-contrast";

const COLOR_TO_TAG_TYPE: Record<string, CarbonTagType> = {
  blue: "blue",
  red: "red",
  green: "green",
  purple: "purple",
  cyan: "cyan",
  teal: "teal",
  magenta: "magenta",
  gray: "gray",
  grey: "gray",
  orange: "warm-gray",
  yellow: "warm-gray",
  pink: "magenta",
  violet: "purple",
  indigo: "blue",
};

function mapColorToTagType(color: string | null): CarbonTagType {
  if (!color) return "cool-gray";
  const lower = color.toLowerCase();
  for (const [key, type] of Object.entries(COLOR_TO_TAG_TYPE)) {
    if (lower.includes(key)) return type;
  }
  return "cool-gray";
}

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
    <div className="tag-row">
      {tags.map((tag) => (
        <Tag
          key={tag.id}
          type={mapColorToTagType(tag.color)}
          size="sm"
          filter={Boolean(onRemove)}
          onClose={() => onRemove?.(tag.id)}
        >
          {tag.name}
        </Tag>
      ))}
    </div>
  );
}
