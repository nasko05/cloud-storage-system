import React from 'react';
import { Box, Button, Divider, List, ListItem, ListItemText, Paper, Stack, Typography } from '@mui/material';
import type { FileAccessRecord } from '../hooks/useFileAccessHistory';

interface QuickAccessPanelProps {
  recentFiles: FileAccessRecord[];
  frequentFiles: FileAccessRecord[];
  onOpenFile: (record: FileAccessRecord) => void;
}

export function QuickAccessPanel({
  recentFiles,
  frequentFiles,
  onOpenFile
}: QuickAccessPanelProps): React.ReactElement | null {
  if (recentFiles.length === 0 && frequentFiles.length === 0) {
    return null;
  }

  return (
    <Paper elevation={0} sx={{ borderRadius: 0, border: 1, borderColor: 'divider', p: 1.25 }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.25}
        divider={<Divider orientation="vertical" flexItem />}
      >
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
            Recent
          </Typography>
          <List dense disablePadding>
            {recentFiles.map((record) => (
              <ListItem
                key={`recent-${record.fileId}`}
                disablePadding
                secondaryAction={
                  <Button size="small" onClick={() => onOpenFile(record)}>
                    Open
                  </Button>
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
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
            Quick access
          </Typography>
          <List dense disablePadding>
            {frequentFiles.map((record) => (
              <ListItem
                key={`frequent-${record.fileId}`}
                disablePadding
                secondaryAction={
                  <Button size="small" onClick={() => onOpenFile(record)}>
                    Open
                  </Button>
                }
              >
                <ListItemText
                  primary={record.filename}
                  secondary={`${record.accessCount} access${record.accessCount === 1 ? '' : 'es'}`}
                />
              </ListItem>
            ))}
          </List>
        </Box>
      </Stack>
    </Paper>
  );
}
