import React from 'react';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import PeopleRoundedIcon from '@mui/icons-material/PeopleRounded';
import LinkRoundedIcon from '@mui/icons-material/LinkRounded';
import {
  IconButton,
  Stack,
  Tooltip,
  Typography
} from '@mui/material';
import type { DriveFile } from '../types/drive';

// Re-export types so existing `import from './File'` still resolves
export type { DriveFile, FileShape, FileGridRow, DriveListRow } from '../types/drive';
export { driveFileFromUnknown, formatFileSize, toFileGridRow } from '../types/drive';

// ---------------------------------------------------------------------------
// Row components
// ---------------------------------------------------------------------------

interface FileItemProps {
  file: DriveFile;
}

interface FileActionsProps {
  file: DriveFile;
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
}

export function FileItem({ file }: FileItemProps): React.ReactElement {
  return (
    <Stack direction="row" alignItems="center" spacing={0.5}>
      <Typography fontWeight={600} noWrap title={file.filename}>
        {file.filename}
      </Typography>
      {file.isShared && (
        <Tooltip title="Shared">
          <PeopleRoundedIcon sx={{ fontSize: 16, color: 'info.main', flexShrink: 0 }} />
        </Tooltip>
      )}
      {file.hasPublicLink && (
        <Tooltip title="Has public link">
          <LinkRoundedIcon sx={{ fontSize: 16, color: 'warning.main', flexShrink: 0 }} />
        </Tooltip>
      )}
    </Stack>
  );
}

export function FileActions({ file, onDownload, onDelete }: FileActionsProps): React.ReactElement {
  return (
    <Stack direction="row" spacing={0.5}>
      <Tooltip title="Download">
        <IconButton size="small" color="primary" onClick={() => onDownload(file)}>
          <DownloadRoundedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title="Delete">
        <IconButton size="small" color="error" onClick={() => onDelete(file)}>
          <DeleteOutlineRoundedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}
