import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Breadcrumbs,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography
} from '@mui/material';
import FolderRoundedIcon from '@mui/icons-material/FolderRounded';
import { listFiles } from '../api';
import type { DriveFolder } from './Folder';

export interface MoveItem {
  type: 'file' | 'folder';
  id: string;
  /** For folders, the full path; for files, the fileId. */
  path?: string;
  name: string;
}

export interface MoveDialogProps {
  open: boolean;
  items: MoveItem[];
  onClose: () => void;
  onConfirm: (destinationPath: string) => void;
}

interface FolderEntry {
  folderId: string;
  name: string;
  path: string;
}

function parseFolder(item: unknown): FolderEntry | null {
  if (!item || typeof item !== 'object') return null;
  const o = item as Record<string, unknown>;
  if (typeof o.folderId !== 'string' || typeof o.name !== 'string' || typeof o.path !== 'string')
    return null;
  return { folderId: o.folderId, name: o.name, path: o.path };
}

export function MoveDialog({
  open,
  items,
  onClose,
  onConfirm
}: MoveDialogProps): React.ReactElement {
  const [browsePath, setBrowsePath] = useState('/');
  const [folders, setFolders] = useState<FolderEntry[]>([]);
  const [loading, setLoading] = useState(false);

  // Set of folder paths being moved (to exclude from the tree)
  const excludedPaths = new Set(
    items.filter((i) => i.type === 'folder').map((i) => i.path ?? '')
  );

  const loadFolders = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const result = await listFiles(path === '/' ? undefined : path);
      const parsed = Array.isArray(result.folders)
        ? result.folders.map(parseFolder).filter((f): f is FolderEntry => f !== null)
        : [];
      setFolders(parsed);
    } catch {
      setFolders([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (open) {
      setBrowsePath('/');
      void loadFolders('/');
    }
  }, [open, loadFolders]);

  const handleNavigate = (path: string): void => {
    setBrowsePath(path);
    void loadFolders(path);
  };

  // Build breadcrumb segments from browsePath
  const segments = browsePath === '/' ? [] : browsePath.split('/').filter(Boolean);

  const excludedArr = Array.from(excludedPaths);
  const visibleFolders = folders.filter((f) => {
    // Exclude the folders being moved (and their children)
    for (let i = 0; i < excludedArr.length; i += 1) {
      const ep = excludedArr[i];
      if (ep && (f.path === ep || f.path.startsWith(ep + '/'))) return false;
    }
    return true;
  });

  const label =
    items.length === 1
      ? `Move "${items[0].name}"`
      : `Move ${items.length} items`;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{label}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5}>
          <Breadcrumbs sx={{ mt: 0.5 }}>
            <Link
              component="button"
              underline="hover"
              color={browsePath === '/' ? 'text.primary' : 'inherit'}
              onClick={() => handleNavigate('/')}
              sx={{ cursor: 'pointer', fontWeight: browsePath === '/' ? 700 : 400 }}
            >
              Root
            </Link>
            {segments.map((seg, idx) => {
              const segPath = '/' + segments.slice(0, idx + 1).join('/');
              const isLast = idx === segments.length - 1;
              return (
                <Link
                  key={segPath}
                  component="button"
                  underline="hover"
                  color={isLast ? 'text.primary' : 'inherit'}
                  onClick={() => handleNavigate(segPath)}
                  sx={{ cursor: 'pointer', fontWeight: isLast ? 700 : 400 }}
                >
                  {seg}
                </Link>
              );
            })}
          </Breadcrumbs>

          <Box
            sx={{
              border: 1,
              borderColor: 'divider',
              borderRadius: 2,
              minHeight: 160,
              maxHeight: 300,
              overflow: 'auto'
            }}
          >
            {loading ? (
              <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
                <CircularProgress size={24} />
              </Stack>
            ) : visibleFolders.length === 0 ? (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ p: 2, textAlign: 'center' }}
              >
                No subfolders here
              </Typography>
            ) : (
              <List dense disablePadding>
                {visibleFolders.map((folder) => (
                  <ListItemButton
                    key={folder.folderId}
                    onClick={() => handleNavigate(folder.path)}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <FolderRoundedIcon sx={{ color: 'warning.main' }} />
                    </ListItemIcon>
                    <ListItemText primary={folder.name} />
                  </ListItemButton>
                ))}
              </List>
            )}
          </Box>

          <Typography variant="body2" color="text.secondary">
            Destination: <strong>{browsePath}</strong>
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => onConfirm(browsePath)}
          disabled={loading}
        >
          Move here
        </Button>
      </DialogActions>
    </Dialog>
  );
}
