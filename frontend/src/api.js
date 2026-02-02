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
  let contentType = file.type || 'application/octet-stream';
  
  // Force correct content types for common files
  if (file.name.toLowerCase().endsWith('.pdf')) {
    contentType = 'application/pdf';
  }
  
  const { uploadUrl, fileId, error } = await getUploadUrl(file.name, contentType, file.size);
  if (error) throw new Error(error);
  
  const response = await fetch(uploadUrl, {
    method: 'PUT',
    body: file
  });
  
  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }
  
  return fileId;
};

export const getDownloadUrl = (fileId) => apiCall('/download', { fileId });

export const deleteFile = (fileId) => apiCall('/upload', { action: 'delete', fileId });
