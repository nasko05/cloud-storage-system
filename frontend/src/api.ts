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

class DriveApiClient {
  public static async call<T extends ApiResult>(endpoint: string, body: ApiBody): Promise<T> {
    const token = await getToken();
    const response = await fetch(`${config.apiEndpoint}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token ?? ''}`
      },
      body: JSON.stringify(body)
    });

    return (await response.json()) as T;
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
