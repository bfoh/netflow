/** What the person ticks by hand, kept per system in this browser (like the wizard's choices). */
export type Ticks = { license?: boolean; report?: boolean; backups?: boolean; powered?: boolean };

const key = (pid: string) => `undm.finish.${pid}`;
export function loadTicks(pid: string): Ticks {
  try { return JSON.parse(window.localStorage.getItem(key(pid)) ?? '{}') as Ticks; } catch { return {}; }
}
export function saveTicks(pid: string, t: Ticks) {
  try { window.localStorage.setItem(key(pid), JSON.stringify(t)); } catch { /* private window: kept for this visit */ }
}
