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

export interface UploadFileOptions {
  signal?: AbortSignal;
  onProgress?: (uploadedBytes: number, totalBytes: number) => void;
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

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

type PagedItems<T> = {
  items?: T[];
  nextCursor?: string | null;
};

interface V2FolderChildItem {
  type?: 'file' | 'folder';
  fileId?: string;
  folderId?: string;
  name?: string;
  size?: number;
  createdAt?: string;
  updatedAt?: string;
  sharedAt?: string;
  permission?: string;
  hasPassword?: boolean;
  downloadCount?: number;
  expiresAt?: string;
  principalType?: string;
  principalValue?: string;
  principalDisplay?: string;
  ownerId?: string;
  ownerEmail?: string;
  filename?: string;
  token?: string;
  isShared?: boolean;
  hasPublicLink?: boolean;
}

interface V2ArchiveCreateResult extends ApiResult {
  archiveJobId?: string;
  status?: string;
}

interface V2ArchiveStatusResult extends ApiResult {
  archiveJobId?: string;
  status?: 'queued' | 'processing' | 'ready' | 'failed' | 'expired';
  downloadUrl?: string;
  expiresIn?: number;
  errorMessage?: string;
}

const ROOT_FOLDER_ID = 'root';
const ARCHIVE_POLL_INTERVAL_MS = 1500;
const ARCHIVE_POLL_TIMEOUT_MS = 2 * 60 * 1000;

const folderPathCache = new Map<string, string>([['/', ROOT_FOLDER_ID]]);

function resetFolderPathCache(): void {
  folderPathCache.clear();
  folderPathCache.set('/', ROOT_FOLDER_ID);
}

class DriveApiClient {
  private static async request<T>(
    endpoint: string,
    method: HttpMethod,
    body?: ApiBody,
    auth = true
  ): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (auth) {
      const token = await getToken();
      headers.Authorization = `Bearer ${token ?? ''}`;
    }

    const init: RequestInit = {
      method,
      headers,
    };

    if (body && method !== 'GET') {
      init.body = JSON.stringify(body);
    }

    const resp = await fetch(`${config.apiEndpoint}${endpoint}`, init);
    if (resp.status === 401) {
      throw new Error('Session expired. Please log in again.');
    }

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

  public static authRequest<T>(
    endpoint: string,
    method: HttpMethod,
    body?: ApiBody
  ): Promise<T> {
    return this.request<T>(endpoint, method, body, true);
  }

  public static publicCall<T>(
    endpoint: string,
    method: 'GET' | 'POST' = 'GET',
    body?: ApiBody
  ): Promise<T> {
    return this.request<T>(endpoint, method, body, false);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function normalizePath(path?: string): string {
  if (!path || path === '/') return '/';
  const trimmed = path.trim();
  if (!trimmed) return '/';
  const withLeadingSlash = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  const normalized = withLeadingSlash.replace(/\/+/g, '/').replace(/\/$/, '');
  return normalized || '/';
}

function joinChildPath(parentPath: string, childName: string): string {
  return parentPath === '/' ? `/${childName}` : `${parentPath}/${childName}`;
}

function principalPath(value: string): string {
  const raw = value.trim();
  if (raw.startsWith('email:') || raw.startsWith('user_sub:')) {
    return raw;
  }
  return raw.includes('@') ? `email:${raw}` : `user_sub:${raw}`;
}

async function listFolderChildrenById(folderId: string, cursor?: string): Promise<PagedItems<V2FolderChildItem>> {
  const query = new URLSearchParams();
  query.set('limit', '200');
  if (cursor) query.set('cursor', cursor);

  return DriveApiClient.authRequest<PagedItems<V2FolderChildItem>>(
    `/v2/folders/${encodeURIComponent(folderId)}/children?${query.toString()}`,
    'GET'
  );
}

async function listAllFolderChildren(folderId: string): Promise<V2FolderChildItem[]> {
  const out: V2FolderChildItem[] = [];
  let cursor: string | undefined;

  do {
    const page = await listFolderChildrenById(folderId, cursor);
    if (Array.isArray(page.items)) out.push(...page.items);
    cursor = page.nextCursor || undefined;
  } while (cursor);

  return out;
}

async function resolveFolderIdByPath(path?: string): Promise<string> {
  const normalizedPath = normalizePath(path);
  const cached = folderPathCache.get(normalizedPath);
  if (cached) return cached;

  if (normalizedPath === '/') {
    folderPathCache.set('/', ROOT_FOLDER_ID);
    return ROOT_FOLDER_ID;
  }

  const segments = normalizedPath.split('/').filter(Boolean);
  let currentId = ROOT_FOLDER_ID;
  let currentPath = '/';

  for (const segment of segments) {
    const children = await listAllFolderChildren(currentId);
    const folder = children.find((item) => item.type === 'folder' && item.name === segment);
    if (!folder?.folderId) {
      throw new Error(`Folder not found: ${normalizedPath}`);
    }
    currentId = folder.folderId;
    currentPath = joinChildPath(currentPath, segment);
    folderPathCache.set(currentPath, currentId);
  }

  return currentId;
}

async function fetchAllPages<T>(
  routeFactory: (cursor?: string) => string,
  mapper: (item: T) => void
): Promise<void> {
  let cursor: string | undefined;
  do {
    const page = await DriveApiClient.authRequest<PagedItems<T>>(routeFactory(cursor), 'GET');
    if (Array.isArray(page.items)) {
      for (const item of page.items) mapper(item);
    }
    cursor = page.nextCursor || undefined;
  } while (cursor);
}

export const listFiles = async (folder?: string): Promise<ListFilesResult> => {
  const currentPath = normalizePath(folder);
  const folderId = await resolveFolderIdByPath(currentPath);
  const items = await listAllFolderChildren(folderId);

  const files = items
    .filter((item) => item.type === 'file' && item.fileId && item.name)
    .map((item) => ({
      fileId: item.fileId as string,
      filename: item.name as string,
      size: Number(item.size ?? 0),
      createdAt: (item.createdAt || item.updatedAt || '') as string,
      isShared: Boolean(item.isShared),
      hasPublicLink: Boolean(item.hasPublicLink),
    }));

  const folders = items
    .filter((item) => item.type === 'folder' && item.folderId && item.name)
    .map((item) => {
      const pathValue = joinChildPath(currentPath, item.name as string);
      folderPathCache.set(pathValue, item.folderId as string);
      return {
        folderId: item.folderId as string,
        name: item.name as string,
        path: pathValue,
        createdAt: item.createdAt,
      };
    });

  return { files, folders };
};

export const createFolder = async (folderName: string, path?: string): Promise<CreateFolderResult> => {
  const parentPath = normalizePath(path);
  const parentFolderId = await resolveFolderIdByPath(parentPath);

  const result = await DriveApiClient.authRequest<{
    folderId?: string;
    name?: string;
  }>(`/v2/folders/${encodeURIComponent(parentFolderId)}/folders`, 'POST', { name: folderName });

  const createdName = result.name ?? folderName;
  const createdPath = joinChildPath(parentPath, createdName);
  if (result.folderId) folderPathCache.set(createdPath, result.folderId);

  return {
    folderId: result.folderId,
    folderName: createdName,
    path: createdPath,
  };
};

export const deleteFolder = async (path: string, recursive = false): Promise<ApiResult> => {
  const folderId = await resolveFolderIdByPath(path);
  const query = recursive ? '?recursive=true' : '';
  const result = await DriveApiClient.authRequest<ApiResult>(
    `/v2/folders/${encodeURIComponent(folderId)}${query}`,
    'DELETE'
  );
  resetFolderPathCache();
  return result;
};

const getUploadUrl = async (
  filename: string,
  contentType: string,
  size: number,
  path?: string
): Promise<UploadUrlResult> => {
  const parentFolderId = await resolveFolderIdByPath(path);

  return DriveApiClient.authRequest<UploadUrlResult>('/v2/files/uploads', 'POST', {
    filename,
    contentType,
    size,
    parentFolderId,
  });
};

const finalizeUpload = async (fileId: string): Promise<void> => {
  await DriveApiClient.authRequest<ApiResult>(
    `/v2/files/${encodeURIComponent(fileId)}/finalize`,
    'POST',
    {}
  );
};

export const uploadFile = async (
  file: File,
  folderPath?: string,
  options?: UploadFileOptions
): Promise<string> => {
  let contentType = file.type || 'application/octet-stream';

  if (file.name.toLowerCase().endsWith('.pdf')) {
    contentType = 'application/pdf';
  }

  const { uploadUrl, fileId, error } = await getUploadUrl(file.name, contentType, file.size, folderPath);
  if (error || !uploadUrl || !fileId) {
    throw new Error(error || 'Upload URL not available');
  }

  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    const cleanupSignal = (): void => {
      if (options?.signal) {
        options.signal.removeEventListener('abort', handleAbortSignal);
      }
    };

    const fail = (err: Error): void => {
      cleanupSignal();
      reject(err);
    };

    const handleAbortSignal = (): void => {
      xhr.abort();
    };

    xhr.open('PUT', uploadUrl);

    xhr.upload.onprogress = (event: ProgressEvent<EventTarget>): void => {
      const total = event.lengthComputable ? event.total : file.size;
      options?.onProgress?.(event.loaded, total);
    };

    xhr.onload = (): void => {
      cleanupSignal();
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        fail(new Error(`Upload failed: ${xhr.status}`));
      }
    };

    xhr.onerror = (): void => {
      fail(new Error('Upload failed due to a network error'));
    };

    xhr.onabort = (): void => {
      fail(new Error('Upload canceled'));
    };

    if (options?.signal) {
      if (options.signal.aborted) {
        xhr.abort();
        return;
      }
      options.signal.addEventListener('abort', handleAbortSignal, { once: true });
    }

    xhr.send(file);
  });

  await finalizeUpload(fileId);
  return fileId;
};

export const getDownloadUrl = async (fileId: string): Promise<DownloadUrlResult> =>
  DriveApiClient.authRequest<DownloadUrlResult>(`/v2/download/files/${encodeURIComponent(fileId)}`, 'POST', {});

export const createDownloadZip = async (
  fileIds: string[],
  folderPaths: string[]
): Promise<CreateDownloadZipResult> => {
  const folderIds: string[] = [];
  for (const path of folderPaths) {
    folderIds.push(await resolveFolderIdByPath(path));
  }

  const created = await DriveApiClient.authRequest<V2ArchiveCreateResult>('/v2/download/archives', 'POST', {
    fileIds,
    folderIds,
  });

  if (created.error || !created.archiveJobId) {
    throw new Error(created.error || 'Failed to create archive job');
  }

  const startedAt = Date.now();
  while (Date.now() - startedAt < ARCHIVE_POLL_TIMEOUT_MS) {
    const status = await DriveApiClient.authRequest<V2ArchiveStatusResult>(
      `/v2/download/archives/${encodeURIComponent(created.archiveJobId)}`,
      'GET'
    );

    if (status.status === 'ready' && status.downloadUrl) {
      return { downloadUrl: status.downloadUrl, expiresIn: status.expiresIn };
    }

    if (status.status === 'failed' || status.status === 'expired') {
      throw new Error(status.errorMessage || `Archive ${status.status}`);
    }

    await sleep(ARCHIVE_POLL_INTERVAL_MS);
  }

  throw new Error('Archive generation timed out');
};

export const deleteFile = async (fileId: string): Promise<ApiResult> =>
  DriveApiClient.authRequest<ApiResult>(`/v2/files/${encodeURIComponent(fileId)}`, 'DELETE');

export const moveFile = async (fileId: string, destinationPath: string): Promise<ApiResult> => {
  const destinationFolderId = await resolveFolderIdByPath(destinationPath);
  return DriveApiClient.authRequest<ApiResult>(`/v2/files/${encodeURIComponent(fileId)}`, 'PATCH', {
    destinationFolderId,
  });
};

export const renameFile = async (fileId: string, newName: string): Promise<ApiResult> =>
  DriveApiClient.authRequest<ApiResult>(`/v2/files/${encodeURIComponent(fileId)}`, 'PATCH', { newName });

export const moveFolder = async (folderPath: string, destinationPath: string): Promise<ApiResult> => {
  const folderId = await resolveFolderIdByPath(folderPath);
  const destinationFolderId = await resolveFolderIdByPath(destinationPath);
  const result = await DriveApiClient.authRequest<ApiResult>(`/v2/folders/${encodeURIComponent(folderId)}`, 'PATCH', {
    destinationFolderId,
  });
  resetFolderPathCache();
  return result;
};

export const renameFolder = async (folderPath: string, newName: string): Promise<ApiResult> => {
  const folderId = await resolveFolderIdByPath(folderPath);
  const result = await DriveApiClient.authRequest<ApiResult>(`/v2/folders/${encodeURIComponent(folderId)}`, 'PATCH', {
    newName,
  });
  resetFolderPathCache();
  return result;
};

export const listSharedWithMe = async (): Promise<SharedWithMeResult> => {
  const files: SharedWithMeResult['files'] = [];

  await fetchAllPages<V2FolderChildItem>(
    (cursor) => {
      const query = new URLSearchParams();
      query.set('limit', '200');
      if (cursor) query.set('cursor', cursor);
      return `/v2/shares/inbound?${query.toString()}`;
    },
    (item) => {
      files?.push({
        fileId: String(item.fileId || ''),
        sharedBy: String(item.ownerId || ''),
        sharedByEmail: String(item.ownerEmail || ''),
        filename: String(item.filename || item.name || ''),
        permission: String(item.permission || 'read'),
        expiresAt: String(item.expiresAt || ''),
      });
    }
  );

  return { files };
};

export const shareFile = async (
  fileId: string,
  shareWithEmail: string,
  permission: string,
  expiryDays?: number
): Promise<ShareFileResult> => {
  const principal = principalPath(shareWithEmail);
  const result = await DriveApiClient.authRequest<{
    fileId?: string;
    expiresAt?: string;
  }>(
    `/v2/files/${encodeURIComponent(fileId)}/shares/${encodeURIComponent(principal)}`,
    'PUT',
    {
      permission,
      ...(expiryDays !== undefined ? { expiryDays } : {}),
    }
  );

  return {
    message: 'Shared successfully',
    fileId: result.fileId ?? fileId,
    sharedWith: shareWithEmail,
    expiresAt: result.expiresAt,
  };
};

export const listFileShares = async (fileId: string): Promise<ListFileSharesResult> => {
  const shares: ListFileSharesResult['shares'] = [];

  await fetchAllPages<V2FolderChildItem>(
    (cursor) => {
      const query = new URLSearchParams();
      query.set('limit', '200');
      if (cursor) query.set('cursor', cursor);
      return `/v2/files/${encodeURIComponent(fileId)}/shares?${query.toString()}`;
    },
    (item) => {
      shares?.push({
        sharedWith: String(item.principalDisplay || item.principalValue || ''),
        permission: String(item.permission || 'read'),
        sharedAt: String(item.sharedAt || item.createdAt || ''),
        expiresAt: String(item.expiresAt || ''),
      });
    }
  );

  return { shares };
};

export const unshareFile = async (fileId: string, revokeUserId: string): Promise<UnshareResult> => {
  const principal = principalPath(revokeUserId);
  await DriveApiClient.authRequest<ApiResult>(
    `/v2/files/${encodeURIComponent(fileId)}/shares/${encodeURIComponent(principal)}`,
    'DELETE'
  );

  return { message: 'Share revoked', fileId, revokedUser: revokeUserId };
};

export const updateSharePermission = async (
  fileId: string,
  targetUserId: string,
  permission: string
): Promise<UpdateShareResult> => {
  const principal = principalPath(targetUserId);
  await DriveApiClient.authRequest<ApiResult>(
    `/v2/files/${encodeURIComponent(fileId)}/shares/${encodeURIComponent(principal)}`,
    'PATCH',
    { permission }
  );

  return { message: 'Permission updated', fileId, targetUserId, permission };
};

export const createPublicLink = async (
  fileId: string,
  password?: string,
  expiryDays?: number
): Promise<CreatePublicLinkResult> =>
  DriveApiClient.authRequest<CreatePublicLinkResult>(
    `/v2/files/${encodeURIComponent(fileId)}/public-links`,
    'POST',
    {
      ...(password ? { password } : {}),
      ...(expiryDays !== undefined ? { expiryDays } : {}),
    }
  );

export const listPublicLinks = async (fileId: string): Promise<ListPublicLinksResult> => {
  const links: NonNullable<ListPublicLinksResult['links']> = [];

  await fetchAllPages<V2FolderChildItem>(
    (cursor) => {
      const query = new URLSearchParams();
      query.set('limit', '200');
      if (cursor) query.set('cursor', cursor);
      return `/v2/files/${encodeURIComponent(fileId)}/public-links?${query.toString()}`;
    },
    (item) => {
      links.push({
        token: String(item.token || ''),
        fileId,
        filename: String(item.filename || ''),
        hasPassword: Boolean(item.hasPassword),
        downloadCount: Number(item.downloadCount ?? 0),
        createdAt: String(item.createdAt || ''),
        expiresAt: String(item.expiresAt || ''),
      });
    }
  );

  return { links };
};

export const deletePublicLink = async (token: string): Promise<ApiResult> =>
  DriveApiClient.authRequest<ApiResult>(`/v2/public-links/${encodeURIComponent(token)}`, 'DELETE');

export const updatePublicLink = async (
  token: string,
  options: { password?: string; removePassword?: boolean; expiryDays?: number }
): Promise<ApiResult> =>
  DriveApiClient.authRequest<ApiResult>(`/v2/public-links/${encodeURIComponent(token)}`, 'PATCH', options);

export const getPublicLinkInfo = async (token: string): Promise<PublicLinkInfoResult> =>
  DriveApiClient.publicCall<PublicLinkInfoResult>(`/v2/public-links/${encodeURIComponent(token)}`, 'GET');

export const downloadPublicLink = async (token: string, password?: string): Promise<PublicDownloadResult> =>
  DriveApiClient.publicCall<PublicDownloadResult>(
    `/v2/public-links/${encodeURIComponent(token)}/download`,
    'POST',
    password ? { password } : {}
  );

// --- AI reorganization assistant -------------------------------------------

export interface AgentMessage {
  role: string;
  content?: string | null;
  tool_calls?: unknown;
  tool_call_id?: string;
  name?: string;
}

export interface AgentPendingAction {
  tool_call_id: string;
  tool: string;
  args: Record<string, unknown>;
  summary: string;
}

export interface AgentChatResponse {
  messages: AgentMessage[];
  assistant_text: string | null;
  pending_actions: AgentPendingAction[];
  done: boolean;
}

export interface AgentStatus {
  configured: boolean;
  model: string;
}

export type AgentOperation = { tool: string } & Record<string, unknown>;

export const agentStatus = async (): Promise<AgentStatus> =>
  DriveApiClient.authRequest<AgentStatus>('/v2/agent/status', 'GET');

export const agentChat = async (messages: AgentMessage[]): Promise<AgentChatResponse> =>
  DriveApiClient.authRequest<AgentChatResponse>('/v2/agent/chat', 'POST', { messages });

export const agentApply = async (operations: AgentOperation[]): Promise<{ applied: number }> => {
  const result = await DriveApiClient.authRequest<{ applied: number }>('/v2/agent/apply', 'POST', { operations });
  // A reorganization can create/move/rename folders, so the path→id cache the
  // listing helpers rely on may now be stale; drop it so the next load re-resolves.
  resetFolderPathCache();
  return result;
};
