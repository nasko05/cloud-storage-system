import React from 'react';
import { Box, Paper, Typography } from '@mui/material';

interface UploadDropOverlayProps {
  visible: boolean;
}

export function UploadDropOverlay({ visible }: UploadDropOverlayProps): React.ReactElement | null {
  if (!visible) return null;

  return (
    <Box
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: (theme) => theme.zIndex.modal + 10,
        bgcolor: 'rgba(15, 23, 42, 0.24)',
        border: '3px dashed',
        borderColor: 'primary.main',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 3,
        pointerEvents: 'none'
      }}
    >
      <Paper
        elevation={6}
        sx={{
          borderRadius: 3,
          px: 4,
          py: 3,
          textAlign: 'center',
          bgcolor: 'rgba(255, 255, 255, 0.96)'
        }}
      >
        <Typography variant="h6" fontWeight={700}>
          Drop files or folders to upload
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Folder structure is preserved automatically.
        </Typography>
      </Paper>
    </Box>
  );
}
