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
import ShareRoundedIcon from '@mui/icons-material/ShareRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import type { ContextMenuTarget, ContextMenuPosition } from '../types/drive';

export type { ContextMenuTarget, ContextMenuPosition } from '../types/drive';

export interface ContextMenuProps {
  target: ContextMenuTarget;
  position: ContextMenuPosition | null;
  /** Number of selected items (show bulk label when > 1). */
  selectedCount?: number;
  /** Show Download item (single file or bulk ZIP). */
  showDownload?: boolean;
  /** Label for Download item: "Download" or "Download as ZIP (N items)". */
  downloadLabel?: string;
  onClose: () => void;
  onRename: () => void;
  onMoveTo: () => void;
  onDownload: () => void;
  onShare: () => void;
  onDelete: () => void;
}

export function ContextMenu({
  target,
  position,
  selectedCount = 0,
  showDownload = false,
  downloadLabel = 'Download',
  onClose,
  onRename,
  onMoveTo,
  onDownload,
  onShare,
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
      {showDownload && (
        <MenuItem
          onClick={() => {
            onClose();
            onDownload();
          }}
        >
          <ListItemIcon>
            <DownloadRoundedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>{downloadLabel}</ListItemText>
        </MenuItem>
      )}
      {isFile && !isBulk && (
        <MenuItem
          onClick={() => {
            onClose();
            onShare();
          }}
        >
          <ListItemIcon>
            <ShareRoundedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Share</ListItemText>
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
