export function fmtDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—';
}

/** Save text as a file in the browser's download folder. */
export function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename.replace(/[^\w.-]/g, '_') });
  a.click();
  URL.revokeObjectURL(url);
}
