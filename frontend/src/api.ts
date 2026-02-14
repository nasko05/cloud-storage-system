import { config } from './config';
import { getToken } from './auth';

interface ApiBody {
  [key: string]: unknown;
}

interface ApiResult {
  error?: string;
}

interface ListFilesResult extends ApiResult {
  files?: unknown[];
  folders?: unknown[];
}

interface UploadUrlResult extends ApiResult {
  uploadUrl?: string;
  fileId?: string;
}

interface DownloadUrlResult extends ApiResult {
  downloadUrl?: string;
}

interface CreateFolderResult extends ApiResult {
  folderId?: string;
  folderName?: string;
  path?: string;
}

interface ShareFileResult extends ApiResult {
  message?: string;
  fileId?: string;
  sharedWith?: string;
  expiresAt?: string;
}

interface SharedWithMeResult extends ApiResult {
  files?: Array<{
    fileId: string;
    sharedBy: string;
    sharedByEmail: string;
    filename: string;
    permission: string;
    expiresAt: string;
  }>;
}

interface ListFileSharesResult extends ApiResult {
  shares?: Array<{
    sharedWith: string;
    permission: string;
    sharedAt: string;
    expiresAt: string;
  }>;
}

interface UpdateShareResult extends ApiResult {
  message?: string;
  fileId?: string;
  targetUserId?: string;
  permission?: string;
}

interface UnshareResult extends ApiResult {
  message?: string;
  fileId?: string;
  revokedUser?: string;
}

class DriveApiClient {
  public static async call<T extends ApiResult>(endpoint: string, body: ApiBody): Promise<T> {
    const token = await getToken();
    const resp = await fetch(`${config.apiEndpoint}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token ?? ''}`
      },
      body: JSON.stringify(body)
    });

    if (resp.status === 401) {
      throw new Error('Session expired. Please log in again.');
    }

    if (!resp.ok) {
      // Try to extract an error message from the response body
      let errorMessage: string;
      try {
        const errorBody = (await resp.json()) as { error?: string };
        errorMessage = errorBody.error ?? `Request failed with status ${resp.status}`;
      } catch {
        errorMessage = `Request failed with status ${resp.status}`;
      }
      throw new Error(errorMessage);
    }

    return (await resp.json()) as T;
  }
}

export const listFiles = async (folder?: string): Promise<ListFilesResult> =>
  DriveApiClient.call<ListFilesResult>('/upload', { action: 'list', folder });

export const createFolder = async (
  folderName: string,
  path?: string
): Promise<CreateFolderResult> =>
  DriveApiClient.call<CreateFolderResult>('/upload', {
    action: 'create-folder',
    folderName,
    path
  });

export const deleteFolder = async (path: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'delete-folder', path });

const getUploadUrl = async (
  filename: string,
  contentType: string,
  size: number,
  path?: string
): Promise<UploadUrlResult> =>
  DriveApiClient.call<UploadUrlResult>('/upload', {
    filename,
    contentType,
    size,
    ...(path !== undefined && path !== '' ? { path } : {})
  });

export const uploadFile = async (
  file: File,
  folderPath?: string
): Promise<string> => {
  let contentType = file.type || 'application/octet-stream';

  if (file.name.toLowerCase().endsWith('.pdf')) {
    contentType = 'application/pdf';
  }

  const { uploadUrl, fileId, error } = await getUploadUrl(
    file.name,
    contentType,
    file.size,
    folderPath
  );
  if (error || !uploadUrl || !fileId) {
    throw new Error(error || 'Upload URL not available');
  }

  const uploadResponse = await fetch(uploadUrl, {
    method: 'PUT',
    body: file
  });

  if (!uploadResponse.ok) {
    throw new Error(`Upload failed: ${uploadResponse.status}`);
  }

  return fileId;
};

export const getDownloadUrl = async (fileId: string): Promise<DownloadUrlResult> =>
  DriveApiClient.call<DownloadUrlResult>('/download', { fileId });

export const deleteFile = async (fileId: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'delete', fileId });

export const moveFile = async (fileId: string, destinationPath: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'move-file', fileId, destinationPath });

export const renameFile = async (fileId: string, newName: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'rename-file', fileId, newName });

export const moveFolder = async (folderPath: string, destinationPath: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'move-folder', folderPath, destinationPath });

export const renameFolder = async (folderPath: string, newName: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'rename-folder', folderPath, newName });

export const listSharedWithMe = async (): Promise<SharedWithMeResult> =>
  DriveApiClient.call<SharedWithMeResult>('/upload', { action: 'shared-with-me' });

export const shareFile = async (
  fileId: string,
  shareWithEmail: string,
  permission: string,
  expiryDays?: number
): Promise<ShareFileResult> =>
  DriveApiClient.call<ShareFileResult>('/upload', {
    action: 'share',
    fileId,
    shareWithEmail,
    permission,
    ...(expiryDays !== undefined ? { expiryDays } : {})
  });

export const listFileShares = async (fileId: string): Promise<ListFileSharesResult> =>
  DriveApiClient.call<ListFileSharesResult>('/upload', { action: 'list-shares', fileId });

export const unshareFile = async (fileId: string, revokeUserId: string): Promise<UnshareResult> =>
  DriveApiClient.call<UnshareResult>('/upload', { action: 'unshare', fileId, revokeUserId });

export const updateSharePermission = async (
  fileId: string,
  targetUserId: string,
  permission: string
): Promise<UpdateShareResult> =>
  DriveApiClient.call<UpdateShareResult>('/upload', {
    action: 'update-share',
    fileId,
    targetUserId,
    permission
  });
