import React from 'react';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import FolderRoundedIcon from '@mui/icons-material/FolderRounded';
import { IconButton, Stack, Tooltip, Typography } from '@mui/material';
import type { DriveFolder } from '../types/drive';

export interface FolderItemProps {
  folder: DriveFolder;
}

/** List-style row: folder icon + name. */
export function FolderItem({ folder }: FolderItemProps): React.ReactElement {
  return (
    <Stack direction="row" alignItems="center" spacing={1.5} minWidth={0}>
      <FolderRoundedIcon sx={{ fontSize: 28, color: 'warning.main', flexShrink: 0 }} />
      <Typography fontWeight={600} noWrap title={folder.name}>
        {folder.name}
      </Typography>
    </Stack>
  );
}

export interface FolderIconProps {
  /** Icon font size (px). */
  size?: number;
  /** MUI color token or hex. */
  color?: string;
}

/** Standalone folder icon for grid cards or toolbars. */
export function FolderIcon({ size = 48, color = 'warning.main' }: FolderIconProps): React.ReactElement {
  return <FolderRoundedIcon sx={{ fontSize: size, color }} aria-hidden />;
}

export interface FolderActionsProps {
  folder: DriveFolder;
  onDownload: (folder: DriveFolder) => void;
  onDelete?: (folder: DriveFolder) => void;
}

/** Action buttons for a folder (download as ZIP, optional delete). */
export function FolderActions({ folder, onDownload, onDelete }: FolderActionsProps): React.ReactElement {
  return (
    <Stack direction="row" spacing={0.5}>
      <Tooltip title="Download as ZIP">
        <IconButton size="small" color="primary" onClick={() => onDownload(folder)}>
          <DownloadRoundedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      {onDelete && (
        <Tooltip title="Delete folder">
          <IconButton size="small" color="error" onClick={() => onDelete(folder)}>
            <DeleteOutlineRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  );
}
