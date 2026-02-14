/**
 * Centralized type definitions for the drive application.
 * This is the CANONICAL source for all shared types -- no imports from
 * component files, breaking the circular dependency.
 */

// ---------------------------------------------------------------------------
// Folder
// ---------------------------------------------------------------------------

export interface DriveFolder {
  folderId: string;
  name: string;
  path: string;
  /** ISO date string when the folder was created. */
  createdAt?: string;
}

// ---------------------------------------------------------------------------
// File
// ---------------------------------------------------------------------------

export interface FileShape {
  fileId: string;
  filename: string;
  size: number;
  createdAt: string;
}

/** DriveFile is a plain data object (no class -- avoids circular deps). */
export interface DriveFile {
  readonly fileId: string;
  readonly filename: string;
  readonly size: number;
  readonly createdAt: string;
  readonly isShared?: boolean;
}

/** Parse an unknown API value into a DriveFile, or null if invalid. */
export function driveFileFromUnknown(value: unknown): DriveFile | null {
  if (!value || typeof value !== 'object') return null;
  const c = value as Partial<FileShape>;
  if (
    typeof c.fileId !== 'string' ||
    typeof c.filename !== 'string' ||
    typeof c.size !== 'number' ||
    typeof c.createdAt !== 'string'
  )
    return null;
  const isShared = (value as Record<string, unknown>).isShared === true;
  return { fileId: c.fileId, filename: c.filename, size: c.size, createdAt: c.createdAt, isShared };
}

/** Format a byte size into a human-readable string. */
export function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Grid / List row types
// ---------------------------------------------------------------------------

export interface FileGridRow {
  id: string;
  file: DriveFile;
}

/** Convert a DriveFile to a grid row. */
export function toFileGridRow(file: DriveFile): FileGridRow {
  return { id: file.fileId, file };
}

/** Unified row for list view: folders and files in one grid. */
export type DriveListRow =
  | { id: string; type: 'file'; file: DriveFile }
  | { id: string; type: 'folder'; folder: DriveFolder };

// ---------------------------------------------------------------------------
// UI interaction targets
// ---------------------------------------------------------------------------

export type ContextMenuTarget =
  | { type: 'file'; file: DriveFile }
  | { type: 'folder'; folder: DriveFolder }
  | null;

export interface ContextMenuPosition {
  mouseX: number;
  mouseY: number;
}

export type RenameTarget =
  | { type: 'file'; file: DriveFile }
  | { type: 'folder'; folder: DriveFolder }
  | null;

export interface MoveItem {
  type: 'file' | 'folder';
  id: string;
  /** For folders, the full path; for files, the fileId. */
  path?: string;
  name: string;
}

// ---------------------------------------------------------------------------
// Sharing
// ---------------------------------------------------------------------------

export type SharePermission = 'read' | 'download' | 'edit';

export type ShareTarget =
  | { type: 'file'; file: DriveFile }
  | null;

/** A file that has been shared with the current user. */
export interface SharedFile {
  fileId: string;
  filename: string;
  sharedBy: string;
  sharedByEmail: string;
  permission: SharePermission;
  expiresAt: string;
}

/** A single share record for a file owned by the current user. */
export interface FileShare {
  sharedWith: string;
  permission: SharePermission;
  sharedAt: string;
  expiresAt: string;
}
