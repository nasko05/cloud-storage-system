const cache = new Map<string, { url: string; expiresAt: number }>();
const TTL_MS = 50 * 60 * 1000; // 50 minutes (presigned URLs last 60min)

export async function getCachedDownloadUrl(
  fileId: string,
  fetcher: (id: string) => Promise<string | null>
): Promise<string | null> {
  const entry = cache.get(fileId);
  if (entry && Date.now() < entry.expiresAt) {
    return entry.url;
  }
  const url = await fetcher(fileId);
  if (url) {
    cache.set(fileId, { url, expiresAt: Date.now() + TTL_MS });
  }
  return url;
}

export function invalidateThumbnail(fileId: string): void {
  cache.delete(fileId);
}
