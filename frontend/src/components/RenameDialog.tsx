import React, { useEffect, useState } from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField
} from '@mui/material';
import type { DriveFile } from './File';
import type { DriveFolder } from './Folder';

export type RenameTarget =
  | { type: 'file'; file: DriveFile }
  | { type: 'folder'; folder: DriveFolder }
  | null;

export interface RenameDialogProps {
  target: RenameTarget;
  onClose: () => void;
  onSubmit: (newName: string) => void;
}

export function RenameDialog({
  target,
  onClose,
  onSubmit
}: RenameDialogProps): React.ReactElement {
  const currentName =
    target?.type === 'file'
      ? target.file.filename
      : target?.type === 'folder'
        ? target.folder.name
        : '';

  const [name, setName] = useState(currentName);

  // Reset name when target changes
  useEffect(() => {
    setName(currentName);
  }, [currentName]);

  const handleSubmit = (): void => {
    const trimmed = name.trim();
    if (trimmed && trimmed !== currentName) {
      onSubmit(trimmed);
    }
    onClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <Dialog open={target !== null} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        Rename {target?.type === 'folder' ? 'folder' : 'file'}
      </DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          fullWidth
          label="New name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={handleKeyDown}
          sx={{ mt: 1 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={!name.trim() || name.trim() === currentName}
        >
          Rename
        </Button>
      </DialogActions>
    </Dialog>
  );
}
