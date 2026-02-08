import React from 'react';
import {
  Box,
  Card,
  CardActionArea,
  CircularProgress,
  Stack,
  Typography
} from '@mui/material';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import { FileActions } from './File';
import type { DriveFile } from './File';

export interface GridLayoutProps {
  files: DriveFile[];
  loading?: boolean;
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
}

export function GridLayout({
  files,
  loading = false,
  onDownload,
  onDelete
}: GridLayoutProps): React.ReactElement {
  if (loading) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ py: 6 }}>
        <CircularProgress size={32} />
      </Stack>
    );
  }

  if (files.length === 0) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
        <Typography variant="body1" color="text.secondary">
          No files yet. Upload something to get started.
        </Typography>
      </Stack>
    );
  }

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
        gap: 2
      }}
    >
      {files.map((file) => (
        <Card
          key={file.fileId}
          variant="outlined"
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            borderRadius: 2
          }}
        >
          <CardActionArea
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'flex-start',
              p: 2,
              '&.Mui-focusVisible': { outline: '2px solid', outlineColor: 'primary.main' }
            }}
          >
            <InsertDriveFileRoundedIcon
              sx={{ fontSize: 48, color: 'action.active', mb: 1 }}
              aria-hidden
            />
            <Typography
              variant="body2"
              fontWeight={600}
              noWrap
              title={file.filename}
              sx={{
                width: '100%',
                textAlign: 'center',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}
            >
              {file.filename}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
              {file.formattedSize}
            </Typography>
          </CardActionArea>
          <Stack
            direction="row"
            justifyContent="center"
            spacing={0.5}
            sx={{ py: 1, px: 1, borderTop: 1, borderColor: 'divider' }}
          >
            <FileActions
              file={file}
              onDownload={onDownload}
              onDelete={onDelete}
            />
          </Stack>
        </Card>
      ))}
    </Box>
  );
}
