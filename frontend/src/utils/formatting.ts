export function formatPay(pay: number | null): string {
  if (pay === null) return "—";
  return `$${pay}/hr`;
}

export function formatDate(iso: string | null, fallback = "—"): string {
  if (!iso) return fallback;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(iso));
}

export function formatLocation(locations: string[]): string {
  if (locations.length === 0) return "—";
  if (locations.length <= 2) return locations.join(" · ");
  return `${locations[0]} +${locations.length - 1} more`;
}

export function formatConfidence(score: number | null): string {
  if (score === null) return "—";
  return `${Math.round(score * 100)}%`;
}

export function formatSource(source: string | null): string {
  if (!source) return "Unknown";
  if (source === "pittcsc") return "PittCSC";
  if (source === "ouckah") return "Ouckah";
  return source;
}
