/**
 * Drive business logic: file listing, download URLs, delete, and batch upload.
 * Uses api.ts for HTTP; no UI or React state.
 */
import { deleteFile, getDownloadUrl, listFiles, uploadFile } from '../api';
import { DriveFile } from '../components/File';

export interface FetchFilesResult {
  files: InstanceType<typeof DriveFile>[];
  error?: string;
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

export async function fetchFiles(): Promise<FetchFilesResult> {
  try {
    const data = await listFiles();
    const files = FileCollection.fromUnknown(data.files);
    return { files };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load files';
    return { files: [], error: message };
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
