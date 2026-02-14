/**
 * Drive business logic: file listing, download URLs, delete, and batch upload.
 * Uses api.ts for HTTP; no UI or React state.
 */
import {
  deleteFile,
  getDownloadUrl,
  listFiles,
  moveFile as apiMoveFile,
  moveFolder as apiMoveFolder,
  renameFile as apiRenameFile,
  renameFolder as apiRenameFolder,
  uploadFile
} from '../api';
import { DriveFile } from '../components/File';
import type { DriveFolder } from '../components/Folder';

// ---------------------------------------------------------------------------
// Shared folder parser (used by MoveDialog as well)
// ---------------------------------------------------------------------------

export function parseFolder(item: unknown): DriveFolder | null {
  if (!item || typeof item !== 'object') return null;
  const o = item as Record<string, unknown>;
  if (
    typeof o.folderId !== 'string' ||
    typeof o.name !== 'string' ||
    typeof o.path !== 'string'
  )
    return null;
  const createdAt = typeof o.createdAt === 'string' ? o.createdAt : undefined;
  return { folderId: o.folderId, name: o.name, path: o.path, createdAt };
}

// ---------------------------------------------------------------------------
// Generic API-call wrapper (error extraction + try/catch)
// ---------------------------------------------------------------------------

interface ApiCallResult {
  success: boolean;
  error?: string;
}

async function wrapApiCall<T extends { error?: string }>(
  fn: () => Promise<T>,
  fallbackMsg: string
): Promise<ApiCallResult> {
  try {
    const result = await fn();
    if (result.error) return { success: false, error: result.error };
    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : fallbackMsg;
    return { success: false, error: message };
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface FetchFilesResult {
  files: InstanceType<typeof DriveFile>[];
  folders: DriveFolder[];
  error?: string;
}

export class FileCollection {
  public static fromUnknown(payload: unknown): InstanceType<typeof DriveFile>[] {
    if (!Array.isArray(payload)) {
      return [];
    }
    return payload
      .map((item) => DriveFile.fromUnknown(item))
      .filter((item): item is InstanceType<typeof DriveFile> => item !== null);
  }
}

export async function fetchFiles(folder?: string): Promise<FetchFilesResult> {
  try {
    const data = await listFiles(folder);
    const files = FileCollection.fromUnknown(data.files);
    const folders = Array.isArray(data.folders)
      ? data.folders.map(parseFolder).filter((f): f is DriveFolder => f !== null)
      : [];
    return { files, folders };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load files';
    return { files: [], folders: [], error: message };
  }
}

export async function getFileDownloadUrl(fileId: string): Promise<string | null> {
  try {
    const { downloadUrl, error } = await getDownloadUrl(fileId);
    if (error || !downloadUrl) return null;
    return downloadUrl;
  } catch {
    return null;
  }
}

export interface DeleteFileResult {
  success: boolean;
  error?: string;
}

export async function deleteFileResult(fileId: string): Promise<DeleteFileResult> {
  return wrapApiCall(() => deleteFile(fileId), 'Delete failed');
}

export interface MoveResult {
  success: boolean;
  error?: string;
}

export async function moveFileResult(fileId: string, destinationPath: string): Promise<MoveResult> {
  return wrapApiCall(() => apiMoveFile(fileId, destinationPath), 'Move failed');
}

export async function moveFolderResult(folderPath: string, destinationPath: string): Promise<MoveResult> {
  return wrapApiCall(() => apiMoveFolder(folderPath, destinationPath), 'Move failed');
}

export async function renameFileResult(fileId: string, newName: string): Promise<MoveResult> {
  return wrapApiCall(() => apiRenameFile(fileId, newName), 'Rename failed');
}

export async function renameFolderResult(folderPath: string, newName: string): Promise<MoveResult> {
  return wrapApiCall(() => apiRenameFolder(folderPath, newName), 'Rename failed');
}

export interface UploadBatchResult {
  successCount: number;
  failureCount: number;
}

export async function uploadBatch(files: File[]): Promise<UploadBatchResult> {
  let successCount = 0;
  let failureCount = 0;
  for (const file of files) {
    try {
      await uploadFile(file);
      successCount += 1;
    } catch {
      failureCount += 1;
    }
  }
  return { successCount, failureCount };
}
