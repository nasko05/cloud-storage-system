import React from 'react';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import {
  Button,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography
} from '@mui/material';
import type {
  GridColDef,
  GridRenderCellParams,
  GridSortCellParams
} from '@mui/x-data-grid';
import { getExtension } from '../service/fileUtils';
import type { DriveFolder } from './Folder';
import { FolderItem } from './Folder';

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

/** Unified row for list view: folders and files in one grid. */
export type DriveListRow =
  | { id: string; type: 'file'; file: DriveFile }
  | { id: string; type: 'folder'; folder: DriveFolder };

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

interface ListColumnFactoryInput {
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
  onFolderClick: (folder: DriveFolder) => void;
}

/** Put folders after files when sorting by size/date/extension. */
function listRowSortFoldersLast(
  vA: unknown,
  vB: unknown,
  cellParams1: GridSortCellParams<unknown>,
  cellParams2: GridSortCellParams<unknown>
): number {
  const rowA = cellParams1.api.getRow(cellParams1.id) as DriveListRow;
  const rowB = cellParams2.api.getRow(cellParams2.id) as DriveListRow;
  const aIsFolder = rowA?.type === 'folder';
  const bIsFolder = rowB?.type === 'folder';
  if (aIsFolder && !bIsFolder) return 1;
  if (!aIsFolder && bIsFolder) return -1;
  if (aIsFolder && bIsFolder) return 0;
  const a = vA as number | string | Date;
  const b = vB as number | string | Date;
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return a < b ? -1 : a > b ? 1 : 0;
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
        valueGetter: (params) => params.row.file.filename,
        renderCell: (params: GridRenderCellParams<FileGridRow>) =>
          React.createElement(FileItem, { file: params.row.file })
      },
      {
        field: 'fileextension',
        headerName: 'Extension',
        flex: 0.45,
        sortable: true,
        valueGetter: (params) => getExtension(params.row.file.filename) ?? 'Unknown',
        renderCell: (params: GridRenderCellParams<FileGridRow>) =>
          React.createElement(Chip, {
            label: params.value ?? 'Unknown',
            size: 'small'
          })
      },
      {  
        field: 'size',
        headerName: 'Size',
        flex: 0.45,
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

export class ListColumnsFactory {
  /** Columns for unified list (folders + files). Folders have no size/extension; sort by name only for folders. */
  public static create(input: ListColumnFactoryInput): GridColDef<DriveListRow>[] {
    return [
      {
        field: 'name',
        headerName: 'Name',
        flex: 1.6,
        sortable: true,
        valueGetter: (params) =>
          params.row.type === 'folder' ? params.row.folder.name : params.row.file.filename,
        renderCell: (params: GridRenderCellParams<DriveListRow>) =>
          params.row.type === 'folder'
            ? React.createElement(FolderItem, { folder: params.row.folder })
            : React.createElement(FileItem, { file: params.row.file })
      },
      {
        field: 'extension',
        headerName: 'Extension',
        flex: 0.45,
        sortable: true,
        valueGetter: (params) =>
          params.row.type === 'file' ? getExtension(params.row.file.filename) ?? '' : '',
        sortComparator: listRowSortFoldersLast,
        renderCell: (params: GridRenderCellParams<DriveListRow>) =>
          params.row.type === 'file' && params.value
            ? React.createElement(Chip, { label: params.value, size: 'small' })
            : '—'
      },
      {
        field: 'size',
        headerName: 'Size',
        flex: 0.45,
        type: 'number',
        valueGetter: (params) => (params.row.type === 'file' ? params.row.file.size : null),
        sortComparator: listRowSortFoldersLast,
        renderCell: (params: GridRenderCellParams<DriveListRow>) =>
          params.row.type === 'file'
            ? React.createElement(Chip, {
                label: params.row.file.formattedSize,
                size: 'small',
                variant: 'outlined'
              })
            : '—'
      },
      {
        field: 'date',
        headerName: 'Date',
        width: 140,
        type: 'dateTime',
        valueGetter: (params) =>
          params.row.type === 'file' ? new Date(params.row.file.createdAt) : null,
        sortComparator: listRowSortFoldersLast,
        renderCell: (params: GridRenderCellParams<DriveListRow>) =>
          params.row.type === 'file'
            ? React.createElement(Chip, {
                label: new Date(params.row.file.createdAt).toLocaleString(),
                size: 'small',
                variant: 'outlined'
              })
            : '—'
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
        renderCell: (params: GridRenderCellParams<DriveListRow>) => {
          if (params.row.type === 'folder') {
            const folder = params.row.folder;
            return React.createElement(
              Button,
              {
                size: 'small',
                variant: 'text',
                onClick: () => input.onFolderClick(folder)
              },
              'Open'
            );
          }
          return React.createElement(FileActions, {
            file: params.row.file,
            onDownload: input.onDownload,
            onDelete: input.onDelete
          });
        }
      }
    ];
  }
}
