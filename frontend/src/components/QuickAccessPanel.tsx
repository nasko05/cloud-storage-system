import React from 'react';
import { Box, Button, IconButton, List, ListItem, ListItemText, Paper, Stack, Typography } from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import type { FileAccessRecord } from '../hooks/useFileAccessHistory';

interface QuickAccessPanelProps {
  recentFiles: FileAccessRecord[];
  onOpenFile: (record: FileAccessRecord) => void;
  onRemoveFile: (record: FileAccessRecord) => void;
}

export function QuickAccessPanel({
  recentFiles,
  onOpenFile,
  onRemoveFile
}: QuickAccessPanelProps): React.ReactElement | null {
  if (recentFiles.length === 0) {
    return null;
  }

  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: '16px',
        boxShadow: '0 1px 3px rgba(18, 22, 39, 0.06), 0 10px 30px rgba(18, 22, 39, 0.05)',
        px: 2,
        py: 1.5
      }}
    >
      <Box>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
          Recent
        </Typography>
        <List dense disablePadding>
          {recentFiles.map((record) => (
            <ListItem
              key={`recent-${record.fileId}`}
              disablePadding
              secondaryAction={
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <Button size="small" onClick={() => onOpenFile(record)}>
                    Open
                  </Button>
                  <IconButton
                    size="small"
                    aria-label={`Remove ${record.filename} from recent files`}
                    onClick={() => onRemoveFile(record)}
                  >
                    <CloseRoundedIcon fontSize="small" />
                  </IconButton>
                </Stack>
              }
            >
              <ListItemText
                primary={record.filename}
                secondary={`Last opened ${new Date(record.lastAccessedAt).toLocaleString()}`}
              />
            </ListItem>
          ))}
        </List>
      </Box>
    </Paper>
  );
}
