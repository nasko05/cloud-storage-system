import React from 'react';
import {
  Divider,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem
} from '@mui/material';
import EditRoundedIcon from '@mui/icons-material/EditRounded';
import DriveFileMoveRoundedIcon from '@mui/icons-material/DriveFileMoveRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import type { DriveFile } from './File';
import type { DriveFolder } from './Folder';

export type ContextMenuTarget =
  | { type: 'file'; file: DriveFile }
  | { type: 'folder'; folder: DriveFolder }
  | null;

export interface ContextMenuPosition {
  mouseX: number;
  mouseY: number;
}

export interface ContextMenuProps {
  target: ContextMenuTarget;
  position: ContextMenuPosition | null;
  /** Number of selected items (show bulk label when > 1). */
  selectedCount?: number;
  onClose: () => void;
  onRename: () => void;
  onMoveTo: () => void;
  onDownload: () => void;
  onDelete: () => void;
}

export function ContextMenu({
  target,
  position,
  selectedCount = 0,
  onClose,
  onRename,
  onMoveTo,
  onDownload,
  onDelete
}: ContextMenuProps): React.ReactElement | null {
  const open = target !== null && position !== null;
  const isBulk = selectedCount > 1;
  const isFile = target?.type === 'file';

  return (
    <Menu
      open={open}
      onClose={onClose}
      anchorReference="anchorPosition"
      anchorPosition={position ? { top: position.mouseY, left: position.mouseX } : undefined}
      slotProps={{
        paper: {
          sx: { minWidth: 180, borderRadius: 2 }
        }
      }}
    >
      {!isBulk && (
        <MenuItem
          onClick={() => {
            onClose();
            onRename();
          }}
        >
          <ListItemIcon>
            <EditRoundedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Rename</ListItemText>
        </MenuItem>
      )}
      <MenuItem
        onClick={() => {
          onClose();
          onMoveTo();
        }}
      >
        <ListItemIcon>
          <DriveFileMoveRoundedIcon fontSize="small" />
        </ListItemIcon>
        <ListItemText>{isBulk ? `Move ${selectedCount} items...` : 'Move to...'}</ListItemText>
      </MenuItem>
      {isFile && !isBulk && (
        <MenuItem
          onClick={() => {
            onClose();
            onDownload();
          }}
        >
          <ListItemIcon>
            <DownloadRoundedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Download</ListItemText>
        </MenuItem>
      )}
      <Divider />
      <MenuItem
        onClick={() => {
          onClose();
          onDelete();
        }}
        sx={{ color: 'error.main' }}
      >
        <ListItemIcon>
          <DeleteOutlineRoundedIcon fontSize="small" color="error" />
        </ListItemIcon>
        <ListItemText>{isBulk ? `Delete ${selectedCount} items` : 'Delete'}</ListItemText>
      </MenuItem>
    </Menu>
  );
}
