export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  // The API sends UTC times; an older backend sent them without a zone. Never read one as local time.
  const zoned = /([zZ]|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  const when = new Date(zoned);
  if (Number.isNaN(when.getTime())) return value;
  // Shown in UTC, like the network devices and their logs (product owner: network time is UTC+0).
  return `${when.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

/** Save text as a file in the browser's download folder. */
export function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename.replace(/[^\w.-]/g, '_') });
  a.click();
  URL.revokeObjectURL(url);
}

export { planKind } from './labels';
