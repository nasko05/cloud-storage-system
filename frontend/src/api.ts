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

interface CreateDownloadZipResult extends ApiResult {
  downloadUrl?: string;
  expiresIn?: number;
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

// --- Public link types (authenticated CRUD) ---

interface CreatePublicLinkResult extends ApiResult {
  token?: string;
  fileId?: string;
  filename?: string;
  hasPassword?: boolean;
  downloadCount?: number;
  createdAt?: string;
  expiresAt?: string;
}

interface ListPublicLinksResult extends ApiResult {
  links?: Array<{
    token: string;
    fileId: string;
    filename: string;
    hasPassword: boolean;
    downloadCount: number;
    createdAt: string;
    expiresAt: string;
  }>;
}

// --- Public link types (unauthenticated access) ---

interface PublicLinkInfoResult extends ApiResult {
  filename?: string;
  size?: number;
  contentType?: string;
  hasPassword?: boolean;
  downloadCount?: number;
  expiresAt?: string;
}

interface PublicDownloadResult extends ApiResult {
  downloadUrl?: string;
  filename?: string;
  contentType?: string;
  size?: number;
  expiresIn?: number;
}

class DriveApiClient {
  /** Authenticated API call (attaches JWT). */
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

  /** Unauthenticated API call (no JWT). */
  public static async publicCall<T extends ApiResult>(
    endpoint: string,
    method: 'GET' | 'POST' = 'GET',
    body?: ApiBody
  ): Promise<T> {
    const options: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body && method === 'POST') {
      options.body = JSON.stringify(body);
    }
    const resp = await fetch(`${config.apiEndpoint}${endpoint}`, options);

    if (!resp.ok) {
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

export const createDownloadZip = async (
  fileIds: string[],
  folderPaths: string[]
): Promise<CreateDownloadZipResult> =>
  DriveApiClient.call<CreateDownloadZipResult>('/zip', { fileIds, folderPaths });

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

// ---------------------------------------------------------------------------
// Public link CRUD (authenticated)
// ---------------------------------------------------------------------------

export const createPublicLink = async (
  fileId: string,
  password?: string,
  expiryDays?: number
): Promise<CreatePublicLinkResult> =>
  DriveApiClient.call<CreatePublicLinkResult>('/upload', {
    action: 'create-public-link',
    fileId,
    ...(password ? { password } : {}),
    ...(expiryDays !== undefined ? { expiryDays } : {}),
  });

export const listPublicLinks = async (fileId: string): Promise<ListPublicLinksResult> =>
  DriveApiClient.call<ListPublicLinksResult>('/upload', { action: 'list-public-links', fileId });

export const deletePublicLink = async (token: string): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', { action: 'delete-public-link', token });

export const updatePublicLink = async (
  token: string,
  options: { password?: string; removePassword?: boolean; expiryDays?: number }
): Promise<ApiResult> =>
  DriveApiClient.call<ApiResult>('/upload', {
    action: 'update-public-link',
    token,
    ...options,
  });

// ---------------------------------------------------------------------------
// Public download (unauthenticated)
// ---------------------------------------------------------------------------

export const getPublicLinkInfo = async (token: string): Promise<PublicLinkInfoResult> =>
  DriveApiClient.publicCall<PublicLinkInfoResult>(`/public/${encodeURIComponent(token)}`, 'GET');

export const downloadPublicLink = async (
  token: string,
  password?: string
): Promise<PublicDownloadResult> =>
  DriveApiClient.publicCall<PublicDownloadResult>(
    `/public/${encodeURIComponent(token)}`,
    'POST',
    password ? { password } : {}
  );
