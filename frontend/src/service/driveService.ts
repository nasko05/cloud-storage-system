/**
 * Drive business logic: file listing, download URLs, delete, and batch upload.
 * Uses api.ts for HTTP; no UI or React state.
 */
import {
  deleteFile,
  getDownloadUrl,
  createDownloadZip,
  listFiles,
  listSharedWithMe,
  listFileShares as apiListFileShares,
  unshareFile as apiUnshareFile,
  updateSharePermission as apiUpdateSharePermission,
  moveFile as apiMoveFile,
  moveFolder as apiMoveFolder,
  renameFile as apiRenameFile,
  renameFolder as apiRenameFolder,
  shareFile as apiShareFile,
  uploadFile,
  createPublicLink as apiCreatePublicLink,
  listPublicLinks as apiListPublicLinks,
  deletePublicLink as apiDeletePublicLink,
  updatePublicLink as apiUpdatePublicLink,
  getPublicLinkInfo as apiGetPublicLinkInfo,
  downloadPublicLink as apiDownloadPublicLink,
} from '../api';
import type { DriveFile, DriveFolder, SharedFile, FileShare, SharePermission, PublicLink, PublicLinkInfo } from '../types/drive';
import { driveFileFromUnknown } from '../types/drive';

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
// File collection parser
// ---------------------------------------------------------------------------

function filesFromUnknown(payload: unknown): DriveFile[] {
  if (!Array.isArray(payload)) return [];
  return payload
    .map((item) => driveFileFromUnknown(item))
    .filter((item): item is DriveFile => item !== null);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface FetchFilesResult {
  files: DriveFile[];
  folders: DriveFolder[];
  error?: string;
}

export async function fetchFiles(folder?: string): Promise<FetchFilesResult> {
  try {
    const data = await listFiles(folder);
    const files = filesFromUnknown(data.files);
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

export interface BulkDownloadZipResult {
  downloadUrl?: string;
  error?: string;
}

export async function getBulkDownloadZipUrl(
  fileIds: string[],
  folderPaths: string[]
): Promise<BulkDownloadZipResult> {
  try {
    const result = await createDownloadZip(fileIds, folderPaths);
    if (result.error) return { error: result.error };
    if (!result.downloadUrl) return { error: 'No download URL returned' };
    return { downloadUrl: result.downloadUrl };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to create ZIP';
    return { error: message };
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

export interface FetchSharedFilesResult {
  files: SharedFile[];
  error?: string;
}

export async function fetchSharedWithMe(): Promise<FetchSharedFilesResult> {
  try {
    const data = await listSharedWithMe();
    const files: SharedFile[] = (data.files ?? []).map((f) => ({
      fileId: f.fileId,
      filename: f.filename,
      sharedBy: f.sharedBy,
      sharedByEmail: f.sharedByEmail,
      permission: f.permission as SharePermission,
      expiresAt: f.expiresAt
    }));
    return { files };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load shared files';
    return { files: [], error: message };
  }
}

export interface ShareResult {
  success: boolean;
  expiresAt?: string;
  error?: string;
}

export async function shareFileResult(
  fileId: string,
  shareWithEmail: string,
  permission: string,
  expiryDays?: number
): Promise<ShareResult> {
  try {
    const result = await apiShareFile(fileId, shareWithEmail, permission, expiryDays);
    if (result.error) return { success: false, error: result.error };
    return { success: true, expiresAt: result.expiresAt };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Share failed';
    return { success: false, error: message };
  }
}

// ---------------------------------------------------------------------------
// Share management (list / revoke / update permission)
// ---------------------------------------------------------------------------

export interface FetchFileSharesResult {
  shares: FileShare[];
  error?: string;
}

export async function fetchFileShares(fileId: string): Promise<FetchFileSharesResult> {
  try {
    const data = await apiListFileShares(fileId);
    const shares: FileShare[] = (data.shares ?? []).map((s) => ({
      sharedWith: s.sharedWith,
      permission: s.permission as SharePermission,
      sharedAt: s.sharedAt,
      expiresAt: s.expiresAt
    }));
    return { shares };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load shares';
    return { shares: [], error: message };
  }
}

export interface RevokeShareResult {
  success: boolean;
  error?: string;
}

export async function revokeShare(fileId: string, userId: string): Promise<RevokeShareResult> {
  return wrapApiCall(() => apiUnshareFile(fileId, userId), 'Revoke failed');
}

export interface UpdateSharePermissionResult {
  success: boolean;
  error?: string;
}

export async function updateSharePermissionResult(
  fileId: string,
  targetUserId: string,
  permission: string
): Promise<UpdateSharePermissionResult> {
  return wrapApiCall(
    () => apiUpdateSharePermission(fileId, targetUserId, permission),
    'Update permission failed'
  );
}

// ---------------------------------------------------------------------------
// Public link management (authenticated CRUD)
// ---------------------------------------------------------------------------

export interface CreatePublicLinkResult {
  success: boolean;
  link?: PublicLink;
  error?: string;
}

export async function createPublicLinkResult(
  fileId: string,
  password?: string,
  expiryDays?: number
): Promise<CreatePublicLinkResult> {
  try {
    const data = await apiCreatePublicLink(fileId, password, expiryDays);
    if (data.error) return { success: false, error: data.error };
    const link: PublicLink = {
      token: data.token ?? '',
      fileId: data.fileId ?? fileId,
      filename: data.filename ?? '',
      hasPassword: data.hasPassword ?? false,
      downloadCount: data.downloadCount ?? 0,
      createdAt: data.createdAt ?? '',
      expiresAt: data.expiresAt ?? '',
    };
    return { success: true, link };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to create public link';
    return { success: false, error: message };
  }
}

export interface FetchPublicLinksResult {
  links: PublicLink[];
  error?: string;
}

export async function fetchPublicLinks(fileId: string): Promise<FetchPublicLinksResult> {
  try {
    const data = await apiListPublicLinks(fileId);
    const links: PublicLink[] = (data.links ?? []).map((l) => ({
      token: l.token,
      fileId: l.fileId,
      filename: l.filename,
      hasPassword: l.hasPassword,
      downloadCount: l.downloadCount,
      createdAt: l.createdAt,
      expiresAt: l.expiresAt,
    }));
    return { links };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load public links';
    return { links: [], error: message };
  }
}

export interface DeletePublicLinkResult {
  success: boolean;
  error?: string;
}

export async function deletePublicLinkResult(token: string): Promise<DeletePublicLinkResult> {
  return wrapApiCall(() => apiDeletePublicLink(token), 'Failed to delete public link');
}

export interface UpdatePublicLinkResult {
  success: boolean;
  error?: string;
}

export async function updatePublicLinkResult(
  token: string,
  options: { password?: string; removePassword?: boolean; expiryDays?: number }
): Promise<UpdatePublicLinkResult> {
  return wrapApiCall(() => apiUpdatePublicLink(token, options), 'Failed to update public link');
}

// ---------------------------------------------------------------------------
// Public download (unauthenticated – used by PublicDownloadPage)
// ---------------------------------------------------------------------------

export interface FetchPublicLinkInfoResult {
  info?: PublicLinkInfo;
  error?: string;
}

export async function fetchPublicLinkInfo(token: string): Promise<FetchPublicLinkInfoResult> {
  try {
    const data = await apiGetPublicLinkInfo(token);
    if (data.error) return { error: data.error };
    const info: PublicLinkInfo = {
      filename: data.filename ?? '',
      size: data.size ?? 0,
      contentType: data.contentType ?? 'application/octet-stream',
      hasPassword: data.hasPassword ?? false,
      downloadCount: data.downloadCount ?? 0,
      expiresAt: data.expiresAt ?? '',
    };
    return { info };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Link not found or expired';
    return { error: message };
  }
}

export interface PublicDownloadUrlResult {
  downloadUrl?: string;
  error?: string;
}

export async function getPublicDownloadUrl(
  token: string,
  password?: string
): Promise<PublicDownloadUrlResult> {
  try {
    const data = await apiDownloadPublicLink(token, password);
    if (data.error) return { error: data.error };
    return { downloadUrl: data.downloadUrl };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Download failed';
    return { error: message };
  }
}

// ---------------------------------------------------------------------------
// Batch upload
// ---------------------------------------------------------------------------

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
