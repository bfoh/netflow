/** The maintenance window a firmware step may run in (D-121): one helper for every approval.
 *  Times are typed and sent in UTC; the server allows at most 24 hours. */
export interface ApprovalWindow { start: string; end: string }

export const toUtcInput = (d: Date) => d.toISOString().slice(0, 16);
export const fromUtcInput = (v: string) => new Date(`${v}:00Z`).toISOString();

/** From five minutes ago (a clock a little behind still fits) to eight hours ahead. */
export function defaultWindow(now = Date.now()): ApprovalWindow {
  return { start: toUtcInput(new Date(now - 5 * 60 * 1000)), end: toUtcInput(new Date(now + 8 * 3600 * 1000)) };
}

export function windowBody(w: ApprovalWindow) {
  return { window_start: fromUtcInput(w.start), window_end: fromUtcInput(w.end) };
}

/** Why a window cannot be used, or null. */
export function windowProblem(w: ApprovalWindow): string | null {
  const start = Date.parse(`${w.start}:00Z`);
  const end = Date.parse(`${w.end}:00Z`);
  if (!w.start || !w.end || Number.isNaN(start) || Number.isNaN(end)) return 'Give both times.';
  if (end <= start) return 'The end must be after the start.';
  if (end - start > 24 * 3600 * 1000) return 'At most 24 hours.';
  return null;
}
