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

/** The system in a name such as "B007z045" (B + 1-3 digits), if exactly one: "B007". */
export function systemInName(name: string): string | undefined {
  const found = [...new Set([...name.matchAll(/(?<!\d)B-?(\d{1,3})(?![0-9A-Fa-f])/gi)].map((m) => Number(m[1])))]
    .filter((n) => n >= 1 && n <= 999);
  return found.length === 1 ? `B${String(found[0]).padStart(3, '0')}` : undefined;
}

/** "b7", "B07" or "B007" as UNDM stores it ("B007"); undefined if it is not a B system. */
export function normalSystem(text: string): string | undefined {
  const m = /^\s*[Bb]-?0*(\d{1,3})\s*$/.exec(text);
  return m && Number(m[1]) >= 1 ? `B${String(Number(m[1])).padStart(3, '0')}` : undefined;
}

/** The zone in a name such as "B001z045" (z + 3 digits), if exactly one; 1-128 only. */
export function zoneInName(name: string): number | undefined {
  const found = [...new Set([...name.matchAll(/z(\d{3})(?!\d)/gi)].map((m) => Number(m[1])))]
    .filter((z) => z >= 1 && z <= 128);
  return found.length === 1 ? found[0] : undefined;
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
