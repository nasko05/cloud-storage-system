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
  FormControlLabel,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography
} from '@mui/material';
import ContentCopyRoundedIcon from '@mui/icons-material/ContentCopyRounded';
import LinkRoundedIcon from '@mui/icons-material/LinkRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import AddLinkRoundedIcon from '@mui/icons-material/AddLinkRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import LockRoundedIcon from '@mui/icons-material/LockRounded';
import type { ShareTarget, SharePermission, FileShare, PublicLink } from '../types/drive';
import { formatDate } from '../utils';
import SuccessToast from './SuccessToast';
import {
  fetchFileShares,
  revokeShare,
  updateSharePermissionResult,
  createPublicLinkResult,
  fetchPublicLinks,
  deletePublicLinkResult,
  updatePublicLinkResult,
} from '../service/driveService';


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

/** Copy text to clipboard with fallback. */
async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
}

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
  const [snackMsg, setSnackMsg] = useState('');

  // --- Current shares state (Tab 1) ---
  const [tabIndex, setTabIndex] = useState(0);
  const [shares, setShares] = useState<FileShare[]>([]);
  const [sharesLoading, setSharesLoading] = useState(false);
  const [sharesError, setSharesError] = useState('');

  // --- Public link state (Tab 2) ---
  const [publicLinks, setPublicLinks] = useState<PublicLink[]>([]);
  const [publicLinksLoading, setPublicLinksLoading] = useState(false);
  const [publicLinksError, setPublicLinksError] = useState('');
  const [newLinkPassword, setNewLinkPassword] = useState('');
  const [newLinkUsePassword, setNewLinkUsePassword] = useState(false);
  const [newLinkExpiryDate, setNewLinkExpiryDate] = useState(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
  const [creatingLink, setCreatingLink] = useState(false);

  const fileId = target?.type === 'file' ? target.file.fileId : '';
  const filename = target?.type === 'file' ? target.file.filename : '';

  // --- Load shares ---
  const loadShares = useCallback(async () => {
    if (!fileId) return;
    setSharesLoading(true);
    setSharesError('');
    const result = await fetchFileShares(fileId);
    setShares(result.shares);
    if (result.error) setSharesError(result.error);
    setSharesLoading(false);
  }, [fileId]);

  // --- Load public links ---
  const loadPublicLinks = useCallback(async () => {
    if (!fileId) return;
    setPublicLinksLoading(true);
    setPublicLinksError('');
    const result = await fetchPublicLinks(fileId);
    setPublicLinks(result.links);
    if (result.error) setPublicLinksError(result.error);
    setPublicLinksLoading(false);
  }, [fileId]);

  // Reset form + load data when target changes
  useEffect(() => {
    if (target) {
      setEmail('');
      setPermission('read');
      setExpiryDate(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
      setTabIndex(0);
      setShares([]);
      setSharesError('');
      setPublicLinks([]);
      setPublicLinksError('');
      setNewLinkPassword('');
      setNewLinkUsePassword(false);
      setNewLinkExpiryDate(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
      void loadShares();
      void loadPublicLinks();
    }
  }, [target, loadShares, loadPublicLinks]);

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

  // --- Public link handlers ---

  const handleCreatePublicLink = async (): Promise<void> => {
    if (!fileId) return;
    setCreatingLink(true);
    setPublicLinksError('');
    const password = newLinkUsePassword && newLinkPassword.trim() ? newLinkPassword.trim() : undefined;
    const days = daysUntil(newLinkExpiryDate);
    const result = await createPublicLinkResult(fileId, password, days);
    if (result.success && result.link) {
      setPublicLinks((prev) => [result.link!, ...prev]);
      setNewLinkPassword('');
      setNewLinkUsePassword(false);
      onShareChanged?.();
      // Auto-copy the new link
      const url = `${window.location.origin}/s/${result.link.token}`;
      await copyToClipboard(url);
      setSnackMsg('Public link created and copied to clipboard');
    } else {
      setPublicLinksError(result.error ?? 'Failed to create public link');
    }
    setCreatingLink(false);
  };

  const handleCopyPublicLink = async (token: string): Promise<void> => {
    const url = `${window.location.origin}/s/${token}`;
    await copyToClipboard(url);
    setSnackMsg('Link copied to clipboard');
  };

  const handleDeletePublicLink = async (token: string): Promise<void> => {
    const result = await deletePublicLinkResult(token);
    if (result.success) {
      setPublicLinks((prev) => prev.filter((l) => l.token !== token));
      onShareChanged?.();
    } else {
      setPublicLinksError(result.error ?? 'Failed to delete link');
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
            variant="scrollable"
            scrollButtons="auto"
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
            <Tab
              label={
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <span>Public link</span>
                  {publicLinks.length > 0 && (
                    <Chip label={publicLinks.length} size="small" sx={{ height: 20, fontSize: '0.75rem' }} />
                  )}
                </Stack>
              }
            />
          </Tabs>
        </Box>
        <DialogContent sx={{ minHeight: 260 }}>
          {/* ---- Tab 0: Share with user ---- */}
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
            </Stack>
          )}

          {/* ---- Tab 1: Current shares ---- */}
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
                              Expires: {formatDate(share.expiresAt)}
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

          {/* ---- Tab 2: Public links ---- */}
          {tabIndex === 2 && (
            <Box sx={{ pt: 1 }}>
              {/* Create new public link form */}
              <Stack spacing={2} sx={{ mb: 3 }}>
                <Typography variant="subtitle2">Create a new public link</Typography>

                <FormControlLabel
                  control={
                    <Switch
                      checked={newLinkUsePassword}
                      onChange={(e) => setNewLinkUsePassword(e.target.checked)}
                      size="small"
                    />
                  }
                  label="Password protection"
                />

                {newLinkUsePassword && (
                  <TextField
                    fullWidth
                    size="small"
                    label="Password"
                    type="password"
                    value={newLinkPassword}
                    onChange={(e) => setNewLinkPassword(e.target.value)}
                    placeholder="Enter a password"
                  />
                )}

                <TextField
                  fullWidth
                  size="small"
                  label="Expires on"
                  type="date"
                  value={newLinkExpiryDate}
                  onChange={(e) => setNewLinkExpiryDate(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  inputProps={{ min: todayStr }}
                  helperText={`Expires in ${daysUntil(newLinkExpiryDate)} day${daysUntil(newLinkExpiryDate) === 1 ? '' : 's'}`}
                />

                <Button
                  variant="contained"
                  size="small"
                  startIcon={<AddLinkRoundedIcon />}
                  onClick={() => void handleCreatePublicLink()}
                  disabled={creatingLink || (newLinkUsePassword && !newLinkPassword.trim())}
                  sx={{ textTransform: 'none', alignSelf: 'flex-start' }}
                >
                  {creatingLink ? 'Creating...' : 'Create public link'}
                </Button>
              </Stack>

              {publicLinksError && (
                <Alert severity="error" sx={{ mb: 2 }}>{publicLinksError}</Alert>
              )}

              {/* Existing public links */}
              {publicLinksLoading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress size={28} />
                </Box>
              ) : publicLinks.length === 0 ? (
                <Typography color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
                  No public links yet.
                </Typography>
              ) : (
                <>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Active links</Typography>
                  <List disablePadding>
                    {publicLinks.map((link) => (
                      <ListItem
                        key={link.token}
                        secondaryAction={
                          <Stack direction="row" spacing={0.5}>
                            <Tooltip title="Copy link">
                              <IconButton
                                size="small"
                                onClick={() => void handleCopyPublicLink(link.token)}
                              >
                                <ContentCopyRoundedIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Delete link">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => void handleDeletePublicLink(link.token)}
                              >
                                <DeleteOutlineRoundedIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                        }
                        sx={{
                          borderBottom: '1px solid',
                          borderColor: 'divider',
                          '&:last-child': { borderBottom: 'none' },
                          py: 1,
                        }}
                      >
                        <ListItemText
                          primary={
                            <Stack direction="row" spacing={1} alignItems="center">
                              <LinkRoundedIcon fontSize="small" color="action" />
                              <Typography
                                variant="body2"
                                sx={{
                                  fontFamily: 'monospace',
                                  fontSize: '0.8rem',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                  maxWidth: 220,
                                }}
                              >
                                {`${window.location.origin}/s/${link.token}`}
                              </Typography>
                              {link.hasPassword && (
                                <Tooltip title="Password protected">
                                  <LockRoundedIcon fontSize="small" color="warning" />
                                </Tooltip>
                              )}
                            </Stack>
                          }
                          secondary={
                            <Stack
                              component="span"
                              direction="row"
                              spacing={2}
                              alignItems="center"
                              sx={{ mt: 0.5 }}
                            >
                              <Stack component="span" direction="row" spacing={0.5} alignItems="center">
                                <DownloadRoundedIcon sx={{ fontSize: 14 }} />
                                <Typography component="span" variant="caption">
                                  {link.downloadCount} download{link.downloadCount !== 1 ? 's' : ''}
                                </Typography>
                              </Stack>
                              <Typography component="span" variant="caption" color="text.secondary">
                                Expires: {formatDate(link.expiresAt)}
                              </Typography>
                            </Stack>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
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

      <SuccessToast message={snackMsg} onClose={() => setSnackMsg('')} autoHideDuration={2500} />
    </>
  );
}
