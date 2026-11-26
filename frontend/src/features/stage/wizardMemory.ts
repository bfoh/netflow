/**
 * Where the person was in Stage a system, kept in this browser (D-120), so "Stage a system"
 * goes straight back to the unfinished system and step. The prefix is `undm.wizard.`, not
 * `undm.stage.`: every `undm.stage.*` key holds the wizard's file and login choices, which
 * other code reads and replaces as a whole.
 */
const LAST = 'undm.wizard.last';
const key = (projectId: string) => `undm.wizard.${projectId}`;

export type WizardMode = 'real' | 'simulated';
export interface WizardPlace { step: number; mode?: WizardMode }

function read(k: string): string | null {
  try { return window.localStorage.getItem(k); } catch { return null; }
}
function write(k: string, v: string | null) {
  try {
    if (v === null) window.localStorage.removeItem(k);
    else window.localStorage.setItem(k, v);
  } catch { /* private window or storage off: the wizard still works, it only forgets */ }
}

/** The system last worked on in Stage a system, if any. */
export function lastSystem(): string | null {
  return read(LAST);
}

export function placeOf(projectId: string): WizardPlace | null {
  const raw = read(key(projectId));
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<WizardPlace>;
    return typeof v.step === 'number' ? { step: v.step, mode: v.mode === 'simulated' ? 'simulated' : v.mode === 'real' ? 'real' : undefined } : null;
  } catch { return null; }
}

export function rememberPlace(projectId: string, place: WizardPlace) {
  if (!projectId) return;
  write(key(projectId), JSON.stringify(place));
  write(LAST, projectId);
}

/** A system that was deleted or finished is not resumed. */
export function forgetSystem(projectId: string) {
  write(key(projectId), null);
  if (lastSystem() === projectId) write(LAST, null);
}
