import React from 'react';
import { Box, Chip, IconButton, LinearProgress, Paper, Stack, Typography } from '@mui/material';
import type { UploadItemProgress, UploadStats } from '../hooks/useUploadManager';

interface UploadProgressPanelProps {
  uploadItems: UploadItemProgress[];
  uploadStats: UploadStats;
  isUploading: boolean;
  onCancelUpload: () => void;
}

export function UploadProgressPanel({
  uploadItems,
  uploadStats,
  isUploading,
  onCancelUpload
}: UploadProgressPanelProps): React.ReactElement | null {
  if (uploadItems.length === 0) return null;

  return (
    <Paper elevation={0} sx={{ borderRadius: 0, border: 1, borderColor: 'divider', p: 1.25 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          Upload progress
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            label={`${uploadStats.completedCount}/${uploadStats.totalCount} complete`}
            color={uploadStats.failedCount > 0 ? 'error' : 'default'}
          />
          {isUploading && (
            <IconButton
              size="small"
              onClick={onCancelUpload}
              aria-label="Cancel upload"
            >
              x
            </IconButton>
          )}
        </Stack>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={uploadStats.percent}
        sx={{ height: 8, borderRadius: 999 }}
      />
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.75, display: 'block' }}>
        {uploadStats.percent}% complete
        {` • `}
        {uploadStats.activeCount} active
        {` • `}
        {uploadStats.failedCount} failed
        {` • `}
        {uploadStats.canceledCount} canceled
      </Typography>
      <Stack spacing={1} sx={{ mt: 1.25, maxHeight: 220, overflowY: 'auto' }}>
        {uploadItems.map((item) => (
          <Box key={item.id}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
              <Typography
                variant="body2"
                noWrap
                title={item.relativePath}
                sx={{ maxWidth: '70%' }}
              >
                {item.relativePath}
              </Typography>
              <Chip
                size="small"
                label={item.status}
                color={
                  item.status === 'failed'
                    ? 'error'
                    : item.status === 'completed'
                      ? 'success'
                      : item.status === 'canceled'
                        ? 'warning'
                        : 'default'
                }
              />
            </Stack>
            <LinearProgress
              variant="determinate"
              value={item.totalBytes > 0 ? Math.round((item.uploadedBytes / item.totalBytes) * 100) : 0}
              sx={{ mt: 0.5, height: 6, borderRadius: 999 }}
            />
            {item.error && (
              <Typography variant="caption" color="error.main">
                {item.error}
              </Typography>
            )}
          </Box>
        ))}
      </Stack>
    </Paper>
  );
}
