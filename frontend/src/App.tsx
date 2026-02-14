import React, { ChangeEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  CssBaseline,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Snackbar,
  Stack,
  Tab,
  Tabs,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Toolbar,
  Tooltip,
  Typography
} from '@mui/material';
import CreateNewFolderRoundedIcon from '@mui/icons-material/CreateNewFolderRounded';
import GridViewRoundedIcon from '@mui/icons-material/GridViewRounded';
import ViewListRoundedIcon from '@mui/icons-material/ViewListRounded';
import CloudUploadRoundedIcon from '@mui/icons-material/CloudUploadRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import FolderSharedRoundedIcon from '@mui/icons-material/FolderSharedRounded';
import FolderRoundedIcon from '@mui/icons-material/FolderRounded';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import { logout, getToken } from './auth';
import { createFolder, uploadFile } from './api';
import {
  fetchFiles,
  fetchSharedWithMe,
  getFileDownloadUrl,
  moveFileResult,
  moveFolderResult,
  renameFileResult,
  renameFolderResult,
  shareFileResult
} from './service/driveService';
import type { DriveFolder } from './components/Folder';
import type { DriveFile, DriveListRow, FileGridRow, ContextMenuTarget, ContextMenuPosition, RenameTarget, MoveItem, ShareTarget, SharePermission, SharedFile } from './types/drive';
import { toFileGridRow } from './types/drive';
import { FileColumnsFactory, ListColumnsFactory } from './components/FileColumns';
import { GridLayout, type GridSize } from './components/GridLayout';
import { ListLayout } from './components/ListLayout';
import { ContextMenu } from './components/ContextMenu';
import { RenameDialog } from './components/RenameDialog';
import { MoveDialog } from './components/MoveDialog';
import { ShareDialog } from './components/ShareDialog';
import { PublicDownloadPage } from './components/PublicDownloadPage';
import { AuthForm } from './components/AuthForm';
import { useSelection } from './hooks/useSelection';
import { useDriveActions } from './hooks/useDriveActions';
import './App.css';

type ViewMode = 'grid' | 'list';
type DriveTab = 'my-drive' | 'shared-with-me';

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
  // --- Public link route: /s/{token} (no auth required) ---
  const publicLinkMatch = window.location.pathname.match(/^\/s\/([a-f0-9-]+)$/i);
  if (publicLinkMatch) {
    return <PublicDownloadPage token={publicLinkMatch[1]} />;
  }

  // --- Auth state ---
  const [token, setToken] = useState<string | null>(null);

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

  // --- Context menu state ---
  const [ctxTarget, setCtxTarget] = useState<ContextMenuTarget>(null);
  const [ctxPosition, setCtxPosition] = useState<ContextMenuPosition | null>(null);

  // --- Rename dialog state ---
  const [renameTarget, setRenameTarget] = useState<RenameTarget>(null);

  // --- Move dialog state ---
  const [moveItems, setMoveItems] = useState<MoveItem[]>([]);
  const [moveDialogOpen, setMoveDialogOpen] = useState(false);

  // --- Share dialog state ---
  const [shareTarget, setShareTarget] = useState<ShareTarget>(null);
  const [shareSuccess, setShareSuccess] = useState('');

  // --- Shared with me state ---
  const [driveTab, setDriveTab] = useState<DriveTab>('my-drive');
  const [sharedFiles, setSharedFiles] = useState<SharedFile[]>([]);
  const [sharedLoading, setSharedLoading] = useState(false);

  // --- Selection (extracted hook) ---
  const {
    selectedItems,
    setSelectedItems,
    handleGridSelectionChange,
    handleListSelectionChange
  } = useSelection(currentPath);

  // =========================================================================
  // Core data helpers
  // =========================================================================

  const loadFiles = async (preserveError = false): Promise<void> => {
    setLoading(true);
    if (!preserveError) setError('');
    const result = await fetchFiles(currentPath || undefined);
    setFiles(result.files);
    setFolders(result.folders);
    if (result.error) setError(result.error);
    setLoading(false);
  };

  const loadSharedFiles = async (): Promise<void> => {
    setSharedLoading(true);
    setError('');
    const result = await fetchSharedWithMe();
    setSharedFiles(result.files);
    if (result.error) setError(result.error);
    setSharedLoading(false);
  };

  // --- Drive actions (extracted hook) ---
  const {
    handleDownload,
    handleDownloadFolder,
    handleBulkDownloadAsZip,
    handleDelete,
    handleDeleteFolder,
    handleBulkDelete,
    handleDrop
  } = useDriveActions({
    files,
    folders,
    selectedItems,
    setFiles,
    setFolders,
    setSelectedItems,
    setLoading,
    setError,
    loadFiles
  });

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

  // Load My Drive files (unchanged from original — always stays fresh)
  useEffect(() => {
    if (!token) return;
    void loadFiles();
  }, [token, currentPath]);

  // Load shared files only when that tab is active
  useEffect(() => {
    if (!token || driveTab !== 'shared-with-me') return;
    void loadSharedFiles();
  }, [token, driveTab]);

  useEffect(() => {
    localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify({ viewMode, gridSize }));
  }, [viewMode, gridSize]);

  // =========================================================================
  // Auth
  // =========================================================================

  const handleAuthenticated = (authToken: string): void => {
    setToken(authToken);
  };

  const handleLogout = (): void => {
    logout();
    setToken(null);
    setFiles([]);
    setFolders([]);
    setSharedFiles([]);
    setCurrentPath('');
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
    [selectedItems, setSelectedItems]
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
    if (selectedItems.size > 1) {
      void handleBulkDownloadAsZip();
    } else if (ctxTarget?.type === 'file') {
      void handleDownload(ctxTarget.file);
    }
  };

  const handleCtxShare = (): void => {
    if (ctxTarget?.type === 'file') {
      setShareTarget(ctxTarget);
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

    const hasError = !result.success;
    if (hasError) {
      setError(result.error ?? 'Rename failed');
    }

    setRenameTarget(null);
    await loadFiles(hasError);
    setLoading(false);
  };

  // =========================================================================
  // Move
  // =========================================================================

  const handleMoveConfirm = async (destinationPath: string): Promise<void> => {
    setMoveDialogOpen(false);
    setLoading(true);
    setError('');

    const errors: string[] = [];
    for (const item of moveItems) {
      let result;
      if (item.type === 'file') {
        result = await moveFileResult(item.id, destinationPath);
      } else {
        result = await moveFolderResult(item.path ?? '', destinationPath);
      }
      if (!result.success) {
        errors.push(result.error ?? `Failed to move "${item.name}"`);
      }
    }

    const hasErrors = errors.length > 0;
    if (hasErrors) {
      setError(errors.join('; '));
    }

    setMoveItems([]);
    setSelectedItems(new Set());
    await loadFiles(hasErrors);
    setLoading(false);
  };

  // =========================================================================
  // Share
  // =========================================================================

  const handleShareSubmit = async (params: {
    fileId: string;
    shareWithEmail: string;
    permission: SharePermission;
    expiryDays: number;
  }): Promise<void> => {
    setShareTarget(null);
    setLoading(true);
    setError('');

    const result = await shareFileResult(
      params.fileId,
      params.shareWithEmail,
      params.permission,
      params.expiryDays
    );

    if (!result.success) {
      setError(result.error ?? 'Share failed');
    } else {
      setShareSuccess(`Shared with ${params.shareWithEmail}`);
      // Refresh file list so isShared icon updates
      await loadFiles(false);
    }

    setLoading(false);
  };

  /** Called by ShareDialog when a share is revoked or permission updated. */
  const handleShareChanged = (): void => {
    void loadFiles(false);
  };

  // =========================================================================
  // Computed values
  // =========================================================================

  const rows: FileGridRow[] = useMemo(
    () => files.map((file) => toFileGridRow(file)),
    [files]
  );

  const columns = useMemo(
    () => FileColumnsFactory.create({
      onDownload: handleDownload,
      onDelete: handleDelete
    }),
    [handleDownload, handleDelete]
  );

  const listRows: DriveListRow[] = useMemo(() => {
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

  const listColumns = useMemo(
    () =>
      ListColumnsFactory.create({
        onDownload: handleDownload,
        onDelete: handleDelete,
        onFolderClick: (folder) => setCurrentPath(folder.path),
        onDownloadFolder: handleDownloadFolder,
        onDeleteFolder: handleDeleteFolder
      }),
    [handleDownload, handleDelete, handleDownloadFolder, handleDeleteFolder]
  );

  // =========================================================================
  // Render
  // =========================================================================

  if (!token) {
    return (
      <>
        <CssBaseline />
        <Container maxWidth="md">
          <AuthForm onAuthenticated={handleAuthenticated} />
        </Container>
      </>
    );
  }

  return (
    <>
      <CssBaseline />
      <Container maxWidth="md">
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

          <Paper elevation={1} sx={{ borderRadius: 3, overflow: 'hidden' }}>
            <Tabs
              value={driveTab}
              onChange={(_, v) => setDriveTab(v as DriveTab)}
              sx={{ px: 2 }}
            >
              <Tab
                icon={<FolderRoundedIcon />}
                iconPosition="start"
                label="My Drive"
                value="my-drive"
                sx={{ textTransform: 'none', minHeight: 48 }}
              />
              <Tab
                icon={<FolderSharedRoundedIcon />}
                iconPosition="start"
                label="Shared with me"
                value="shared-with-me"
                sx={{ textTransform: 'none', minHeight: 48 }}
              />
            </Tabs>
          </Paper>

          {driveTab === 'my-drive' && (
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
          )}

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

          {driveTab === 'my-drive' ? (
          <Paper key="my-drive" elevation={1} sx={{ borderRadius: 3, p: 1.5 }}>
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
                onDownloadFolder={handleDownloadFolder}
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
          ) : (
          <Paper key="shared-with-me" elevation={1} sx={{ borderRadius: 3, p: 2 }}>
            {sharedLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                <CircularProgress />
              </Box>
            ) : sharedFiles.length === 0 ? (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <FolderSharedRoundedIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                <Typography color="text.secondary">
                  No files have been shared with you yet.
                </Typography>
              </Box>
            ) : (
              <List disablePadding>
                {sharedFiles.map((sf) => (
                  <ListItem
                    key={sf.fileId}
                    secondaryAction={
                      (sf.permission === 'download' || sf.permission === 'edit') ? (
                        <Tooltip title="Download">
                          <Button
                            size="small"
                            onClick={() => void handleDownload({ fileId: sf.fileId, filename: sf.filename, size: 0, createdAt: '' } as DriveFile)}
                          >
                            <DownloadRoundedIcon fontSize="small" />
                          </Button>
                        </Tooltip>
                      ) : null
                    }
                    sx={{ borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { borderBottom: 'none' } }}
                  >
                    <ListItemIcon>
                      <InsertDriveFileRoundedIcon color="action" />
                    </ListItemIcon>
                    <ListItemText
                      primary={sf.filename}
                      secondary={
                        <Stack component="span" direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                          <Typography component="span" variant="caption" color="text.secondary">
                            From: {sf.sharedByEmail}
                          </Typography>
                          <Chip
                            label={sf.permission === 'read' ? 'View' : sf.permission === 'download' ? 'Download' : 'Edit'}
                            size="small"
                            variant="outlined"
                            sx={{ height: 20, fontSize: '0.7rem' }}
                          />
                          <Typography component="span" variant="caption" color="text.secondary">
                            Expires: {new Date(sf.expiresAt).toLocaleDateString()}
                          </Typography>
                        </Stack>
                      }
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </Paper>
          )}

          {/* Context menu */}
          <ContextMenu
            target={ctxTarget}
            position={ctxPosition}
            selectedCount={selectedItems.size}
            showDownload={
              (ctxTarget?.type === 'file' && selectedItems.size <= 1) ||
              selectedItems.size > 1
            }
            downloadLabel={
              selectedItems.size > 1
                ? `Download as ZIP (${selectedItems.size} items)`
                : 'Download'
            }
            onClose={handleCtxClose}
            onRename={handleCtxRename}
            onMoveTo={handleCtxMoveTo}
            onDownload={handleCtxDownload}
            onShare={handleCtxShare}
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

          {/* Share dialog */}
          <ShareDialog
            target={shareTarget}
            onClose={() => setShareTarget(null)}
            onSubmit={handleShareSubmit}
            onShareChanged={handleShareChanged}
          />

          {/* Share success notification */}
          <Snackbar
            open={!!shareSuccess}
            autoHideDuration={3000}
            onClose={() => setShareSuccess('')}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
          >
            <Alert
              onClose={() => setShareSuccess('')}
              severity="success"
              variant="filled"
              sx={{ width: '100%' }}
            >
              {shareSuccess}
            </Alert>
          </Snackbar>
        </Stack>
      </Container>
    </>
  );
}

export default App;
