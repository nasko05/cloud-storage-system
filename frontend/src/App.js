import React, { useState, useEffect } from 'react';
import { login, logout, getToken } from './auth';
import { listFiles, uploadFile, getDownloadUrl, deleteFile } from './api';
import './App.css';

function App() {
  const [token, setToken] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    getToken().then(t => { if (t) { setToken(t); loadFiles(); } });
  }, []);

  const loadFiles = async () => {
    setLoading(true);
    try {
      const data = await listFiles();
      setFiles(data.files || []);
    } catch (e) {
      setError('Failed to load files');
    }
    setLoading(false);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const t = await login(email, password);
      setToken(t);
      loadFiles();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleLogout = () => {
    logout();
    setToken(null);
    setFiles([]);
  };


  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setLoading(true);
    setError('');
    try {
      await uploadFile(file);
      loadFiles();
    } catch (e) {
      setError('Upload failed: ' + e.message);
    }
    setLoading(false);
  };

  const handleDownload = async (fileId, filename) => {
    try {
      const { downloadUrl, error } = await getDownloadUrl(fileId);
      if (error) throw new Error(error);
      window.open(downloadUrl, '_blank');
    } catch (e) {
      setError('Download failed: ' + e.message);
    }
  };

  const handleDelete = async (fileId) => {
    if (!window.confirm('Delete this file?')) return;
    setLoading(true);
    try {
      await deleteFile(fileId);
      loadFiles();
    } catch (e) {
      setError('Delete failed');
    }
    setLoading(false);
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  if (!token) {
    return (
      <div className="container">
        <h1>Personal Drive</h1>
        <form onSubmit={handleLogin} className="login-form">
          <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required />
          <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required />
          <button type="submit">Login</button>
          {error && <p className="error">{error}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="container">
      <header>
        <h1>Personal Drive</h1>
        <button onClick={handleLogout}>Logout</button>
      </header>
      
      <div className="upload-section">
        <label className="upload-btn">
          Upload File
          <input type="file" onChange={handleUpload} hidden />
        </label>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p>Loading...</p>}

      <div className="file-list">
        {files.length === 0 ? (
          <p className="empty">No files yet. Upload something!</p>
        ) : (
          files.map(file => (
            <div key={file.fileId} className="file-item">
              <div className="file-info">
                <span className="filename">{file.filename}</span>
                <span className="meta">{formatSize(file.size)}</span>
              </div>
              <div className="file-actions">
                <button onClick={() => handleDownload(file.fileId, file.filename)}>Download</button>
                <button onClick={() => handleDelete(file.fileId)} className="delete">Delete</button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default App;
