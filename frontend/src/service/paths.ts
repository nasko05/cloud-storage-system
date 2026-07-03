/**
 * Drive-path helpers shared by the API layer and the upload manager, so the
 * two sides can't disagree on what a normalized path looks like.
 */

/** Normalize a drive path: leading slash, collapsed slashes, no trailing slash. */
export function normalizePath(path?: string): string {
  if (!path || path === '/') return '/';
  const trimmed = path.trim();
  if (!trimmed) return '/';
  const withLeadingSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  const normalized = withLeadingSlash.replace(/\/+/g, '/').replace(/\/$/, '');
  return normalized || '/';
}

/** Join a child segment onto an already-normalized parent path. */
export function joinPath(parentPath: string, childName: string): string {
  return parentPath === '/' ? `/${childName}` : `${parentPath}/${childName}`;
}
