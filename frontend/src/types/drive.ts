/**
 * Centralized type definitions for the drive application.
 * All shared interfaces live here; components import from this file
 * instead of cross-importing from each other.
 */
import type { DriveFile } from '../components/File';

// Re-export DriveFile class type for convenience
export type { DriveFile };

// Re-export DriveFolder from its canonical definition in Folder.tsx
import type { DriveFolder } from '../components/Folder';
export type { DriveFolder };

// ---------------------------------------------------------------------------
// File shape (raw data from API)
// ---------------------------------------------------------------------------

export interface FileShape {
  fileId: string;
  filename: string;
  size: number;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Grid / List row types
// ---------------------------------------------------------------------------

export interface FileGridRow {
  id: string;
  file: DriveFile;
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
