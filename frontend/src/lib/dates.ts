// Week and date helpers. Pure functions, no scoring, no validation.
// Week 1 starts on horizon_start (a Monday) and every week is 7 days:
//   week N starts on horizon_start + 7*(N-1) and ends 6 days later (Sunday).
// Everything is handled in UTC so the answer does not change with the
// controller's time zone.

const DAY_MS = 86_400_000;

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** "2027-01-04" (or a full ISO stamp) -> Date at UTC midnight. NaN date if unparseable. */
function parseIso(iso: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso?.trim() ?? "");
  if (!m) return new Date(NaN);
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

function toIso(d: Date): string {
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

/** First day (Monday) of `week`, as "YYYY-MM-DD". */
export function weekStart(horizonStart: string, week: number): string {
  const start = parseIso(horizonStart);
  if (Number.isNaN(start.getTime())) return "";
  return toIso(new Date(start.getTime() + (week - 1) * 7 * DAY_MS));
}

/** Last day (Sunday) of `week`, as "YYYY-MM-DD". */
export function weekEnd(horizonStart: string, week: number): string {
  const start = parseIso(horizonStart);
  if (Number.isNaN(start.getTime())) return "";
  return toIso(new Date(start.getTime() + (week * 7 - 1) * DAY_MS));
}

/** "2027-05-24" -> "24 May 2027". Unparseable input comes back unchanged. */
export function formatDate(iso: string): string {
  const d = parseIso(iso);
  if (Number.isNaN(d.getTime())) return iso ?? "";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** Which week contains `isoDate`. 1-based; 0 when the date is before week 1 or unparseable. */
export function weekOf(horizonStart: string, isoDate: string): number {
  const start = parseIso(horizonStart);
  const day = parseIso(isoDate);
  if (Number.isNaN(start.getTime()) || Number.isNaN(day.getTime())) return 0;
  const diffDays = Math.floor((day.getTime() - start.getTime()) / DAY_MS);
  if (diffDays < 0) return 0;
  return Math.floor(diffDays / 7) + 1;
}

/** "24 May 2027 – 30 May 2027" for one week. */
export function weekRangeLabel(horizonStart: string, week: number): string {
  return `${formatDate(weekStart(horizonStart, week))} – ${formatDate(weekEnd(horizonStart, week))}`;
}
