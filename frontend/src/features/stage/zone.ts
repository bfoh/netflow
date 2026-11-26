import type { TemplateRole } from '../../types/api';
import type { RoleKey } from './roles';

/** Team templates per wizard role (D-111): which file of which device each one gives. The
 * modem's and BBU's files also depend on the system (D-114); the BBU is not a wizard device
 * yet, so its SCF comes only in the download. */
export const TEMPLATE_ROLES: {
  role: TemplateRole; label: string; wizardRole?: RoleKey; slot: 'baseId' | 'siteId' | 'fileId';
  /** Its file depends on the system (B007). */ system?: boolean;
  /** Its file sets a password from the device's login: handed out only from a system. */ secret?: boolean;
}[] = [
  { role: 'fortigate_base', label: 'FortiGate base file (same for every zone)', wizardRole: 'firewall', slot: 'baseId' },
  { role: 'fortigate_site', label: 'FortiGate site script', wizardRole: 'firewall', slot: 'siteId' },
  { role: 'bhdmz', label: 'BH-DMZ switch (2930F, OOBM port 2)', wizardRole: 'aruba_a', slot: 'fileId' },
  { role: 'lte', label: 'LTE switch (2930F, OOBM port 3)', wizardRole: 'aruba_b', slot: 'fileId' },
  { role: 'tetra', label: 'Tetra switch (Black Box)', wizardRole: 'blackbox', slot: 'fileId' },
  { role: 'modem', label: 'LTE modem (Nokia 7705 SAR-Hmc)', wizardRole: 'modem', slot: 'fileId', system: true, secret: true },
  { role: 'bbu_scf', label: 'Flexi BBU site configuration file (SCF)', slot: 'fileId', system: true },
];

const sys3 = (n: number) => `B${String(n).padStart(3, '0')}`;
const one = (found: number[], lo: number, hi: number) => {
  const set = [...new Set(found)].filter((n) => n >= lo && n <= hi);
  return set.length === 1 ? set[0] : undefined;
};

/** The system in a name, if exactly one: "B007" from "B007z045", "…ABCB-007-Z041…" or
 * "MRBTS-7"; a shorter "B7" only when the name has no such form. "eNB1" (an eNodeB) is not a
 * system. Either case. */
export function systemInName(name: string): string | undefined {
  const strong = [...name.matchAll(/(?<!\d)B-?(\d{3})(?![0-9A-Fa-f])|MRBTS-(\d{1,3})(?!\d)/gi)]
    .map((m) => Number(m[1] ?? m[2]));
  const found = strong.length ? strong
    : [...name.matchAll(/(?<!\d)(?<!en)B-?(\d{1,2})(?![0-9A-Fa-f])/gi)].map((m) => Number(m[1]));
  const n = one(found, 1, 999);
  return n === undefined ? undefined : sys3(n);
}

/** The system in a file's text, as UNDM's server reads it: B + 3 digits or MRBTS-<n>, as
 * written (configgen/zone.py system_from_text). */
export function systemInText(text: string): string | undefined {
  const n = one([...text.matchAll(/(?<!\d)B-?(\d{3})(?![0-9A-Fa-f])|MRBTS-(\d{1,3})(?!\d)/g)]
    .map((m) => Number(m[1] ?? m[2])), 1, 999);
  return n === undefined ? undefined : sys3(n);
}

/** "b7", "B07" or "B007" as UNDM stores it ("B007"); undefined if it is not a B system. */
export function normalSystem(text: string): string | undefined {
  const m = /^\s*[Bb]-?0*(\d{1,3})\s*$/.exec(text);
  return m && Number(m[1]) >= 1 ? `B${String(Number(m[1])).padStart(3, '0')}` : undefined;
}

/** The zone in a name, if exactly one, 1-128: "z045", "Z041", "Zone041", and also without
 * leading zeros as the team names the modem's file ("…z41.txt"). */
export function zoneInName(name: string): number | undefined {
  return one([...name.matchAll(/z(?:one)?(\d{1,3})(?!\d)/gi)].map((m) => Number(m[1])), 1, 128);
}

/** The zone in a file's text, as UNDM's server reads it: z / Zone + 3 digits
 * (configgen/zone.py zone_from_text). */
export function zoneInText(text: string): number | undefined {
  return one([...text.matchAll(/z(?:one)?(\d{3})(?!\d)/gi)].map((m) => Number(m[1])), 1, 128);
}

export type FileFacts = {
  zone?: number; zoneFrom?: 'name' | 'text'; system?: string; systemFrom?: 'name' | 'text';
  /** The name and the text name different zones or systems. */ disagree: string[];
};

/** The zone and system of a team file: from its name first, else from its text. */
export async function readFileFacts(file: File): Promise<FileFacts> {
  const text = file.size <= 20 * 1024 * 1024 ? await file.text() : '';
  const byName = { zone: zoneInName(file.name), system: systemInName(file.name) };
  const byText = { zone: zoneInText(text), system: systemInText(text) };
  const out: FileFacts = { disagree: [] };
  if (byName.zone !== undefined) Object.assign(out, { zone: byName.zone, zoneFrom: 'name' });
  else if (byText.zone !== undefined) Object.assign(out, { zone: byText.zone, zoneFrom: 'text' });
  if (byName.system) Object.assign(out, { system: byName.system, systemFrom: 'name' });
  else if (byText.system) Object.assign(out, { system: byText.system, systemFrom: 'text' });
  if (byName.zone !== undefined && byText.zone !== undefined && byName.zone !== byText.zone)
    out.disagree.push(`its name says zone ${byName.zone}, its text zone ${byText.zone}`);
  if (byName.system && byText.system && byName.system !== byText.system)
    out.disagree.push(`its name says ${byName.system}, its text ${byText.system}`);
  return out;
}

/** A template's file formatting in words ("Windows line endings · no final line break"). */
export function formatWords(t: { line_ending: 'lf' | 'crlf'; final_newline: boolean }): string {
  return `${t.line_ending === 'crlf' ? 'Windows line endings (CRLF)' : 'Unix line endings (LF)'} · ${t.final_newline ? 'ends with a line break' : 'no final line break'}`;
}

/** What a zone gives, in words (the team's numbering convention). */
export function zoneWords(zone: number): string {
  const tag = `z${String(zone).padStart(3, '0')}`;
  return `${tag} · 10.${127 + zone}.x · 10.${zone}.x · 10.0.${zone}.x · 130.${zone}.x`;
}
