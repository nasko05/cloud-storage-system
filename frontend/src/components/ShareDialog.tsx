import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  TextField,
  Typography
} from '@mui/material';
import ContentCopyRoundedIcon from '@mui/icons-material/ContentCopyRounded';
import LinkRoundedIcon from '@mui/icons-material/LinkRounded';
import type { ShareTarget, SharePermission } from '../types/drive';

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

export function ShareDialog({
  target,
  onClose,
  onSubmit
}: ShareDialogProps): React.ReactElement {
  const [email, setEmail] = useState('');
  const [permission, setPermission] = useState<SharePermission>('read');
  const [expiryDate, setExpiryDate] = useState(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
  const [linkCopied, setLinkCopied] = useState(false);

  // Reset form when target changes
  useEffect(() => {
    if (target) {
      setEmail('');
      setPermission('read');
      setExpiryDate(defaultExpiryDate(DEFAULT_EXPIRY_DAYS));
    }
  }, [target]);

  const fileId = target?.type === 'file' ? target.file.fileId : '';
  const filename = target?.type === 'file' ? target.file.filename : '';

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
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = link;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setLinkCopied(true);
    }
  };

  return (
    <>
      <Dialog open={target !== null} onClose={onClose} maxWidth="xs" fullWidth>
        <DialogTitle>Share &ldquo;{filename}&rdquo;</DialogTitle>
        <DialogContent>
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
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={!canSubmit}
          >
            Share
          </Button>
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
