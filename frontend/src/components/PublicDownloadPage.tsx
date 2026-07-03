import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloudDownloadRoundedIcon from '@mui/icons-material/CloudDownloadRounded';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import LockRoundedIcon from '@mui/icons-material/LockRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import TimerOffRoundedIcon from '@mui/icons-material/TimerOffRounded';
import type { PublicLinkInfo } from '../types/drive';
import { formatFileSize } from '../types/drive';
import { fetchPublicLinkInfo, getPublicDownloadUrl } from '../service/driveService';
import { formatDate } from '../utils';

interface PublicDownloadPageProps {
  token: string;
}

export function PublicDownloadPage({ token }: PublicDownloadPageProps): React.ReactElement {
  const [info, setInfo] = useState<PublicLinkInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [password, setPassword] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');

  const loadInfo = useCallback(async (isRefresh = false) => {
    setLoading(true);
    if (!isRefresh) setError('');
    const result = await fetchPublicLinkInfo(token);
    if (result.info) {
      setInfo(result.info);
      setError('');
    } else if (!isRefresh) {
      setError(result.error ?? 'Link not found or expired');
    }
    setLoading(false);
  }, [token]);

  useEffect(() => {
    void loadInfo();
  }, [loadInfo]);

  const handleDownload = async (): Promise<void> => {
    setDownloading(true);
    setDownloadError('');
    const result = await getPublicDownloadUrl(token, info?.hasPassword ? password : undefined);
    if (result.downloadUrl) {
      // Trigger browser download
      const a = document.createElement('a');
      a.href = result.downloadUrl;
      a.download = info?.filename ?? 'download';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Refresh info to update download count (don't show error state if refresh fails)
      void loadInfo(true);
    } else {
      setDownloadError(result.error ?? 'Download failed');
    }
    setDownloading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void handleDownload();
    }
  };

  // --- Loading state ---
  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          bgcolor: 'background.default',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  // --- Error state (invalid / expired link) ---
  if (error || !info) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          bgcolor: 'background.default',
        }}
      >
        <Container maxWidth="xs">
          <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
            <TimerOffRoundedIcon sx={{ fontSize: 56, color: 'error.main', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              Link unavailable
            </Typography>
            <Typography color="text.secondary">
              {error || 'This link is invalid or has expired.'}
            </Typography>
          </Paper>
        </Container>
      </Box>
    );
  }

  // --- Normal download page ---
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        bgcolor: 'background.default',
      }}
    >
      <Container maxWidth="xs">
        <Paper elevation={3} sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            {/* Header / branding */}
            <Stack direction="row" spacing={1} alignItems="center">
              <CloudDownloadRoundedIcon color="primary" />
              <Typography variant="h6" fontWeight={600}>
                Cloud Storage
              </Typography>
            </Stack>

            {/* File info */}
            <Paper
              variant="outlined"
              sx={{
                width: '100%',
                p: 2,
                display: 'flex',
                alignItems: 'center',
                gap: 2,
              }}
            >
              <InsertDriveFileRoundedIcon sx={{ fontSize: 40, color: 'primary.main' }} />
              <Box sx={{ overflow: 'hidden' }}>
                <Typography
                  variant="subtitle1"
                  fontWeight={600}
                  sx={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {info.filename}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {formatFileSize(info.size)}
                </Typography>
              </Box>
            </Paper>

            {/* Stats */}
            <Stack
              direction="row"
              spacing={3}
              justifyContent="center"
              sx={{ width: '100%' }}
            >
              <Stack direction="row" spacing={0.5} alignItems="center">
                <DownloadRoundedIcon fontSize="small" color="action" />
                <Typography variant="body2" color="text.secondary">
                  {info.downloadCount} download{info.downloadCount !== 1 ? 's' : ''}
                </Typography>
              </Stack>
              {info.expiresAt && (
                <Typography variant="body2" color="text.secondary">
                  Expires: {formatDate(info.expiresAt)}
                </Typography>
              )}
            </Stack>

            {/* Password field if required */}
            {info.hasPassword && (
              <Stack spacing={1} sx={{ width: '100%' }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <LockRoundedIcon fontSize="small" color="warning" />
                  <Typography variant="body2" color="text.secondary">
                    This file is password protected
                  </Typography>
                </Stack>
                <TextField
                  fullWidth
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  size="small"
                  autoFocus
                />
              </Stack>
            )}

            {downloadError && (
              <Alert severity="error" sx={{ width: '100%' }}>
                {downloadError}
              </Alert>
            )}

            {/* Download button */}
            <Button
              variant="contained"
              size="large"
              fullWidth
              startIcon={
                downloading ? (
                  <CircularProgress size={20} color="inherit" />
                ) : (
                  <CloudDownloadRoundedIcon />
                )
              }
              onClick={() => void handleDownload()}
              disabled={downloading || (info.hasPassword && !password.trim())}
              sx={{ textTransform: 'none', py: 1.5 }}
            >
              {downloading ? 'Preparing download...' : 'Download'}
            </Button>
          </Stack>
        </Paper>
      </Container>
    </Box>
  );
}
