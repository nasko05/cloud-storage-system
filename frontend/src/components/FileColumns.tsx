/**
 * Column definitions for file/folder data grids (grid view + list view).
 * Uses shared cell renderers to avoid duplication.
 */
import React from 'react';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import { Chip, IconButton, Stack, Tooltip } from '@mui/material';
import type {
  GridColDef,
  GridRenderCellParams,
  GridSortCellParams
} from '@mui/x-data-grid';
import { getExtension } from '../service/fileUtils';
import type { DriveFile } from './File';
import { FileItem, FileActions } from './File';
import { FolderItem } from './Folder';
import type { DriveFolder } from '../types/drive';
import type { FileGridRow, DriveListRow } from '../types/drive';

// ---------------------------------------------------------------------------
// Shared cell renderers
// ---------------------------------------------------------------------------

function ChipCell({ label }: { label: string }): React.ReactElement {
  return <Chip label={label} size="small" />;
}

function OutlinedChipCell({ label }: { label: string }): React.ReactElement {
  return <Chip label={label} size="small" variant="outlined" />;
}

function DateChipCell({ date }: { date: string }): React.ReactElement {
  return <Chip label={new Date(date).toLocaleString()} size="small" variant="outlined" />;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface FileColumnFactoryInput {
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
}

interface ListColumnFactoryInput {
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
  onFolderClick: (folder: DriveFolder) => void;
  onDeleteFolder: (folder: DriveFolder) => void;
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

// ---------------------------------------------------------------------------
// Column factories
// ---------------------------------------------------------------------------

export class FileColumnsFactory {
  public static create(input: FileColumnFactoryInput): GridColDef<FileGridRow>[] {
    return [
      {
        field: 'filename',
        headerName: 'File',
        flex: 1.6,
        sortable: true,
        valueGetter: (params) => params.row.file.filename,
        renderCell: (params: GridRenderCellParams<FileGridRow>) => (
          <FileItem file={params.row.file} />
        )
      },
      {
        field: 'fileextension',
        headerName: 'Extension',
        flex: 0.45,
        sortable: true,
        valueGetter: (params) => getExtension(params.row.file.filename) ?? 'Unknown',
        renderCell: (params: GridRenderCellParams<FileGridRow>) => (
          <ChipCell label={params.value ?? 'Unknown'} />
        )
      },
      {
        field: 'size',
        headerName: 'Size',
        flex: 0.45,
        type: 'number',
        valueGetter: (params) => params.row.file.size,
        renderCell: (params: GridRenderCellParams<FileGridRow>) => (
          <OutlinedChipCell label={params.row.file.formattedSize} />
        )
      },
      {
        field: 'date',
        headerName: 'Date',
        width: 140,
        type: 'dateTime',
        valueGetter: (params) => new Date(params.row.file.createdAt),
        renderCell: (params: GridRenderCellParams<FileGridRow>) => (
          <DateChipCell date={params.row.file.createdAt} />
        )
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
        renderCell: (params: GridRenderCellParams<FileGridRow>) => (
          <FileActions
            file={params.row.file}
            onDownload={input.onDownload}
            onDelete={input.onDelete}
          />
        )
      }
    ];
  }
}

export class ListColumnsFactory {
  /** Columns for unified list (folders + files). */
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
            ? <FolderItem folder={params.row.folder} />
            : <FileItem file={params.row.file} />
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
            ? <ChipCell label={params.value} />
            : <>{'\u2014'}</>
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
            ? <OutlinedChipCell label={params.row.file.formattedSize} />
            : <>{'\u2014'}</>
      },
      {
        field: 'date',
        headerName: 'Date',
        width: 140,
        type: 'dateTime',
        valueGetter: (params) => {
          if (params.row.type === 'file') return new Date(params.row.file.createdAt);
          if (params.row.type === 'folder' && params.row.folder.createdAt)
            return new Date(params.row.folder.createdAt);
          return null;
        },
        sortComparator: listRowSortFoldersLast,
        renderCell: (params: GridRenderCellParams<DriveListRow>) => {
          if (params.row.type === 'file') {
            return <DateChipCell date={params.row.file.createdAt} />;
          }
          if (params.row.type === 'folder' && params.row.folder.createdAt) {
            return <DateChipCell date={params.row.folder.createdAt} />;
          }
          return <>{'\u2014'}</>;
        }
      },
      {
        field: 'actions',
        headerName: 'Actions',
        width: 160,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        align: 'right',
        headerAlign: 'right',
        renderCell: (params: GridRenderCellParams<DriveListRow>) => {
          if (params.row.type === 'folder') {
            const folder = params.row.folder;
            return (
              <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
                <Tooltip title="Delete folder">
                  <IconButton
                    size="small"
                    aria-label="Delete folder"
                    onClick={(e: React.MouseEvent) => {
                      e.stopPropagation();
                      input.onDeleteFolder(folder);
                    }}
                    color="error"
                  >
                    <DeleteOutlineRoundedIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            );
          }
          return (
            <FileActions
              file={params.row.file}
              onDownload={input.onDownload}
              onDelete={input.onDelete}
            />
          );
        }
      }
    ];
  }
}
