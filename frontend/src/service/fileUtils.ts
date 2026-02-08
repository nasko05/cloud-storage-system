/**
 * File extension and type helpers (business rules for filenames).
 */

export const IMAGE_EXTENSIONS = new Set([
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif'
]);

export function getExtension(filename: string): string | undefined {
  return filename.split('.').pop()?.toLowerCase();
}

export function isImageFilename(filename: string): boolean {
  const ext = getExtension(filename);
  return ext != null && IMAGE_EXTENSIONS.has(ext);
}
