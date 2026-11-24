const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
const HOSTNAME = /^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$/;

/** An IPv4 address, an IPv6 address or a host name; empty is allowed (simulated devices). */
export function addressProblem(value: string): string | null {
  const v = value.trim();
  if (!v || IPV4.test(v) || (HOSTNAME.test(v) && !/^[\d.]+$/.test(v)) || ((v.match(/:/g)?.length ?? 0) >= 2 && /^[0-9A-Fa-f:.]+$/.test(v))) return null;
  return 'Not an address: use e.g. 192.0.2.1 or a host name (no port, no prefix length)';
}
