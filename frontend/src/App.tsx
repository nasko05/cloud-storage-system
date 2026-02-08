import React, { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  CssBaseline,
  Paper,
  Stack,
  TextField,
  Toolbar,
  Typography
} from '@mui/material';
import CloudUploadRoundedIcon from '@mui/icons-material/CloudUploadRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import { DataGrid } from '@mui/x-data-grid';
import { login, logout, getToken, register, confirmRegistration } from './auth';
import { deleteFile, getDownloadUrl, listFiles, uploadFile } from './api';
import { DensitySelectorToolbar } from './components/DensitySelectorToolbar';
import { DriveFile, FileColumnsFactory, FileGridRow } from './components/File';
import './App.css';

type AuthMode = 'login' | 'register' | 'confirm';

class FileCollection {
  public static fromUnknown(payload: unknown): DriveFile[] {
    if (!Array.isArray(payload)) {
      return [];
    }

    return payload
      .map((item) => DriveFile.fromUnknown(item))
      .filter((item): item is DriveFile => item !== null);
  }
}

function App(): JSX.Element {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [confirmCode, setConfirmCode] = useState<string>('');
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [authMode, setAuthMode] = useState<AuthMode>('login');
  const [pendingEmail, setPendingEmail] = useState<string>('');
  const [uploadProgress, setUploadProgress] = useState<string>('');

  useEffect(() => {
    const bootstrap = async (): Promise<void> => {
      const existingToken = await getToken();
      if (existingToken) {
        setToken(existingToken);
        await loadFiles();
      }
    };

    void bootstrap();
  }, []);

  const loadFiles = async (): Promise<void> => {
    setLoading(true);
    setError('');
    try {
      const data = await listFiles();
      setFiles(FileCollection.fromUnknown(data.files));
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Failed to load files';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError('');
    try {
      const authToken = await login(email, password);
      setToken(authToken);
      await loadFiles();
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Login failed';
      setError(message);
    }
  };

  const handleRegister = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError('');
    try {
      await register(email, password);
      setPendingEmail(email);
      setAuthMode('confirm');
      setEmail('');
      setPassword('');
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Registration failed';
      setError(message);
    }
  };

  const handleConfirm = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError('');
    try {
      await confirmRegistration(pendingEmail, confirmCode);
      setAuthMode('login');
      setConfirmCode('');
    } catch (caughtError: unknown) {
      const message =
        caughtError instanceof Error ? caughtError.message : 'Confirmation failed';
      setError(message);
    }
  };

  const handleLogout = (): void => {
    logout();
    setToken(null);
    setFiles([]);
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const selectedFiles = Array.from(event.target.files ?? []);
    if (selectedFiles.length === 0) {
      return;
    }

    setLoading(true);
    setError('');
    setUploadProgress('');

    let successCount = 0;
    let failureCount = 0;

    for (let index = 0; index < selectedFiles.length; index += 1) {
      const current = selectedFiles[index];
      setUploadProgress(`Uploading ${index + 1}/${selectedFiles.length}: ${current.name}`);
      try {
        await uploadFile(current);
        successCount += 1;
      } catch (caughtError: unknown) {
        failureCount += 1;
        console.error(`Failed to upload ${current.name}:`, caughtError);
      }
    }

    setUploadProgress('');
    if (failureCount > 0) {
      setError(`Uploaded ${successCount} files, ${failureCount} failed`);
    }

    await loadFiles();
    setLoading(false);
    event.target.value = '';
  };

  async function handleDownload(file: DriveFile): Promise<void> {
    try {
      const { downloadUrl, error: downloadError } = await getDownloadUrl(file.fileId);
      if (downloadError) {
        throw new Error(downloadError);
      }

      window.open(downloadUrl, '_blank', 'noopener,noreferrer');
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Download failed';
      setError(message);
    }
  }

  async function handleDelete(file: DriveFile): Promise<void> {
    if (!window.confirm(`Delete "${file.filename}"?`)) {
      return;
    }

    setLoading(true);
    setError('');
    try {
      const result = await deleteFile(file.fileId);
      if (result.error) {
        setError(`Delete failed: ${result.error}`);
      } else {
        setFiles((current) => current.filter((entry) => entry.fileId !== file.fileId));
      }
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Delete failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  const rows: FileGridRow[] = files.map((file) => file.toGridRow());
  const columns = FileColumnsFactory.create({
    onDownload: handleDownload,
    onDelete: handleDelete
  });

  const authForm = (
    <Card sx={{ maxWidth: 460, mx: 'auto', mt: 12, borderRadius: 3 }}>
      <CardContent sx={{ p: 4 }}>
        <Stack spacing={2.5}>
          <Typography variant="h4" fontWeight={700}>
            Personal Drive
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {authMode === 'confirm'
              ? `Enter the verification code sent to ${pendingEmail}`
              : 'Authenticate to manage your files'}
          </Typography>
          <Box
            component="form"
            onSubmit={
              authMode === 'confirm'
                ? handleConfirm
                : authMode === 'login'
                  ? handleLogin
                  : handleRegister
            }
          >
            <Stack spacing={2}>
              {authMode !== 'confirm' && (
                <TextField
                  required
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              )}
              {authMode !== 'confirm' && (
                <TextField
                  required
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              )}
              {authMode === 'confirm' && (
                <TextField
                  required
                  label="Verification Code"
                  value={confirmCode}
                  onChange={(event) => setConfirmCode(event.target.value)}
                />
              )}

              {error && <Alert severity="error">{error}</Alert>}

              <Button type="submit" size="large" variant="contained">
                {authMode === 'login'
                  ? 'Login'
                  : authMode === 'register'
                    ? 'Register'
                    : 'Confirm'}
              </Button>

              {authMode === 'confirm' ? (
                <Button variant="text" onClick={() => setAuthMode('login')}>
                  Back to login
                </Button>
              ) : (
                <Button
                  variant="text"
                  onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
                >
                  {authMode === 'login'
                    ? "Don't have an account? Register"
                    : 'Already have an account? Login'}
                </Button>
              )}
            </Stack>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );

  const driveView = (
    <Stack spacing={3} sx={{ py: 4 }}>
      <Paper elevation={1} sx={{ borderRadius: 3, overflow: 'hidden' }}>
        <AppBar position="static" color="transparent" elevation={0}>
          <Toolbar sx={{ justifyContent: 'space-between', px: { xs: 2, md: 3 } }}>
            <Typography variant="h5" fontWeight={700}>
              Personal Drive
            </Typography>
            <Button
              color="inherit"
              variant="outlined"
              onClick={handleLogout}
              startIcon={<LogoutRoundedIcon />}
            >
              Logout
            </Button>
          </Toolbar>
        </AppBar>
      </Paper>

      <Paper elevation={1} sx={{ borderRadius: 3, p: 2.5 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="center">
          <Button
            component="label"
            variant="contained"
            startIcon={<CloudUploadRoundedIcon />}
            disabled={loading}
          >
            Upload Files
            <input type="file" hidden multiple onChange={handleUpload} />
          </Button>
          <Typography variant="body2" color="text.secondary">
            Upload multiple files in a single batch.
          </Typography>
        </Stack>
      </Paper>

      {error && <Alert severity="error">{error}</Alert>}
      {uploadProgress && <Alert severity="info">{uploadProgress}</Alert>}

      <Paper elevation={1} sx={{ borderRadius: 3, p: 1.5 }}>
        <Box sx={{ width: '100%' }}>
          <DataGrid
            rows={rows}
            columns={columns}
            autoHeight
            loading={loading}
            disableRowSelectionOnClick
            pageSizeOptions={[5, 10, 20]}
            initialState={{
              pagination: {
                paginationModel: { page: 0, pageSize: 10 }
              }
            }}
            slots={{
              toolbar: DensitySelectorToolbar,
              noRowsOverlay: () => (
                <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
                  <Typography variant="body1" color="text.secondary">
                    No files yet. Upload something to get started.
                  </Typography>
                </Stack>
              ),
              loadingOverlay: () => (
                <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
                  <CircularProgress size={28} />
                </Stack>
              )
            }}
          />
        </Box>
      </Paper>
    </Stack>
  );

  return (
    <>
      <CssBaseline />
      <Container maxWidth="md">{token ? driveView : authForm}</Container>
    </>
  );
}

export default App;
