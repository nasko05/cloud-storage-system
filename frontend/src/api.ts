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
}

interface UploadUrlResult extends ApiResult {
  uploadUrl?: string;
  fileId?: string;
}

interface DownloadUrlResult extends ApiResult {
  downloadUrl?: string;
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

export const listFiles = async (): Promise<ListFilesResult> =>
  DriveApiClient.call<ListFilesResult>('/upload', { action: 'list' });

const getUploadUrl = async (
  filename: string,
  contentType: string,
  size: number
): Promise<UploadUrlResult> =>
  DriveApiClient.call<UploadUrlResult>('/upload', { filename, contentType, size });

export const uploadFile = async (file: File): Promise<string> => {
  let contentType = file.type || 'application/octet-stream';

  if (file.name.toLowerCase().endsWith('.pdf')) {
    contentType = 'application/pdf';
  }

  const { uploadUrl, fileId, error } = await getUploadUrl(file.name, contentType, file.size);
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
