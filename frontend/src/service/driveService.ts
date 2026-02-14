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

export interface FetchFilesResult {
  files: InstanceType<typeof DriveFile>[];
  folders: DriveFolder[];
  error?: string;
}

function parseFolder(item: unknown): DriveFolder | null {
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

export interface DeleteFileResult {
  success: boolean;
  error?: string;
}

export interface UploadBatchResult {
  successCount: number;
  failureCount: number;
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

export async function deleteFileResult(fileId: string): Promise<DeleteFileResult> {
  try {
    const result = await deleteFile(fileId);
    if (result.error) {
      return { success: false, error: result.error };
    }
    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Delete failed';
    return { success: false, error: message };
  }
}

export interface MoveResult {
  success: boolean;
  error?: string;
}

export async function moveFileResult(fileId: string, destinationPath: string): Promise<MoveResult> {
  try {
    const result = await apiMoveFile(fileId, destinationPath);
    if (result.error) return { success: false, error: result.error };
    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Move failed';
    return { success: false, error: message };
  }
}

export async function moveFolderResult(folderPath: string, destinationPath: string): Promise<MoveResult> {
  try {
    const result = await apiMoveFolder(folderPath, destinationPath);
    if (result.error) return { success: false, error: result.error };
    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Move failed';
    return { success: false, error: message };
  }
}

export async function renameFileResult(fileId: string, newName: string): Promise<MoveResult> {
  try {
    const result = await apiRenameFile(fileId, newName);
    if (result.error) return { success: false, error: result.error };
    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Rename failed';
    return { success: false, error: message };
  }
}

export async function renameFolderResult(folderPath: string, newName: string): Promise<MoveResult> {
  try {
    const result = await apiRenameFolder(folderPath, newName);
    if (result.error) return { success: false, error: result.error };
    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Rename failed';
    return { success: false, error: message };
  }
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
