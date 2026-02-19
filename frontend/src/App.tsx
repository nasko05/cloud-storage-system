import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  CssBaseline,
  Divider,
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
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import GridViewRoundedIcon from '@mui/icons-material/GridViewRounded';
import ViewListRoundedIcon from '@mui/icons-material/ViewListRounded';
import ExpandMoreRoundedIcon from '@mui/icons-material/ExpandMoreRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import FolderSharedRoundedIcon from '@mui/icons-material/FolderSharedRounded';
import FolderRoundedIcon from '@mui/icons-material/FolderRounded';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import { logout, getToken } from './auth';
import { createFolder } from './api';
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
import type {
  DriveFile,
  DriveListRow,
  FileGridRow,
  ContextMenuTarget,
  ContextMenuPosition,
  RenameTarget,
  MoveItem,
  ShareTarget,
  SharePermission,
  SharedFile
} from './types/drive';
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
import { UploadControlsPanel } from './components/UploadControlsPanel';
import { UploadProgressPanel } from './components/UploadProgressPanel';
import { QuickAccessPanel } from './components/QuickAccessPanel';
import { UploadDropOverlay } from './components/UploadDropOverlay';
import { useSelection } from './hooks/useSelection';
import { useDriveActions } from './hooks/useDriveActions';
import { useUploadManager } from './hooks/useUploadManager';
import { useFileAccessHistory, type FileAccessRecord } from './hooks/useFileAccessHistory';
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

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  return (
    tagName === 'input' ||
    tagName === 'textarea' ||
    tagName === 'select' ||
    target.isContentEditable
  );
}

function getParentPath(path: string): string {
  const slashIndex = path.lastIndexOf('/');
  return slashIndex === -1 ? '' : path.slice(0, slashIndex);
}

function sortFoldersByName(values: DriveFolder[]): DriveFolder[] {
  return [...values].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  );
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
  const [folderTreeByPath, setFolderTreeByPath] = useState<Record<string, DriveFolder[]>>({});
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set(['']));

  const {
    recentFiles,
    recordFileAccess,
    removeFileAccess
  } = useFileAccessHistory();

  // --- Selection ---
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
    setFolderTreeByPath((prev) => ({
      ...prev,
      [currentPath]: sortFoldersByName(result.folders)
    }));
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

  const {
    fileUploadInputRef,
    uploadItems,
    uploadStats,
    isUploading,
    uploadSummary,
    isUploadDragActive,
    setUploadSummary,
    openFilePicker,
    handleUploadFiles,
    uploadFromDataTransfer,
    handleCancelUpload
  } = useUploadManager({
    currentPath,
    enabled: !!token,
    setError,
    loadFiles
  });

  // --- Drive actions ---
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
    loadFiles,
    onFileAccess: recordFileAccess
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

  useEffect(() => {
    if (!token) return;
    void loadFiles();
  }, [token, currentPath]);

  useEffect(() => {
    if (!token || driveTab !== 'shared-with-me') return;
    void loadSharedFiles();
  }, [token, driveTab]);

  useEffect(() => {
    localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify({ viewMode, gridSize }));
  }, [viewMode, gridSize]);

  useEffect(() => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      next.add('');
      if (!currentPath) return next;
      const parts = currentPath.split('/').filter(Boolean);
      let acc = '';
      parts.forEach((part) => {
        acc = acc ? `${acc}/${part}` : part;
        next.add(acc);
      });
      return next;
    });
  }, [currentPath]);

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
    setFolderTreeByPath({});
    setExpandedFolders(new Set(['']));
    setCurrentPath('');
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
    const items: MoveItem[] = [];

    if (selectedItems.size > 1) {
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
      if (!window.confirm(`Delete ${selectedItems.size} selected items?`)) return;
      void handleBulkDelete();
    } else if (ctxTarget?.type === 'file') {
      void handleDelete(ctxTarget.file);
    } else if (ctxTarget?.type === 'folder') {
      void handleDeleteFolder(ctxTarget.folder);
    }
  };

  useEffect(() => {
    if (!token || driveTab !== 'my-drive') return;

    const handleShortcuts = (event: KeyboardEvent): void => {
      if (isEditableTarget(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const key = event.key.toLowerCase();

      if (key === 'u') {
        event.preventDefault();
        openFilePicker();
        return;
      }

      if (key === 'n') {
        event.preventDefault();
        handleCreateFolderOpen();
        return;
      }

      if (key === 'r') {
        event.preventDefault();
        void loadFiles();
        return;
      }

      if (event.key === 'Escape') {
        if (isUploading) {
          handleCancelUpload();
        } else {
          handleCtxClose();
          setSelectedItems(new Set());
        }
      }
    };

    window.addEventListener('keydown', handleShortcuts);
    return (): void => {
      window.removeEventListener('keydown', handleShortcuts);
    };
  }, [currentPath, driveTab, isUploading, token]);

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
      await loadFiles(false);
    }

    setLoading(false);
  };

  const handleShareChanged = (): void => {
    void loadFiles(false);
  };

  // =========================================================================
  // Computed values
  // =========================================================================

  const handleQuickAccessDownload = async (record: FileAccessRecord): Promise<void> => {
    await handleDownload({
      fileId: record.fileId,
      filename: record.filename,
      size: 0,
      createdAt: ''
    } as DriveFile);
  };

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

  const currentFolderParent = useMemo(() => getParentPath(currentPath), [currentPath]);

  const handleFolderSelection = useCallback((path: string): void => {
    setDriveTab('my-drive');
    setCurrentPath(path);
  }, []);

  const handleFolderExpandToggle = useCallback((path: string): void => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const renderFolderTree = useCallback(
    (parentPath: string, depth = 0): React.ReactNode => {
      const childFolders = folderTreeByPath[parentPath] ?? [];
      if (!childFolders.length) {
        if (depth === 0) {
          return (
            <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 1.5 }}>
              {loading ? 'Loading folders...' : 'No folders yet'}
            </Typography>
          );
        }
        return null;
      }

      return childFolders.map((folder) => {
        const knownChildren = folderTreeByPath[folder.path] ?? [];
        const hasKnownChildren = knownChildren.length > 0;
        const isExpanded = expandedFolders.has(folder.path);
        const isCurrent = currentPath === folder.path;

        return (
          <Box key={folder.folderId}>
            <Stack direction="row" alignItems="center" spacing={0.5} sx={{ pl: 1 + depth * 2 }}>
              {hasKnownChildren ? (
                <Button
                  size="small"
                  onClick={(event) => {
                    event.stopPropagation();
                    handleFolderExpandToggle(folder.path);
                  }}
                  sx={{
                    minWidth: 26,
                    width: 26,
                    height: 26,
                    p: 0,
                    borderRadius: 0
                  }}
                  aria-label={isExpanded ? 'Collapse folder' : 'Expand folder'}
                >
                  {isExpanded ? (
                    <ExpandMoreRoundedIcon sx={{ fontSize: 18 }} />
                  ) : (
                    <ChevronRightRoundedIcon sx={{ fontSize: 18 }} />
                  )}
                </Button>
              ) : (
                <Box sx={{ width: 26, height: 26 }} />
              )}
              <Button
                fullWidth
                size="small"
                onClick={() => {
                  handleFolderSelection(folder.path);
                  setExpandedFolders((prev) => new Set(prev).add(folder.path));
                }}
                startIcon={<FolderRoundedIcon sx={{ fontSize: 19, color: 'warning.dark' }} />}
                sx={{
                  justifyContent: 'flex-start',
                  textTransform: 'none',
                  py: 0.5,
                  px: 1,
                  borderRadius: 0,
                  color: 'text.primary',
                  backgroundColor: isCurrent ? 'action.selected' : 'transparent',
                  '&:hover': {
                    backgroundColor: isCurrent ? 'action.selected' : 'action.hover'
                  }
                }}
              >
                <Typography noWrap variant="body2" fontWeight={isCurrent ? 600 : 500}>
                  {folder.name}
                </Typography>
              </Button>
            </Stack>
            {isExpanded ? renderFolderTree(folder.path, depth + 1) : null}
          </Box>
        );
      });
    },
    [
      currentPath,
      expandedFolders,
      folderTreeByPath,
      handleFolderExpandToggle,
      handleFolderSelection,
      loading
    ]
  );

  // =========================================================================
  // Render
  // =========================================================================

  if (!token) {
    return (
      <>
        <CssBaseline />
        <Box
          sx={{
            minHeight: '100vh',
            px: { xs: 2, sm: 3 },
            py: 3,
            display: 'grid',
            placeItems: 'center'
          }}
        >
          <Box sx={{ width: '100%', maxWidth: 720 }}>
            <AuthForm onAuthenticated={handleAuthenticated} />
          </Box>
        </Box>
      </>
    );
  }

  return (
    <>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          gap: 0
        }}
      >
        <Paper
          elevation={0}
          sx={{
            borderRadius: 0,
            overflow: 'hidden',
            borderBottom: 1,
            borderColor: 'divider'
          }}
        >
          <Toolbar
            variant="dense"
            sx={{
              minHeight: { xs: 50, sm: 54 },
              px: { xs: 1.75, sm: 2.5 },
              justifyContent: 'space-between'
            }}
          >
            <Typography variant="h6" fontWeight={700}>
              Personal Drive
            </Typography>
            <Button
              color="inherit"
              variant="outlined"
              size="small"
              onClick={handleLogout}
              startIcon={<LogoutRoundedIcon />}
            >
              Logout
            </Button>
          </Toolbar>
        </Paper>

        <Box
          sx={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            gap: 1,
            px: { xs: 0.5, sm: 1, md: 1.25 },
            py: { xs: 0.5, sm: 0.75 }
          }}
        >
          <Paper
            elevation={0}
            sx={{
              borderRadius: 0,
              border: 1,
              borderColor: 'divider',
              width: { xs: '100%', md: 320 },
              flexShrink: 0,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              maxHeight: { md: 'calc(100vh - 120px)' }
            }}
          >
            <Tabs
              value={driveTab}
              onChange={(_, v) => setDriveTab(v as DriveTab)}
              variant="fullWidth"
              sx={{ px: 0 }}
            >
              <Tab
                icon={<FolderRoundedIcon />}
                iconPosition="start"
                label="My files"
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
            <Divider />
            {driveTab === 'my-drive' ? (
              <Stack spacing={0.75} sx={{ p: 0.75, flex: 1, minHeight: 0 }}>
                <Typography variant="caption" color="text.secondary" sx={{ px: 1, pt: 0.5 }}>
                  Folder tree
                </Typography>
                <Button
                  fullWidth
                  size="small"
                  onClick={() => handleFolderSelection('')}
                  startIcon={<FolderRoundedIcon sx={{ fontSize: 19, color: 'warning.dark' }} />}
                  sx={{
                    justifyContent: 'flex-start',
                    textTransform: 'none',
                    py: 0.5,
                    px: 1,
                    borderRadius: 0,
                    color: 'text.primary',
                    backgroundColor: currentPath === '' ? 'action.selected' : 'transparent',
                    '&:hover': {
                      backgroundColor: currentPath === '' ? 'action.selected' : 'action.hover'
                    }
                  }}
                >
                  <Typography noWrap variant="body2" fontWeight={currentPath === '' ? 600 : 500}>
                    Root
                  </Typography>
                </Button>
                <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto', pr: 0.5 }}>
                  {renderFolderTree('', 0)}
                </Box>
              </Stack>
            ) : (
              <Stack
                spacing={1}
                sx={{
                  p: 1,
                  flex: 1,
                  alignItems: 'center',
                  justifyContent: 'center',
                  textAlign: 'center'
                }}
              >
                <FolderSharedRoundedIcon sx={{ color: 'text.disabled', fontSize: 38 }} />
                <Typography variant="body2" color="text.secondary">
                  Shared files are shown in the center panel.
                </Typography>
              </Stack>
            )}
          </Paper>

          <Stack spacing={1} sx={{ flex: 1, minWidth: 0, minHeight: 0 }}>
            {error && <Alert severity="error">{error}</Alert>}
            {uploadSummary && (
              <Alert severity="info" onClose={() => setUploadSummary('')}>
                {uploadSummary}
              </Alert>
            )}

            {driveTab === 'my-drive' && (
              <UploadControlsPanel
                fileUploadInputRef={fileUploadInputRef}
                loading={loading}
                isUploading={isUploading}
                onUploadFilesChange={handleUploadFiles}
                onOpenFilePicker={openFilePicker}
                onCreateFolder={handleCreateFolderOpen}
                onCancelUpload={handleCancelUpload}
              />
            )}

            <UploadProgressPanel
              uploadItems={uploadItems}
              uploadStats={uploadStats}
              isUploading={isUploading}
              onCancelUpload={handleCancelUpload}
            />

            {driveTab === 'my-drive' && (
              <QuickAccessPanel
                recentFiles={recentFiles}
                onOpenFile={(record) => {
                  void handleQuickAccessDownload(record);
                }}
                onRemoveFile={(record) => {
                  removeFileAccess(record.fileId);
                }}
              />
            )}

            {driveTab === 'my-drive' ? (
              <Paper
                key="my-drive"
                elevation={0}
                sx={{
                  borderRadius: 0,
                  border: 1,
                  borderColor: 'divider',
                  p: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                  flex: 1
                }}
              >
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                  spacing={1}
                  sx={{ mb: 1.25 }}
                >
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                    <Typography variant="body2" color="text.secondary">
                      Path:
                    </Typography>
                    <Button
                      size="small"
                      onClick={() => handleFolderSelection(currentFolderParent)}
                      disabled={!currentPath}
                    >
                      Up
                    </Button>
                    <Typography variant="body2" color="text.secondary" noWrap>
                      {currentPath || '/'}
                    </Typography>
                  </Stack>
                  <Stack direction="row" justifyContent="flex-end" alignItems="center" spacing={1}>
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
                </Stack>
                <Box sx={{ flex: 1, minHeight: { xs: 320, md: 0 }, overflowY: 'auto', pr: 0.25 }}>
                  {viewMode === 'grid' ? (
                    <GridLayout
                      files={files}
                      folders={folders}
                      loading={loading}
                      selectedItems={selectedItems}
                      onDownload={handleDownload}
                      onDelete={handleDelete}
                      onFolderClick={(folder) => handleFolderSelection(folder.path)}
                      onDownloadFolder={handleDownloadFolder}
                      onDeleteFolder={handleDeleteFolder}
                      onContextMenu={handleContextMenu}
                      onSelectionChange={handleGridSelectionChange}
                      onDrop={handleDrop}
                      onExternalDropUpload={(folder, dataTransfer) => {
                        void uploadFromDataTransfer(dataTransfer, folder.path);
                      }}
                      getDownloadUrl={getFileDownloadUrl}
                      gridSize={gridSize}
                    />
                  ) : (
                    <ListLayout
                      rows={listRows}
                      columns={listColumns}
                      loading={loading}
                      selectedItems={selectedItems}
                      onFolderClick={(folder) => handleFolderSelection(folder.path)}
                      onContextMenu={handleContextMenu}
                      onSelectionChange={handleListSelectionChange}
                    />
                  )}
                </Box>
              </Paper>
            ) : (
              <Paper
                key="shared-with-me"
                elevation={0}
                sx={{
                  borderRadius: 0,
                  border: 1,
                  borderColor: 'divider',
                  p: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                  flex: 1
                }}
              >
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
                  <Box sx={{ flex: 1, minHeight: { xs: 320, md: 0 }, overflowY: 'auto', pr: 0.25 }}>
                    <List disablePadding>
                      {sharedFiles.map((sf) => (
                        <ListItem
                          key={sf.fileId}
                          secondaryAction={
                            sf.permission === 'download' || sf.permission === 'edit' ? (
                              <Tooltip title="Download">
                                <Button
                                  size="small"
                                  onClick={() =>
                                    void handleDownload({
                                      fileId: sf.fileId,
                                      filename: sf.filename,
                                      size: 0,
                                      createdAt: ''
                                    } as DriveFile)
                                  }
                                >
                                  <DownloadRoundedIcon fontSize="small" />
                                </Button>
                              </Tooltip>
                            ) : null
                          }
                          sx={{
                            borderBottom: '1px solid',
                            borderColor: 'divider',
                            '&:last-child': { borderBottom: 'none' }
                          }}
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
                  </Box>
                )}
              </Paper>
            )}
          </Stack>
        </Box>

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

          <RenameDialog
            target={renameTarget}
            onClose={() => setRenameTarget(null)}
            onSubmit={handleRenameSubmit}
          />

          <MoveDialog
            open={moveDialogOpen}
            items={moveItems}
            onClose={() => {
              setMoveDialogOpen(false);
              setMoveItems([]);
            }}
            onConfirm={handleMoveConfirm}
          />

          <ShareDialog
            target={shareTarget}
            onClose={() => setShareTarget(null)}
            onSubmit={handleShareSubmit}
            onShareChanged={handleShareChanged}
          />

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
      </Box>
      <UploadDropOverlay visible={driveTab === 'my-drive' && isUploadDragActive} />
    </>
  );
}

export default App;
