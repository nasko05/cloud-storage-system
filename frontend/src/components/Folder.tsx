import React from 'react';
import { Stack, Typography } from '@mui/material';
import FolderRoundedIcon from '@mui/icons-material/FolderRounded';

export interface DriveFolder {
  folderId: string;
  name: string;
  path: string;
  /** ISO date string when the folder was created. */
  createdAt?: string;
}

export const FOLDER_ICON_DEFAULT_PROPS = {
  sx: { fontSize: 48, color: 'warning.main', mb: 1 },
  'aria-hidden': true
} as const;

export interface FolderItemProps {
  folder: DriveFolder;
}

/** List-style row: folder icon + name. */
export function FolderItem({ folder }: FolderItemProps): React.ReactElement {
  return React.createElement(
    Stack,
    { direction: 'row', alignItems: 'center', spacing: 1.5, minWidth: 0 },
    React.createElement(
      FolderRoundedIcon,
      { sx: { fontSize: 28, color: 'warning.main', flexShrink: 0 } }
    ),
    React.createElement(
      Typography,
      { fontWeight: 600, noWrap: true, title: folder.name },
      folder.name
    )
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
  return React.createElement(FolderRoundedIcon, {
    sx: { fontSize: size, color },
    'aria-hidden': true
  });
}
