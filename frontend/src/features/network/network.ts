import type { Device, Project } from '../../types/api';

/** The start-up setting that lets UNDM log in to production devices to read (D-125). */
export const READ_SWITCH_LINE = 'UNDM_ALLOW_PRODUCTION_READ_ONLY=true';

/** The BFW: the one chosen for the system, else its only firewall. */
export function gatewayOf(project: Project, devices: Device[]): Device | undefined {
  const firewalls = devices.filter((d) => d.category === 'firewall');
  return devices.find((d) => d.id === project.network_gateway_id) ?? (firewalls.length === 1 ? firewalls[0] : undefined);
}
