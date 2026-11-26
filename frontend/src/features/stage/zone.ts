import type { TemplateRole } from '../../types/api';
import type { RoleKey } from './roles';

/** Team templates per wizard role (D-111): which file of which device each one gives. */
export const TEMPLATE_ROLES: { role: TemplateRole; label: string; wizardRole: RoleKey; slot: 'baseId' | 'siteId' | 'fileId' }[] = [
  { role: 'fortigate_base', label: 'FortiGate base file (same for every zone)', wizardRole: 'firewall', slot: 'baseId' },
  { role: 'fortigate_site', label: 'FortiGate site script', wizardRole: 'firewall', slot: 'siteId' },
  { role: 'bhdmz', label: 'BH-DMZ switch (2930F, OOBM port 2)', wizardRole: 'aruba_a', slot: 'fileId' },
  { role: 'lte', label: 'LTE switch (2930F, OOBM port 3)', wizardRole: 'aruba_b', slot: 'fileId' },
  { role: 'tetra', label: 'Tetra switch (Black Box)', wizardRole: 'blackbox', slot: 'fileId' },
];

/** The zone in a name such as "B001z045" (z + 3 digits), if exactly one; 1-128 only. */
export function zoneInName(name: string): number | undefined {
  const found = [...new Set([...name.matchAll(/z(\d{3})(?!\d)/gi)].map((m) => Number(m[1])))]
    .filter((z) => z >= 1 && z <= 128);
  return found.length === 1 ? found[0] : undefined;
}

/** What a zone gives, in words (the team's numbering convention). */
export function zoneWords(zone: number): string {
  const tag = `z${String(zone).padStart(3, '0')}`;
  return `${tag} · 10.${127 + zone}.x · 10.${zone}.x · 10.0.${zone}.x · 130.${zone}.x`;
}
