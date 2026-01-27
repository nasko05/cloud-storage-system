import { config } from './config';
import { getToken } from './auth';

const apiCall = async (endpoint, body) => {
  const token = await getToken();
  const res = await fetch(`${config.apiEndpoint}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(body)
  });
  return res.json();
};

export const listFiles = () => apiCall('/upload', { action: 'list' });

export const getUploadUrl = (filename, contentType, size) => 
  apiCall('/upload', { filename, contentType, size });

export const uploadFile = async (file) => {
  const { uploadUrl, fileId, error } = await getUploadUrl(file.name, file.type, file.size);
  if (error) throw new Error(error);
  
  await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': file.type },
    body: file
  });
  return fileId;
};

export const getDownloadUrl = (fileId) => apiCall('/download', { fileId });

export const deleteFile = (fileId) => apiCall('/upload', { action: 'delete', fileId });
