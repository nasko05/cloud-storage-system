import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  CircularProgress,
  CssBaseline,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import GridViewRoundedIcon from '@mui/icons-material/GridViewRounded';
import ViewListRoundedIcon from '@mui/icons-material/ViewListRounded';
import ExpandMoreRoundedIcon from '@mui/icons-material/ExpandMoreRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import KeyRoundedIcon from '@mui/icons-material/KeyRounded';
import FolderSharedRoundedIcon from '@mui/icons-material/FolderSharedRounded';
import FolderRoundedIcon from '@mui/icons-material/FolderRounded';
import CloudRoundedIcon from '@mui/icons-material/CloudRounded';
import CloudUploadRoundedIcon from '@mui/icons-material/CloudUploadRounded';
import CreateNewFolderRoundedIcon from '@mui/icons-material/CreateNewFolderRounded';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import AutoStoriesRoundedIcon from '@mui/icons-material/AutoStoriesRounded';
import { logout, getToken, registerPasskey, passkeySupported } from './auth';
import { config } from './config';
import { createFolder, agentStatus } from './api';
import { Assistant } from './components/Assistant';
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
import type { DriveFolder } from './types/drive';
import type {
  DriveFile,
  DriveListRow,
  ContextMenuTarget,
  ContextMenuPosition,
  RenameTarget,
  MoveItem,
  ShareTarget,
  SharePermission,
  SharedFile
} from './types/drive';
import { ListColumnsFactory } from './components/FileColumns';
import { GridLayout, type GridSize } from './components/GridLayout';
import { ListLayout } from './components/ListLayout';
import { ContextMenu } from './components/ContextMenu';
import { PreviewModal } from './components/Preview/PreviewModal';
import { RenameDialog } from './components/RenameDialog';
import { MoveDialog } from './components/MoveDialog';
import { ShareDialog } from './components/ShareDialog';
import { PublicDownloadPage } from './components/PublicDownloadPage';
import { AuthForm } from './components/AuthForm';
import { UploadProgressPanel } from './components/UploadProgressPanel';
import { QuickAccessPanel } from './components/QuickAccessPanel';
import { UploadDropOverlay } from './components/UploadDropOverlay';
import { useSelection } from './hooks/useSelection';
import { useDriveActions } from './hooks/useDriveActions';
import { useUploadManager } from './hooks/useUploadManager';
import { useFileAccessHistory, type FileAccessRecord } from './hooks/useFileAccessHistory';
import './App.css';
import { partitionSelection } from './service/selection';
import SuccessToast from './components/SuccessToast';
import { formatDate } from './utils';

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

  // --- AI assistant availability (server is the source of truth) ---
  const [assistantConfigured, setAssistantConfigured] = useState(false);

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

  // --- Preview modal state ---
  const [previewFile, setPreviewFile] = useState<DriveFile | null>(null);

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
    if (!token) {
      setAssistantConfigured(false);
      return;
    }
    let active = true;
    void agentStatus()
      .then((status) => {
        if (active) setAssistantConfigured(status.configured);
      })
      .catch(() => {
        if (active) setAssistantConfigured(false);
      });
    return (): void => {
      active = false;
    };
  }, [token]);

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

  const handleAddPasskey = async (): Promise<void> => {
    if (!token) return;
    setError('');
    try {
      await registerPasskey(token);
      setShareSuccess('Passkey added. You can now sign in with it.');
    } catch (caughtError: unknown) {
      const message =
        caughtError instanceof Error ? caughtError.message : 'Could not add passkey';
      setError(message);
    }
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

  const handleCtxPreview = (): void => {
    if (ctxTarget?.type === 'file') {
      setPreviewFile(ctxTarget.file);
    }
  };

  const handleCtxRename = (): void => {
    if (!ctxTarget) return;
    setRenameTarget(ctxTarget);
  };

  const handleCtxMoveTo = (): void => {
    const items: MoveItem[] = [];

    if (selectedItems.size > 1) {
      const selection = partitionSelection(selectedItems, files, folders);
      for (const file of selection.files) {
        items.push({ type: 'file', id: file.fileId, name: file.filename });
      }
      for (const folder of selection.folders) {
        items.push({ type: 'folder', id: folder.folderId, path: folder.path, name: folder.name });
      }
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
                <IconButton
                  size="small"
                  onClick={(event) => {
                    event.stopPropagation();
                    handleFolderExpandToggle(folder.path);
                  }}
                  sx={{ width: 26, height: 26, p: 0, color: 'text.secondary' }}
                  aria-label={isExpanded ? 'Collapse folder' : 'Expand folder'}
                >
                  {isExpanded ? (
                    <ExpandMoreRoundedIcon sx={{ fontSize: 18 }} />
                  ) : (
                    <ChevronRightRoundedIcon sx={{ fontSize: 18 }} />
                  )}
                </IconButton>
              ) : (
                <Box sx={{ width: 26, height: 26, flexShrink: 0 }} />
              )}
              <Button
                fullWidth
                size="small"
                onClick={() => {
                  handleFolderSelection(folder.path);
                  setExpandedFolders((prev) => new Set(prev).add(folder.path));
                }}
                startIcon={<FolderRoundedIcon sx={{ fontSize: 19, color: '#818CF8' }} />}
                sx={{
                  justifyContent: 'flex-start',
                  py: 0.6,
                  px: 1.25,
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
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          gap: 0
        }}
      >
        <Box
          component="header"
          sx={{
            px: { xs: 2, md: 3 },
            py: 1.75,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0
          }}
        >
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Box
              sx={{
                width: 36,
                height: 36,
                borderRadius: '11px',
                display: 'grid',
                placeItems: 'center',
                color: '#fff',
                background: 'linear-gradient(135deg, #818CF8 0%, #4F46E5 65%, #4338CA 100%)',
                boxShadow: '0 6px 16px rgba(79, 70, 229, 0.35)'
              }}
            >
              <CloudRoundedIcon sx={{ fontSize: 21 }} />
            </Box>
            <Typography variant="h6">Personal Drive</Typography>
          </Stack>
          <Stack direction="row" spacing={0.75} alignItems="center">
            {config.personalAreaUrl && (
              <Button
                color="inherit"
                size="small"
                href={config.personalAreaUrl}
                startIcon={<AutoStoriesRoundedIcon />}
                title="Open My Space — your notes editor"
              >
                My Space
              </Button>
            )}
            {passkeySupported() && (
              <Tooltip title="Add a passkey to this account">
                <IconButton size="small" onClick={handleAddPasskey}>
                  <KeyRoundedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            <Button
              color="inherit"
              size="small"
              onClick={handleLogout}
              startIcon={<LogoutRoundedIcon />}
            >
              Log out
            </Button>
          </Stack>
        </Box>

        <Box
          sx={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            gap: { xs: 1.5, md: 2.5 },
            px: { xs: 1.5, md: 3 },
            pb: { xs: 1.5, md: 2.5 }
          }}
        >
          <Box
            sx={{
              width: { xs: '100%', md: 256 },
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
              maxHeight: { md: '100%' }
            }}
          >
            <List dense disablePadding sx={{ mb: 1 }}>
              <ListItemButton
                selected={driveTab === 'my-drive'}
                onClick={() => setDriveTab('my-drive')}
                sx={{ mb: 0.5, py: 1 }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <FolderRoundedIcon
                    sx={{ fontSize: 21, color: driveTab === 'my-drive' ? 'primary.main' : 'text.secondary' }}
                  />
                </ListItemIcon>
                <ListItemText
                  primary="My files"
                  primaryTypographyProps={{ fontWeight: 600, variant: 'body2' }}
                />
              </ListItemButton>
              <ListItemButton
                selected={driveTab === 'shared-with-me'}
                onClick={() => setDriveTab('shared-with-me')}
                sx={{ py: 1 }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <FolderSharedRoundedIcon
                    sx={{
                      fontSize: 21,
                      color: driveTab === 'shared-with-me' ? 'primary.main' : 'text.secondary'
                    }}
                  />
                </ListItemIcon>
                <ListItemText
                  primary="Shared with me"
                  primaryTypographyProps={{ fontWeight: 600, variant: 'body2' }}
                />
              </ListItemButton>
            </List>

            {driveTab === 'my-drive' && (
              <>
                <Typography
                  variant="overline"
                  sx={{ px: 1.5, color: 'text.secondary', letterSpacing: '0.08em', lineHeight: 2.2 }}
                >
                  Folders
                </Typography>
                <Button
                  fullWidth
                  size="small"
                  onClick={() => handleFolderSelection('')}
                  startIcon={<FolderRoundedIcon sx={{ fontSize: 19, color: '#818CF8' }} />}
                  sx={{
                    justifyContent: 'flex-start',
                    py: 0.6,
                    px: 1.5,
                    color: 'text.primary',
                    backgroundColor: currentPath === '' ? 'action.selected' : 'transparent',
                    '&:hover': {
                      backgroundColor: currentPath === '' ? 'action.selected' : 'action.hover'
                    }
                  }}
                >
                  <Typography noWrap variant="body2" fontWeight={currentPath === '' ? 600 : 500}>
                    All files
                  </Typography>
                </Button>
                <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto', pr: 0.5 }}>
                  {renderFolderTree('', 0)}
                </Box>
              </>
            )}
          </Box>

          <Stack spacing={1.5} sx={{ flex: 1, minWidth: 0, minHeight: 0 }}>
            {error && <Alert severity="error">{error}</Alert>}
            {uploadSummary && (
              <Alert severity="info" onClose={() => setUploadSummary('')}>
                {uploadSummary}
              </Alert>
            )}

            {driveTab === 'my-drive' && (
              <input
                ref={fileUploadInputRef}
                type="file"
                hidden
                multiple
                onChange={(event) => {
                  void handleUploadFiles(event);
                }}
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
                  borderRadius: '16px',
                  boxShadow: '0 1px 3px rgba(18, 22, 39, 0.06), 0 10px 30px rgba(18, 22, 39, 0.05)',
                  p: { xs: 1.5, md: 2.5 },
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
                  spacing={1.5}
                  sx={{ mb: 2 }}
                >
                  <Breadcrumbs
                    separator={<ChevronRightRoundedIcon sx={{ fontSize: 16, color: 'text.disabled' }} />}
                    aria-label="Current folder path"
                    sx={{ minWidth: 0 }}
                  >
                    {currentPath ? (
                      <Link
                        component="button"
                        type="button"
                        underline="hover"
                        color="text.secondary"
                        onClick={() => handleFolderSelection('')}
                        sx={{ fontWeight: 500, fontSize: '0.95rem' }}
                      >
                        My files
                      </Link>
                    ) : (
                      <Typography fontWeight={600} fontSize="0.95rem">
                        My files
                      </Typography>
                    )}
                    {currentPath
                      .split('/')
                      .filter(Boolean)
                      .map((segment, index, segments) => {
                        const target = segments.slice(0, index + 1).join('/');
                        const isLast = index === segments.length - 1;
                        return isLast ? (
                          <Typography key={target} fontWeight={600} fontSize="0.95rem" noWrap>
                            {segment}
                          </Typography>
                        ) : (
                          <Link
                            key={target}
                            component="button"
                            type="button"
                            underline="hover"
                            color="text.secondary"
                            onClick={() => handleFolderSelection(target)}
                            sx={{ fontWeight: 500, fontSize: '0.95rem' }}
                          >
                            {segment}
                          </Link>
                        );
                      })}
                  </Breadcrumbs>
                  <Stack direction="row" justifyContent="flex-end" alignItems="center" spacing={1}>
                    {isUploading && (
                      <Button size="small" color="error" onClick={handleCancelUpload}>
                        Cancel upload
                      </Button>
                    )}
                    <Tooltip title="New folder (N)">
                      <Button
                        variant="outlined"
                        size="small"
                        startIcon={<CreateNewFolderRoundedIcon />}
                        onClick={handleCreateFolderOpen}
                        disabled={loading || isUploading}
                      >
                        New folder
                      </Button>
                    </Tooltip>
                    <Tooltip title="Upload files (U)">
                      <Button
                        variant="contained"
                        size="small"
                        startIcon={<CloudUploadRoundedIcon />}
                        disabled={loading || isUploading}
                        onClick={openFilePicker}
                      >
                        Upload
                      </Button>
                    </Tooltip>
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
                          <GridViewRoundedIcon sx={{ fontSize: 16 }} />
                        </ToggleButton>
                        <ToggleButton value="medium" aria-label="Medium grid">
                          <GridViewRoundedIcon sx={{ fontSize: 20 }} />
                        </ToggleButton>
                        <ToggleButton value="large" aria-label="Large grid">
                          <GridViewRoundedIcon sx={{ fontSize: 24 }} />
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
                      onFilePreview={setPreviewFile}
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
                      onFileOpen={setPreviewFile}
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
                  borderRadius: '16px',
                  boxShadow: '0 1px 3px rgba(18, 22, 39, 0.06), 0 10px 30px rgba(18, 22, 39, 0.05)',
                  p: { xs: 1.5, md: 2.5 },
                  display: 'flex',
                  flexDirection: 'column',
                  minHeight: 0,
                  flex: 1
                }}
              >
                <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
                  Shared with me
                </Typography>
                {sharedLoading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                    <CircularProgress />
                  </Box>
                ) : sharedFiles.length === 0 ? (
                  <Stack alignItems="center" spacing={1} sx={{ py: 8 }}>
                    <Box
                      sx={{
                        width: 64,
                        height: 64,
                        borderRadius: '20px',
                        display: 'grid',
                        placeItems: 'center',
                        bgcolor: (t) => alpha(t.palette.primary.main, 0.08)
                      }}
                    >
                      <FolderSharedRoundedIcon sx={{ fontSize: 32, color: 'primary.main' }} />
                    </Box>
                    <Typography fontWeight={600}>Nothing shared yet</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Files that others share with you will show up here.
                    </Typography>
                  </Stack>
                ) : (
                  <Box sx={{ flex: 1, minHeight: { xs: 320, md: 0 }, overflowY: 'auto', pr: 0.25 }}>
                    <List disablePadding>
                      {sharedFiles.map((sf) => (
                        <ListItem
                          key={sf.fileId}
                          secondaryAction={
                            sf.permission === 'download' || sf.permission === 'edit' ? (
                              <Tooltip title="Download">
                                <IconButton
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
                                </IconButton>
                              </Tooltip>
                            ) : null
                          }
                          sx={{
                            borderRadius: '12px',
                            mb: 0.5,
                            transition: 'background-color 0.15s',
                            '&:hover': { bgcolor: 'action.hover' }
                          }}
                        >
                          <ListItemIcon sx={{ minWidth: 52 }}>
                            <Avatar
                              sx={{
                                width: 38,
                                height: 38,
                                bgcolor: (t) => alpha(t.palette.primary.main, 0.1),
                                color: 'primary.main',
                                fontWeight: 700,
                                fontSize: '0.95rem'
                              }}
                            >
                              {(sf.sharedByEmail || '?').charAt(0).toUpperCase()}
                            </Avatar>
                          </ListItemIcon>
                          <ListItemText
                            primary={
                              <Stack component="span" direction="row" spacing={0.75} alignItems="center">
                                <InsertDriveFileRoundedIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                                <Typography component="span" fontWeight={600} noWrap>
                                  {sf.filename}
                                </Typography>
                              </Stack>
                            }
                            secondary={
                              <Stack component="span" direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                                <Typography component="span" variant="caption" color="text.secondary">
                                  From {sf.sharedByEmail}
                                </Typography>
                                <Chip
                                  label={sf.permission === 'read' ? 'View' : sf.permission === 'download' ? 'Download' : 'Edit'}
                                  size="small"
                                  sx={{
                                    height: 20,
                                    fontSize: '0.7rem',
                                    bgcolor: (t) => alpha(t.palette.primary.main, 0.08),
                                    color: 'primary.dark'
                                  }}
                                />
                                <Typography component="span" variant="caption" color="text.secondary">
                                  Expires {formatDate(sf.expiresAt)}
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
            onPreview={handleCtxPreview}
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

          <PreviewModal
            file={previewFile}
            onClose={() => setPreviewFile(null)}
            getDownloadUrl={getFileDownloadUrl}
            onDownload={handleDownload}
          />

          <SuccessToast message={shareSuccess} onClose={() => setShareSuccess('')} />

          {assistantConfigured && <Assistant onApplied={() => loadFiles()} />}
      </Box>
      <UploadDropOverlay visible={driveTab === 'my-drive' && isUploadDragActive} />
    </>
  );
}

export default App;
