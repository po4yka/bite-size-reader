import { sanitizeUrl } from "../../utils/url";

interface ArticleContentProps {
  markdown: string;
}

function renderInline(text: string): (string | JSX.Element)[] {
  const parts: (string | JSX.Element)[] = [];
  // Process bold, italic, code, and links in a single pass
  const re = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\((.+?)\)/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const key = match.index;
    if (match[1]) parts.push(<strong key={key}>{match[1]}</strong>);
    else if (match[2]) parts.push(<em key={key}>{match[2]}</em>);
    else if (match[3]) parts.push(<code key={key}>{match[3]}</code>);
    else if (match[4] && match[5]) {
      parts.push(<a key={key} href={sanitizeUrl(match[5])} target="_blank" rel="noopener noreferrer">{match[4]}</a>);
    }
    last = match.index + match[0].length;
  }

  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function renderBlock(block: string, idx: number): JSX.Element {
  const trimmed = block.trim();

  // Headings
  if (trimmed.startsWith("### ")) return <h3 key={idx}>{renderInline(trimmed.slice(4))}</h3>;
  if (trimmed.startsWith("## ")) return <h2 key={idx}>{renderInline(trimmed.slice(3))}</h2>;
  if (trimmed.startsWith("# ")) return <h1 key={idx}>{renderInline(trimmed.slice(2))}</h1>;

  // List block (consecutive lines starting with -)
  const lines = trimmed.split("\n");
  if (lines.every((l) => l.trimStart().startsWith("- "))) {
    return (
      <ul key={idx}>
        {lines.map((l, i) => (
          <li key={i}>{renderInline(l.trimStart().slice(2))}</li>
        ))}
      </ul>
    );
  }

  return <p key={idx}>{renderInline(trimmed)}</p>;
}

export default function ArticleContent({ markdown }: ArticleContentProps) {
  const blocks = markdown.split(/\n{2,}/);
  return <div className="article-content">{blocks.map(renderBlock)}</div>;
}
