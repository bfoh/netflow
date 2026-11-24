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

/** Short label for a plan's type in lists. */
export function planKind(d: { kind: string; apply_mode: string; dry_run: boolean }): string {
  const base = d.kind === 'firmware' ? 'firmware' : d.kind === 'first_login' ? 'first login' : `config · ${d.apply_mode}`;
  return base + (d.dry_run ? ' · dry run' : '');
}
