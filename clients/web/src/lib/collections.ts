import type { Collection } from "../api/types";

/**
 * Flatten a nested collection tree into a flat array.
 * Each item's name is prefixed with its ancestor names separated by " / ".
 */
export function flattenCollections(input: Collection[]): Collection[] {
  const result: Collection[] = [];

  function walk(items: Collection[], prefix: string): void {
    for (const item of items) {
      result.push({
        ...item,
        name: prefix ? `${prefix} / ${item.name}` : item.name,
      });
      walk(item.children ?? [], prefix ? `${prefix} / ${item.name}` : item.name);
    }
  }

  walk(input, "");
  return result;
}
