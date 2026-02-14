import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography
} from '@mui/material';
import ContentCopyRoundedIcon from '@mui/icons-material/ContentCopyRounded';
import LinkRoundedIcon from '@mui/icons-material/LinkRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import type { ShareTarget, SharePermission, FileShare } from '../types/drive';
import { fetchFileShares, revokeShare, updateSharePermissionResult } from '../service/driveService';

export type { ShareTarget, SharePermission } from '../types/drive';

export interface ShareDialogProps {
  target: ShareTarget;
  onClose: () => void;
  onSubmit: (params: {
    fileId: string;
    shareWithEmail: string;
    permission: SharePermission;
    expiryDays: number;
  }) => void;
  /** Called when a share is revoked or permission is updated, so the parent can refresh. */
  onShareChanged?: () => void;
}

/** Return an ISO date string (YYYY-MM-DD) offset by `days` from today. */
function defaultExpiryDate(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Calculate the number of days between today and a YYYY-MM-DD string. */
function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + 'T00:00:00');
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.max(1, Math.round((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

const DEFAULT_EXPIRY_DAYS = 30;

const PERMISSION_LABELS: Record<SharePermission, string> = {
  read: 'View',
  download: 'Download',
  edit: 'Edit'
};

export function ShareDialog({
  target,
  onClose,
  onSubmit,
  onShareChanged
}: ShareDialogProps): React.ReactElement {
  // --- Share form state (Tab 0) ---
  const [email, setEmail] = useState('');
  const [permission, setPermission] = useState<SharePermission>('read');
  const [expiryDate, setExpiryDate] = useState(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
  const [linkCopied, setLinkCopied] = useState(false);

  // --- Current shares state (Tab 1) ---
  const [tabIndex, setTabIndex] = useState(0);
  const [shares, setShares] = useState<FileShare[]>([]);
  const [sharesLoading, setSharesLoading] = useState(false);
  const [sharesError, setSharesError] = useState('');

  const fileId = target?.type === 'file' ? target.file.fileId : '';
  const filename = target?.type === 'file' ? target.file.filename : '';

  const loadShares = useCallback(async () => {
    if (!fileId) return;
    setSharesLoading(true);
    setSharesError('');
    const result = await fetchFileShares(fileId);
    setShares(result.shares);
    if (result.error) setSharesError(result.error);
    setSharesLoading(false);
  }, [fileId]);

  // Reset form + load shares when target changes
  useEffect(() => {
    if (target) {
      setEmail('');
      setPermission('read');
      setExpiryDate(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
      setTabIndex(0);
      setShares([]);
      setSharesError('');
      void loadShares();
    }
  }, [target, loadShares]);

  const todayStr = new Date().toISOString().slice(0, 10);

  const canSubmit = email.trim().length > 0 && expiryDate >= todayStr;

  const handleSubmit = (): void => {
    if (!canSubmit || !fileId) return;
    onSubmit({
      fileId,
      shareWithEmail: email.trim(),
      permission,
      expiryDays: daysUntil(expiryDate)
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleCopyLink = async (): Promise<void> => {
    const link = `${window.location.origin}/shared/${fileId}`;
    try {
      await navigator.clipboard.writeText(link);
      setLinkCopied(true);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = link;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setLinkCopied(true);
    }
  };

  const handleRevoke = async (sharedWith: string): Promise<void> => {
    const result = await revokeShare(fileId, sharedWith);
    if (result.success) {
      setShares((prev) => prev.filter((s) => s.sharedWith !== sharedWith));
      onShareChanged?.();
    } else {
      setSharesError(result.error ?? 'Failed to revoke share');
    }
  };

  const handlePermissionChange = async (
    sharedWith: string,
    newPermission: SharePermission
  ): Promise<void> => {
    const result = await updateSharePermissionResult(fileId, sharedWith, newPermission);
    if (result.success) {
      setShares((prev) =>
        prev.map((s) =>
          s.sharedWith === sharedWith ? { ...s, permission: newPermission } : s
        )
      );
      onShareChanged?.();
    } else {
      setSharesError(result.error ?? 'Failed to update permission');
    }
  };

  return (
    <>
      <Dialog open={target !== null} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>Share &ldquo;{filename}&rdquo;</DialogTitle>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }}>
          <Tabs
            value={tabIndex}
            onChange={(_, v) => setTabIndex(v)}
            aria-label="Share dialog tabs"
          >
            <Tab label="Share" />
            <Tab
              label={
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <span>Current shares</span>
                  {shares.length > 0 && (
                    <Chip label={shares.length} size="small" sx={{ height: 20, fontSize: '0.75rem' }} />
                  )}
                </Stack>
              }
            />
          </Tabs>
        </Box>
        <DialogContent sx={{ minHeight: 260 }}>
          {tabIndex === 0 && (
            <Stack spacing={2.5} sx={{ pt: 1 }}>
              <TextField
                autoFocus
                fullWidth
                label="Email or user ID"
                placeholder="colleague@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={handleKeyDown}
                type="email"
              />

              <FormControl fullWidth>
                <InputLabel id="share-permission-label">Permission</InputLabel>
                <Select
                  labelId="share-permission-label"
                  value={permission}
                  label="Permission"
                  onChange={(e) => setPermission(e.target.value as SharePermission)}
                >
                  <MenuItem value="read">View</MenuItem>
                  <MenuItem value="download">Download</MenuItem>
                  <MenuItem value="edit">Edit</MenuItem>
                </Select>
              </FormControl>

              <TextField
                fullWidth
                label="Expires on"
                type="date"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                inputProps={{ min: todayStr }}
                helperText={`Expires in ${daysUntil(expiryDate)} day${daysUntil(expiryDate) === 1 ? '' : 's'}`}
              />

              <Box>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<LinkRoundedIcon />}
                  endIcon={<ContentCopyRoundedIcon />}
                  onClick={handleCopyLink}
                  sx={{ textTransform: 'none' }}
                >
                  Copy shareable link
                </Button>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  Anyone with the link and permissions can access this file.
                </Typography>
              </Box>
            </Stack>
          )}

          {tabIndex === 1 && (
            <Box sx={{ pt: 1 }}>
              {sharesLoading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress size={28} />
                </Box>
              ) : sharesError ? (
                <Alert severity="error" sx={{ mb: 1 }}>{sharesError}</Alert>
              ) : shares.length === 0 ? (
                <Typography color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                  This file is not shared with anyone.
                </Typography>
              ) : (
                <List disablePadding>
                  {shares.map((share) => (
                    <ListItem
                      key={share.sharedWith}
                      secondaryAction={
                        <Tooltip title="Revoke access">
                          <IconButton
                            edge="end"
                            size="small"
                            color="error"
                            onClick={() => void handleRevoke(share.sharedWith)}
                          >
                            <DeleteOutlineRoundedIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      }
                      sx={{
                        borderBottom: '1px solid',
                        borderColor: 'divider',
                        '&:last-child': { borderBottom: 'none' },
                        py: 1
                      }}
                    >
                      <ListItemText
                        primary={share.sharedWith}
                        secondary={
                          <Stack
                            component="span"
                            direction="row"
                            spacing={1}
                            alignItems="center"
                            sx={{ mt: 0.5 }}
                          >
                            <FormControl size="small" variant="standard" sx={{ minWidth: 100 }}>
                              <Select
                                value={share.permission}
                                onChange={(e) =>
                                  void handlePermissionChange(
                                    share.sharedWith,
                                    e.target.value as SharePermission
                                  )
                                }
                                sx={{ fontSize: '0.8rem' }}
                              >
                                {(Object.keys(PERMISSION_LABELS) as SharePermission[]).map((p) => (
                                  <MenuItem key={p} value={p}>
                                    {PERMISSION_LABELS[p]}
                                  </MenuItem>
                                ))}
                              </Select>
                            </FormControl>
                            <Typography component="span" variant="caption" color="text.secondary">
                              Expires: {new Date(share.expiresAt).toLocaleDateString()}
                            </Typography>
                          </Stack>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          {tabIndex === 0 && (
            <Button
              onClick={handleSubmit}
              variant="contained"
              disabled={!canSubmit}
            >
              Share
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <Snackbar
        open={linkCopied}
        autoHideDuration={2500}
        onClose={() => setLinkCopied(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setLinkCopied(false)}
          severity="success"
          variant="filled"
          sx={{ width: '100%' }}
        >
          Link copied to clipboard
        </Alert>
      </Snackbar>
    </>
  );
}
