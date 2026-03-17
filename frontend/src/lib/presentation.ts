const IMPORT_PREFIX_RE = /^(Transcript|Notes)\s+[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\s+/i;
const RELATIVE_TIME_FORMATTER = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function formatDate(value: string | null | undefined, fallback = "Unknown"): string {
  if (!value) {
    return fallback;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString();
}

export function formatDateTime(value: string | null | undefined, fallback = "Unknown"): string {
  if (!value) {
    return fallback;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

export function formatDueDate(value: string | null | undefined): string {
  return formatDate(value, "not specified");
}

export function formatSourceLabel(value: string | null | undefined): string {
  if (!value) {
    return "Imported meeting";
  }
  const normalized = value.trim().toLowerCase();
  if (normalized === "google_drive") {
    return "Google Meet transcript";
  }
  if (normalized === "gemini_notes") {
    return "Google Meet notes";
  }
  return normalized
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

export function formatMeetingTitle(value: string | null | undefined): string {
  if (!value) {
    return "Untitled meeting";
  }

  let title = value.replace(/^[^\w(]+/, "").trim();
  title = title.replace(IMPORT_PREFIX_RE, "");
  title = title.replace(/\s*-\s*Notes by Gemini$/i, "");
  title = title.replace(/\s*-\s*Transcript$/i, "");
  title = title.replace(/\s+/g, " ").trim();

  if (/^Meeting started /i.test(title)) {
    return "Imported meeting";
  }
  return title || "Untitled meeting";
}

export function formatRelativeTime(value: string | number | Date | null | undefined): string {
  if (!value) {
    return "Just now";
  }

  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return typeof value === "string" ? value : "Just now";
  }

  const diffMs = parsed.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const absMinutes = Math.abs(diffMinutes);

  if (absMinutes < 1) {
    return "Just now";
  }
  if (absMinutes < 60) {
    return RELATIVE_TIME_FORMATTER.format(diffMinutes, "minute");
  }

  const diffHours = Math.round(diffMinutes / 60);
  const absHours = Math.abs(diffHours);
  if (absHours < 24) {
    return RELATIVE_TIME_FORMATTER.format(diffHours, "hour");
  }

  const diffDays = Math.round(diffHours / 24);
  const absDays = Math.abs(diffDays);
  if (absDays < 7) {
    return RELATIVE_TIME_FORMATTER.format(diffDays, "day");
  }
  if (absDays < 28) {
    return RELATIVE_TIME_FORMATTER.format(Math.round(diffDays / 7), "week");
  }

  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: parsed.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}
