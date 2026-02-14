import React, { ChangeEvent, FormEvent, useCallback, useEffect, useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  CssBaseline,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Toolbar,
  Typography
} from '@mui/material';
import CreateNewFolderRoundedIcon from '@mui/icons-material/CreateNewFolderRounded';
import GridViewRoundedIcon from '@mui/icons-material/GridViewRounded';
import ViewListRoundedIcon from '@mui/icons-material/ViewListRounded';
import CloudUploadRoundedIcon from '@mui/icons-material/CloudUploadRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import { login, logout, getToken, register, confirmRegistration } from './auth';
import { createFolder, deleteFolder, uploadFile } from './api';
import {
  fetchFiles,
  getFileDownloadUrl,
  deleteFileResult,
  moveFileResult,
  moveFolderResult,
  renameFileResult,
  renameFolderResult
} from './service/driveService';
import type { DriveFolder } from './components/Folder';
import {
  DriveFile,
  type DriveListRow,
  FileColumnsFactory,
  FileGridRow,
  ListColumnsFactory
} from './components/File';
import { GridLayout, type GridSize } from './components/GridLayout';
import { ListLayout } from './components/ListLayout';
import { ContextMenu, type ContextMenuTarget, type ContextMenuPosition } from './components/ContextMenu';
import { RenameDialog, type RenameTarget } from './components/RenameDialog';
import { MoveDialog, type MoveItem } from './components/MoveDialog';
import './App.css';

type AuthMode = 'login' | 'register' | 'confirm';
type ViewMode = 'grid' | 'list';

const VIEW_PREFS_KEY = 'driveViewPrefs';

function readViewPrefs(): { viewMode: ViewMode; gridSize: GridSize } {
  try {
    const raw = localStorage.getItem(VIEW_PREFS_KEY);
    if (!raw) return { viewMode: 'grid', gridSize: 'medium' };
    const parsed = JSON.parse(raw) as { viewMode?: string; gridSize?: string };
    const viewMode =
      parsed.viewMode === 'grid' || parsed.viewMode === 'list' ? parsed.viewMode : 'grid';
    const gridSize =
      parsed.gridSize === 'small' || parsed.gridSize === 'medium' || parsed.gridSize === 'large'
        ? parsed.gridSize
        : 'medium';
    return { viewMode, gridSize };
  } catch {
    return { viewMode: 'grid', gridSize: 'medium' };
  }
}

function App(): JSX.Element {
  // --- Auth state ---
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [confirmCode, setConfirmCode] = useState<string>('');
  const [authMode, setAuthMode] = useState<AuthMode>('login');
  const [pendingEmail, setPendingEmail] = useState<string>('');

  // --- Drive state ---
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const [viewMode, setViewMode] = useState<ViewMode>(() => readViewPrefs().viewMode);
  const [gridSize, setGridSize] = useState<GridSize>(() => readViewPrefs().gridSize);
  const [currentPath, setCurrentPath] = useState('');
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  // --- Selection state ---
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());

  // --- Context menu state ---
  const [ctxTarget, setCtxTarget] = useState<ContextMenuTarget>(null);
  const [ctxPosition, setCtxPosition] = useState<ContextMenuPosition | null>(null);

  // --- Rename dialog state ---
  const [renameTarget, setRenameTarget] = useState<RenameTarget>(null);

  // --- Move dialog state ---
  const [moveItems, setMoveItems] = useState<MoveItem[]>([]);
  const [moveDialogOpen, setMoveDialogOpen] = useState(false);

  // =========================================================================
  // Bootstrap & effects
  // =========================================================================

  useEffect(() => {
    const bootstrap = async (): Promise<void> => {
      const existingToken = await getToken();
      if (existingToken) {
        setToken(existingToken);
      }
    };

    void bootstrap();
  }, []);

  useEffect(() => {
    if (!token) return;
    void loadFiles();
  }, [token, currentPath]);

  useEffect(() => {
    localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify({ viewMode, gridSize }));
  }, [viewMode, gridSize]);

  // Clear selection when navigating
  useEffect(() => {
    setSelectedItems(new Set());
  }, [currentPath]);

  // =========================================================================
  // Core data helpers
  // =========================================================================

  const loadFiles = async (): Promise<void> => {
    setLoading(true);
    setError('');
    const result = await fetchFiles(currentPath || undefined);
    setFiles(result.files);
    setFolders(result.folders);
    if (result.error) setError(result.error);
    setLoading(false);
  };

  // =========================================================================
  // Auth handlers
  // =========================================================================

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

  // =========================================================================
  // Upload
  // =========================================================================

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
        await uploadFile(current, currentPath || undefined);
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

  // =========================================================================
  // Folder create
  // =========================================================================

  const handleCreateFolderOpen = (): void => {
    setNewFolderName('');
    setCreateFolderOpen(true);
  };

  const handleCreateFolderClose = (): void => {
    setCreateFolderOpen(false);
  };

  const handleCreateFolderSubmit = async (): Promise<void> => {
    const name = newFolderName.trim();
    if (!name) {
      setError('Folder name is required');
      return;
    }
    setError('');
    try {
      const result = await createFolder(name, currentPath || undefined);
      if (result.error) {
        setError(result.error);
        return;
      }
      handleCreateFolderClose();
      await loadFiles();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create folder';
      setError(message);
    }
  };

  // =========================================================================
  // Download & Delete
  // =========================================================================

  async function handleDownload(file: DriveFile): Promise<void> {
    const url = await getFileDownloadUrl(file.fileId);
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    } else {
      setError('Download failed');
    }
  }

  async function handleDelete(file: DriveFile): Promise<void> {
    if (!window.confirm(`Delete "${file.filename}"?`)) {
      return;
    }
    setLoading(true);
    setError('');
    const result = await deleteFileResult(file.fileId);
    if (result.success) {
      setFiles((current) => current.filter((entry) => entry.fileId !== file.fileId));
      setSelectedItems((prev) => {
        const next = new Set(prev);
        next.delete(file.fileId);
        return next;
      });
    } else {
      setError(result.error ?? 'Delete failed');
    }
    setLoading(false);
  }

  async function handleDeleteFolder(folder: DriveFolder): Promise<void> {
    if (!window.confirm(`Delete folder "${folder.name}"? This cannot be undone.`)) {
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await deleteFolder(folder.path);
      if (!result.error) {
        setFolders((current) => current.filter((f) => f.folderId !== folder.folderId));
        setSelectedItems((prev) => {
          const next = new Set(prev);
          next.delete(folder.folderId);
          return next;
        });
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete folder');
    }
    setLoading(false);
  }

  // =========================================================================
  // Context menu
  // =========================================================================

  const handleContextMenu = useCallback(
    (
      e: React.MouseEvent,
      target: { type: 'file'; file: DriveFile } | { type: 'folder'; folder: DriveFolder }
    ) => {
      // If the right-clicked item isn't in selection, select only it
      const id = target.type === 'file' ? target.file.fileId : target.folder.folderId;
      if (!selectedItems.has(id)) {
        setSelectedItems(new Set([id]));
      }
      setCtxTarget(target);
      setCtxPosition({ mouseX: e.clientX, mouseY: e.clientY });
    },
    [selectedItems]
  );

  const handleCtxClose = (): void => {
    setCtxTarget(null);
    setCtxPosition(null);
  };

  const handleCtxRename = (): void => {
    if (!ctxTarget) return;
    setRenameTarget(ctxTarget);
  };

  const handleCtxMoveTo = (): void => {
    // Build MoveItem list from selected items (or context-clicked item)
    const items: MoveItem[] = [];

    if (selectedItems.size > 1) {
      // Bulk move
      Array.from(selectedItems).forEach((id) => {
        const file = files.find((f) => f.fileId === id);
        if (file) {
          items.push({ type: 'file', id: file.fileId, name: file.filename });
          return;
        }
        const folder = folders.find((f) => f.folderId === id);
        if (folder) {
          items.push({ type: 'folder', id: folder.folderId, path: folder.path, name: folder.name });
        }
      });
    } else if (ctxTarget) {
      if (ctxTarget.type === 'file') {
        items.push({ type: 'file', id: ctxTarget.file.fileId, name: ctxTarget.file.filename });
      } else {
        items.push({
          type: 'folder',
          id: ctxTarget.folder.folderId,
          path: ctxTarget.folder.path,
          name: ctxTarget.folder.name
        });
      }
    }

    if (items.length > 0) {
      setMoveItems(items);
      setMoveDialogOpen(true);
    }
  };

  const handleCtxDownload = (): void => {
    if (ctxTarget?.type === 'file') {
      void handleDownload(ctxTarget.file);
    }
  };

  const handleCtxDelete = (): void => {
    if (selectedItems.size > 1) {
      // Bulk delete
      if (!window.confirm(`Delete ${selectedItems.size} selected items?`)) return;
      void handleBulkDelete();
    } else if (ctxTarget?.type === 'file') {
      void handleDelete(ctxTarget.file);
    } else if (ctxTarget?.type === 'folder') {
      void handleDeleteFolder(ctxTarget.folder);
    }
  };

  async function handleBulkDelete(): Promise<void> {
    setLoading(true);
    setError('');
    let failCount = 0;
    const ids = Array.from(selectedItems);
    for (let i = 0; i < ids.length; i += 1) {
      const id = ids[i];
      const file = files.find((f) => f.fileId === id);
      if (file) {
        const r = await deleteFileResult(file.fileId);
        if (!r.success) failCount += 1;
        continue;
      }
      const folder = folders.find((f) => f.folderId === id);
      if (folder) {
        try {
          const r = await deleteFolder(folder.path);
          if (r.error) failCount += 1;
        } catch {
          failCount += 1;
        }
      }
    }
    if (failCount > 0) {
      setError(`${failCount} item(s) failed to delete`);
    }
    setSelectedItems(new Set());
    await loadFiles();
    setLoading(false);
  }

  // =========================================================================
  // Rename
  // =========================================================================

  const handleRenameSubmit = async (newName: string): Promise<void> => {
    if (!renameTarget) return;
    setLoading(true);
    setError('');

    let result;
    if (renameTarget.type === 'file') {
      result = await renameFileResult(renameTarget.file.fileId, newName);
    } else {
      result = await renameFolderResult(renameTarget.folder.path, newName);
    }

    if (!result.success) {
      setError(result.error ?? 'Rename failed');
    }

    setRenameTarget(null);
    await loadFiles();
    setLoading(false);
  };

  // =========================================================================
  // Move
  // =========================================================================

  const handleMoveConfirm = async (destinationPath: string): Promise<void> => {
    setMoveDialogOpen(false);
    setLoading(true);
    setError('');

    let failCount = 0;
    for (const item of moveItems) {
      let result;
      if (item.type === 'file') {
        result = await moveFileResult(item.id, destinationPath);
      } else {
        result = await moveFolderResult(item.path ?? '', destinationPath);
      }
      if (!result.success) failCount += 1;
    }

    if (failCount > 0) {
      setError(`${failCount} item(s) failed to move`);
    }

    setMoveItems([]);
    setSelectedItems(new Set());
    await loadFiles();
    setLoading(false);
  };

  // =========================================================================
  // Drag-and-drop
  // =========================================================================

  const handleDrop = useCallback(
    async (
      targetFolder: DriveFolder,
      dragData: { type: 'file' | 'folder'; id: string }
    ): Promise<void> => {
      setLoading(true);
      setError('');

      // If multiple items are selected and the dragged item is among them, move all
      const idsToMove: Array<{ type: 'file' | 'folder'; id: string; path?: string }> = [];
      if (selectedItems.has(dragData.id) && selectedItems.size > 1) {
        Array.from(selectedItems).forEach((id) => {
          const file = files.find((f) => f.fileId === id);
          if (file) {
            idsToMove.push({ type: 'file', id });
            return;
          }
          const folder = folders.find((f) => f.folderId === id);
          if (folder) {
            idsToMove.push({ type: 'folder', id, path: folder.path });
          }
        });
      } else {
        if (dragData.type === 'folder') {
          const folder = folders.find((f) => f.folderId === dragData.id);
          idsToMove.push({ type: 'folder', id: dragData.id, path: folder?.path });
        } else {
          idsToMove.push({ type: 'file', id: dragData.id });
        }
      }

      let failCount = 0;
      for (const item of idsToMove) {
        let result;
        if (item.type === 'file') {
          result = await moveFileResult(item.id, targetFolder.path);
        } else {
          result = await moveFolderResult(item.path ?? '', targetFolder.path);
        }
        if (!result.success) failCount += 1;
      }

      if (failCount > 0) {
        setError(`${failCount} item(s) failed to move`);
      }

      setSelectedItems(new Set());
      await loadFiles();
      setLoading(false);
    },
    [selectedItems, files, folders]
  );

  // =========================================================================
  // Selection
  // =========================================================================

  const handleGridSelectionChange = useCallback(
    (id: string, multi: boolean) => {
      setSelectedItems((prev) => {
        const next = new Set(prev);
        if (multi) {
          if (next.has(id)) {
            next.delete(id);
          } else {
            next.add(id);
          }
        } else {
          if (next.has(id) && next.size === 1) {
            next.clear();
          } else {
            return new Set([id]);
          }
        }
        return next;
      });
    },
    []
  );

  const handleListSelectionChange = useCallback(
    (ids: string[]) => {
      setSelectedItems(new Set(ids));
    },
    []
  );

  // =========================================================================
  // Computed values
  // =========================================================================

  const rows: FileGridRow[] = files.map((file) => file.toGridRow());
  const columns = FileColumnsFactory.create({
    onDownload: handleDownload,
    onDelete: handleDelete
  });

  const listRows: DriveListRow[] = React.useMemo(() => {
    const folderRows: DriveListRow[] = folders.map((f) => ({
      id: f.folderId,
      type: 'folder' as const,
      folder: f
    }));
    const fileRows: DriveListRow[] = files.map((f) => ({
      id: f.fileId,
      type: 'file' as const,
      file: f
    }));
    const combined = [...folderRows, ...fileRows];
    combined.sort((a, b) => {
      const nameA = a.type === 'folder' ? a.folder.name : a.file.filename;
      const nameB = b.type === 'folder' ? b.folder.name : b.file.filename;
      return nameA.localeCompare(nameB, undefined, { sensitivity: 'base' });
    });
    return combined;
  }, [folders, files]);

  const listColumns = React.useMemo(
    () =>
      ListColumnsFactory.create({
        onDownload: handleDownload,
        onDelete: handleDelete,
        onFolderClick: (folder) => setCurrentPath(folder.path),
        onDeleteFolder: handleDeleteFolder
      }),
    []
  );

  // =========================================================================
  // Render
  // =========================================================================

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
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="center" flexWrap="wrap">
          <Button
            component="label"
            variant="contained"
            startIcon={<CloudUploadRoundedIcon />}
            disabled={loading}
          >
            Upload Files
            <input type="file" hidden multiple onChange={handleUpload} />
          </Button>
          <Button
            variant="outlined"
            startIcon={<CreateNewFolderRoundedIcon />}
            onClick={handleCreateFolderOpen}
            disabled={loading}
          >
            New folder
          </Button>
          <Typography variant="body2" color="text.secondary" sx={{ width: { xs: '100%', sm: 'auto' } }}>
            Upload multiple files in a single batch.
          </Typography>
        </Stack>
      </Paper>

      <Dialog open={createFolderOpen} onClose={handleCreateFolderClose} maxWidth="xs" fullWidth>
        <DialogTitle>New folder</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Create in: {currentPath || '/'}
            </Typography>
            <TextField
              autoFocus
              label="Folder name"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="e.g. Documents"
              fullWidth
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCreateFolderClose}>Cancel</Button>
          <Button onClick={handleCreateFolderSubmit} variant="contained">
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {error && <Alert severity="error">{error}</Alert>}
      {uploadProgress && <Alert severity="info">{uploadProgress}</Alert>}

      <Paper elevation={1} sx={{ borderRadius: 3, p: 1.5 }}>
        {currentPath ? (
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Button
              size="small"
              onClick={() => setCurrentPath(currentPath.replace(/\/[^/]+$/, '') || '')}
            >
              ↑ Up
            </Button>
            <Typography variant="body2" color="text.secondary">
              {currentPath}
            </Typography>
          </Stack>
        ) : null}
        <Stack direction="row" justifyContent="flex-end" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={(_, next) => next != null && setViewMode(next)}
            size="small"
            aria-label="View mode"
          >
            <ToggleButton value="grid" aria-label="Grid view">
              <GridViewRoundedIcon fontSize="small" />
            </ToggleButton>
            <ToggleButton value="list" aria-label="List view">
              <ViewListRoundedIcon fontSize="small" />
            </ToggleButton>
          </ToggleButtonGroup>
          {viewMode === 'grid' && (
            <ToggleButtonGroup
              value={gridSize}
              exclusive
              onChange={(_, next) => next != null && setGridSize(next)}
              size="small"
              aria-label="Grid size"
            >
              <ToggleButton value="small" aria-label="Small grid">
                <GridViewRoundedIcon sx={{ fontSize: 18 }} />
              </ToggleButton>
              <ToggleButton value="medium" aria-label="Medium grid">
                <GridViewRoundedIcon sx={{ fontSize: 24 }} />
              </ToggleButton>
              <ToggleButton value="large" aria-label="Large grid">
                <GridViewRoundedIcon sx={{ fontSize: 30 }} />
              </ToggleButton>
            </ToggleButtonGroup>
          )}
        </Stack>
        {viewMode === 'grid' ? (
          <GridLayout
            files={files}
            folders={folders}
            loading={loading}
            selectedItems={selectedItems}
            onDownload={handleDownload}
            onDelete={handleDelete}
            onFolderClick={(folder) => setCurrentPath(folder.path)}
            onDeleteFolder={handleDeleteFolder}
            onContextMenu={handleContextMenu}
            onSelectionChange={handleGridSelectionChange}
            onDrop={handleDrop}
            getDownloadUrl={getFileDownloadUrl}
            gridSize={gridSize}
          />
        ) : (
          <ListLayout
            rows={listRows}
            columns={listColumns}
            loading={loading}
            selectedItems={selectedItems}
            onFolderClick={(folder) => setCurrentPath(folder.path)}
            onContextMenu={handleContextMenu}
            onSelectionChange={handleListSelectionChange}
          />
        )}
      </Paper>

      {/* Context menu */}
      <ContextMenu
        target={ctxTarget}
        position={ctxPosition}
        selectedCount={selectedItems.size}
        onClose={handleCtxClose}
        onRename={handleCtxRename}
        onMoveTo={handleCtxMoveTo}
        onDownload={handleCtxDownload}
        onDelete={handleCtxDelete}
      />

      {/* Rename dialog */}
      <RenameDialog
        target={renameTarget}
        onClose={() => setRenameTarget(null)}
        onSubmit={handleRenameSubmit}
      />

      {/* Move dialog */}
      <MoveDialog
        open={moveDialogOpen}
        items={moveItems}
        onClose={() => {
          setMoveDialogOpen(false);
          setMoveItems([]);
        }}
        onConfirm={handleMoveConfirm}
      />
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
