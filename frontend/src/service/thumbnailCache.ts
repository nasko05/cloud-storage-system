const MAX_CACHE_SIZE = 200;
const TTL_MS = 50 * 60 * 1000; // 50 minutes (presigned URLs last 60min)

const cache = new Map<string, { url: string; expiresAt: number }>();

/**
 * Evict the oldest entries when the cache exceeds MAX_CACHE_SIZE.
 * Map iteration order is insertion order, so the first entries are the oldest.
 */
function evictIfNeeded(): void {
  if (cache.size <= MAX_CACHE_SIZE) return;
  const excess = cache.size - MAX_CACHE_SIZE;
  const iter = cache.keys();
  for (let i = 0; i < excess; i++) {
    const key = iter.next().value;
    if (key !== undefined) {
      cache.delete(key);
    }
  }
}

export async function getCachedDownloadUrl(
  fileId: string,
  fetcher: (id: string) => Promise<string | null>
): Promise<string | null> {
  const entry = cache.get(fileId);
  if (entry && Date.now() < entry.expiresAt) {
    // Move to end (most-recently-used) by re-inserting
    cache.delete(fileId);
    cache.set(fileId, entry);
    return entry.url;
  }
  // Remove stale entry if expired
  if (entry) {
    cache.delete(fileId);
  }
  const url = await fetcher(fileId);
  if (url) {
    cache.set(fileId, { url, expiresAt: Date.now() + TTL_MS });
    evictIfNeeded();
  }
  return url;
}

export function invalidateThumbnail(fileId: string): void {
  cache.delete(fileId);
}
