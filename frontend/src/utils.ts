/** Small shared UI helpers. */

/** Human date (locale) for an ISO timestamp, e.g. expiry lines. */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

/** Open a URL in a new tab without giving it a handle back to this window. */
export function openInNewTab(url: string): void {
  window.open(url, '_blank', 'noopener,noreferrer');
}
