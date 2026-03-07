function snakeToCamel(value: string): string {
  return value.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

export function normalizeKeys<T>(input: T): T {
  if (Array.isArray(input)) {
    return input.map((item) => normalizeKeys(item)) as T;
  }

  if (input && typeof input === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
      result[snakeToCamel(key)] = normalizeKeys(value);
    }
    return result as T;
  }

  return input;
}
