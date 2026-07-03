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
  return wrapApiFetch(
    fn,
    (): ApiCallResult => ({ success: true }),
    (error) => ({ success: false, error }),
    fallbackMsg
  );
}

/**
 * Shared try/catch + error-field extraction for calls whose result carries
 * data: `map` shapes the success value, `onError` the failure value.
 */
async function wrapApiFetch<T extends { error?: string }, R>(
  fn: () => Promise<T>,
  map: (data: T) => R,
  onError: (message: string) => R,
  fallbackMsg: string
): Promise<R> {
  try {
    const data = await fn();
    if (data.error) return onError(data.error);
    return map(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : fallbackMsg;
    return onError(message);
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
  return wrapApiFetch(
    () => listFiles(folder),
    (data) => ({
      files: filesFromUnknown(data.files),
      folders: Array.isArray(data.folders)
        ? data.folders.map(parseFolder).filter((f): f is DriveFolder => f !== null)
        : [],
    }),
    (error) => ({ files: [], folders: [], error }),
    'Failed to load files'
  );
}

export async function getFileDownloadUrl(fileId: string): Promise<string | null> {
  return wrapApiFetch(
    () => getDownloadUrl(fileId),
    (data) => data.downloadUrl ?? null,
    () => null,
    'Download failed'
  );
}

export interface BulkDownloadZipResult {
  downloadUrl?: string;
  error?: string;
}

export async function getBulkDownloadZipUrl(
  fileIds: string[],
  folderPaths: string[]
): Promise<BulkDownloadZipResult> {
  return wrapApiFetch(
    () => createDownloadZip(fileIds, folderPaths),
    (data) => (data.downloadUrl ? { downloadUrl: data.downloadUrl } : { error: 'No download URL returned' }),
    (error) => ({ error }),
    'Failed to create ZIP'
  );
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
  return wrapApiFetch(
    () => listSharedWithMe(),
    (data) => ({
      files: (data.files ?? []).map((f) => ({
        fileId: f.fileId,
        filename: f.filename,
        sharedBy: f.sharedBy,
        sharedByEmail: f.sharedByEmail,
        permission: f.permission as SharePermission,
        expiresAt: f.expiresAt,
      })),
    }),
    (error) => ({ files: [], error }),
    'Failed to load shared files'
  );
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
  return wrapApiFetch(
    () => apiShareFile(fileId, shareWithEmail, permission, expiryDays),
    (data): ShareResult => ({ success: true, expiresAt: data.expiresAt }),
    (error) => ({ success: false, error }),
    'Share failed'
  );
}

// ---------------------------------------------------------------------------
// Share management (list / revoke / update permission)
// ---------------------------------------------------------------------------

export interface FetchFileSharesResult {
  shares: FileShare[];
  error?: string;
}

export async function fetchFileShares(fileId: string): Promise<FetchFileSharesResult> {
  return wrapApiFetch(
    () => apiListFileShares(fileId),
    (data) => ({
      shares: (data.shares ?? []).map((s) => ({
        sharedWith: s.sharedWith,
        permission: s.permission as SharePermission,
        sharedAt: s.sharedAt,
        expiresAt: s.expiresAt,
      })),
    }),
    (error) => ({ shares: [], error }),
    'Failed to load shares'
  );
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
  return wrapApiFetch(
    () => apiCreatePublicLink(fileId, password, expiryDays),
    (data): CreatePublicLinkResult => ({
      success: true,
      link: {
        token: data.token ?? '',
        fileId: data.fileId ?? fileId,
        filename: data.filename ?? '',
        hasPassword: data.hasPassword ?? false,
        downloadCount: data.downloadCount ?? 0,
        createdAt: data.createdAt ?? '',
        expiresAt: data.expiresAt ?? '',
      } satisfies PublicLink,
    }),
    (error) => ({ success: false, error }),
    'Failed to create public link'
  );
}

export interface FetchPublicLinksResult {
  links: PublicLink[];
  error?: string;
}

export async function fetchPublicLinks(fileId: string): Promise<FetchPublicLinksResult> {
  return wrapApiFetch(
    () => apiListPublicLinks(fileId),
    (data) => ({
      links: (data.links ?? []).map((l) => ({
        token: l.token,
        fileId: l.fileId,
        filename: l.filename,
        hasPassword: l.hasPassword,
        downloadCount: l.downloadCount,
        createdAt: l.createdAt,
        expiresAt: l.expiresAt,
      })),
    }),
    (error) => ({ links: [], error }),
    'Failed to load public links'
  );
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
  return wrapApiFetch(
    () => apiGetPublicLinkInfo(token),
    (data): FetchPublicLinkInfoResult => ({
      info: {
        filename: data.filename ?? '',
        size: data.size ?? 0,
        contentType: data.contentType ?? 'application/octet-stream',
        hasPassword: data.hasPassword ?? false,
        downloadCount: data.downloadCount ?? 0,
        expiresAt: data.expiresAt ?? '',
      } satisfies PublicLinkInfo,
    }),
    (error) => ({ error }),
    'Link not found or expired'
  );
}

export interface PublicDownloadUrlResult {
  downloadUrl?: string;
  error?: string;
}

export async function getPublicDownloadUrl(
  token: string,
  password?: string
): Promise<PublicDownloadUrlResult> {
  return wrapApiFetch(
    () => apiDownloadPublicLink(token, password),
    (data): PublicDownloadUrlResult => ({ downloadUrl: data.downloadUrl }),
    (error) => ({ error }),
    'Download failed'
  );
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
