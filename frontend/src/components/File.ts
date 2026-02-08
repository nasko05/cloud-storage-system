import React from 'react';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import {
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography
} from '@mui/material';
import type { GridColDef, GridRenderCellParams } from '@mui/x-data-grid';

export interface FileShape {
  fileId: string;
  filename: string;
  size: number;
  createdAt: string;
}

export interface FileGridRow {
  id: string;
  file: DriveFile;
}

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

interface FileItemProps {
  file: DriveFile;
}

interface FileActionsProps {
  file: DriveFile;
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
}

interface FileColumnFactoryInput {
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
}

export class FileItem extends React.PureComponent<FileItemProps> {
  public render(): React.ReactNode {
    return React.createElement(
      Stack,
      { spacing: 0.5 },
      React.createElement(
        Typography,
        { fontWeight: 600, noWrap: true, title: this.props.file.filename },
        this.props.file.filename
      )
    );
  }
}

export class FileActions extends React.PureComponent<FileActionsProps> {
  public render(): React.ReactNode {
    return React.createElement(
      Stack,
      { direction: 'row', spacing: 0.5 },
      React.createElement(
        Tooltip,
        {
          title: 'Download',
          children: React.createElement(
            IconButton,
            {
              size: 'small',
              color: 'primary',
              onClick: () => this.props.onDownload(this.props.file)
            },
            React.createElement(DownloadRoundedIcon, { fontSize: 'small' })
          )
        }
      ),
      React.createElement(
        Tooltip,
        {
          title: 'Delete',
          children: React.createElement(
            IconButton,
            {
              size: 'small',
              color: 'error',
              onClick: () => this.props.onDelete(this.props.file)
            },
            React.createElement(DeleteOutlineRoundedIcon, { fontSize: 'small' })
          )
        }
      )
    );
  }
}

export class FileColumnsFactory {
  public static create(input: FileColumnFactoryInput): GridColDef<FileGridRow>[] {
    return [
      {
        field: 'filename',
        headerName: 'File',
        flex: 1.6,
        sortable: true,
        renderCell: (params: GridRenderCellParams<FileGridRow>) =>
          React.createElement(FileItem, { file: params.row.file })
      },
      {
        field: 'size',
        headerName: 'Size',
        width: 140,
        type: 'number',
        valueGetter: (params) => params.row.file.size,
        renderCell: (params: GridRenderCellParams<FileGridRow>) =>
          React.createElement(Chip, {
            label: params.row.file.formattedSize,
            size: 'small',
            variant: 'outlined'
          })
      },
      {
        field: 'date',
        headerName: 'Date',
        width: 140,
        type: 'dateTime',
        valueGetter: (params) => new Date(params.row.file.createdAt),
        renderCell: (params: GridRenderCellParams<FileGridRow>) =>
          React.createElement(Chip, {
            label: new Date(params.row.file.createdAt).toLocaleString(),
            size: 'small',
            variant: 'outlined'
          })
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 130,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        align: 'right',
        headerAlign: 'right',
        renderCell: (params: GridRenderCellParams<FileGridRow>) =>
          React.createElement(FileActions, {
            file: params.row.file,
            onDownload: input.onDownload,
            onDelete: input.onDelete
          })
      }
    ];
  }
}
