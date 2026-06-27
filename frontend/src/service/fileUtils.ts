/**
 * File extension and type helpers (business rules for filenames).
 */

export const IMAGE_EXTENSIONS = new Set([
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif'
]);

// Only browser-playable containers belong here — others fall back to download
// rather than rendering an empty <video>.
export const VIDEO_EXTENSIONS = new Set([
  'mp4', 'webm', 'ogg', 'ogv', 'mov', 'm4v'
]);

export function getExtension(filename: string): string | undefined {
  return filename.split('.').pop()?.toLowerCase();
}

export function isImageFilename(filename: string): boolean {
  const ext = getExtension(filename);
  return ext != null && IMAGE_EXTENSIONS.has(ext);
}

export function isVideoFilename(filename: string): boolean {
  const ext = getExtension(filename);
  return ext != null && VIDEO_EXTENSIONS.has(ext);
}

/** Which in-app preview renderer handles this filename, or null to fall back to
 *  download. Mirrors the space-io editor's supported set. */
export type PreviewKind = 'image' | 'video' | 'pdf' | 'docx';

export function previewKind(filename: string): PreviewKind | null {
  const ext = getExtension(filename);
  if (ext == null) return null;
  if (IMAGE_EXTENSIONS.has(ext)) return 'image';
  if (VIDEO_EXTENSIONS.has(ext)) return 'video';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'docx') return 'docx';
  return null;
}
