import type { Device, DeviceServices } from '../../types/api';

/** Plain text to send to the team or UNDM's developers: what was read, no login secret. */
export function asText(device: Device, data: DeviceServices): string {
  const lines = [`Management services of ${device.name} (${device.model || device.manufacturer})`];
  const s = data.services;
  if (s) {
    lines.push(`Read ${s.at} at ${s.address}${s.simulated ? ' (SIMULATED)' : ''}`);
    for (const p of s.ports) {
      const what = [p.banner, p.certificate && `certificate ${p.certificate.subject}; issuer ${p.certificate.issuer}; until ${p.certificate.not_after}${p.certificate.tls ? `; ${p.certificate.tls}` : ''}`, p.note]
        .filter(Boolean).join(' | ');
      lines.push(`  ${p.port} ${p.name}: ${p.open ? 'answers' : 'no answer'}${what ? ` | ${what}` : ''}`);
    }
  }
  const h = data.netconf_hello;
  if (h) {
    lines.push(`NETCONF <hello> read ${h.at} with login "${h.login}": ${h.ok ? h.message : `failed: ${h.message}`}`);
    if (h.ok) {
      lines.push(`  base ${(h.base_versions ?? []).join(', ')}; session ${h.session_id ?? '-'}; host key ${h.host_key ?? '-'}`);
      for (const c of h.capabilities ?? []) lines.push(`  ${c}`);
      if (h.note) lines.push(`  ${h.note}`);
    }
  }
  return lines.join('\n');
}
