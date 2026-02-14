import React from 'react';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import {
  IconButton,
  Stack,
  Tooltip,
  Typography
} from '@mui/material';
import type { FileShape, FileGridRow } from '../types/drive';

// Re-export types so existing imports from './File' keep working
export type { FileShape, FileGridRow } from '../types/drive';
export type { DriveListRow } from '../types/drive';

export class DriveFile {
  public readonly fileId: string;
  public readonly filename: string;
  public readonly size: number;
  public readonly createdAt: string;
  public constructor(fileId: string, filename: string, size: number, createdAt: string) {
    this.fileId = fileId;
    this.filename = filename;
    this.size = size;
    this.createdAt = createdAt;
  }

  public static fromUnknown(value: unknown): DriveFile | null {
    if (!value || typeof value !== 'object') {
      return null;
    }

    const candidate = value as Partial<FileShape>;
    if (
      typeof candidate.fileId !== 'string' ||
      typeof candidate.filename !== 'string' ||
      typeof candidate.size !== 'number' ||
      typeof candidate.createdAt !== 'string'
    ) {
      return null;
    }

    return new DriveFile(candidate.fileId, candidate.filename, candidate.size, candidate.createdAt);
  }

  public get formattedSize(): string {
    if (this.size < 1024) {
      return `${this.size} B`;
    }

    if (this.size < 1024 * 1024) {
      return `${(this.size / 1024).toFixed(1)} KB`;
    }

    return `${(this.size / (1024 * 1024)).toFixed(1)} MB`;
  }

  public toGridRow(): FileGridRow {
    return {
      id: this.fileId,
      file: this
    };
  }
}

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
    <Stack spacing={0.5}>
      <Typography fontWeight={600} noWrap title={file.filename}>
        {file.filename}
      </Typography>
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
