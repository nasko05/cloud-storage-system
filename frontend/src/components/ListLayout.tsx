import React from 'react';
import { Box, CircularProgress, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { DensitySelectorToolbar } from './DensitySelectorToolbar';
import type { DriveFile, DriveFolder, DriveListRow } from '../types/drive';

export interface ListLayoutProps {
  /** Unified rows: folders and files in one list. */
  rows: DriveListRow[];
  columns: GridColDef<DriveListRow>[];
  loading?: boolean;
  selectedItems?: Set<string>;
  /** When set, clicking a folder row opens that folder (navigates). */
  onFolderClick?: (folder: DriveFolder) => void;
  /** Open a file's preview (double-click a file row). */
  onFileOpen?: (file: DriveFile) => void;
  onContextMenu?: (
    e: React.MouseEvent,
    target: { type: 'file'; file: DriveFile } | { type: 'folder'; folder: DriveFolder }
  ) => void;
  onSelectionChange?: (ids: string[]) => void;
}

export function ListLayout({
  rows,
  columns,
  loading = false,
  selectedItems,
  onFolderClick,
  onFileOpen,
  onContextMenu,
  onSelectionChange
}: ListLayoutProps): React.ReactElement {
  const empty = rows.length === 0;

  const handleRowClick = React.useCallback(
    (params: { row: DriveListRow }) => {
      if (params.row.type === 'folder') {
        onFolderClick?.(params.row.folder);
      }
    },
    [onFolderClick]
  );

  const handleRowDoubleClick = React.useCallback(
    (e: React.MouseEvent) => {
      // DataGrid has no onRowDoubleClick, so resolve the row from the DOM the
      // same way the context-menu handler does.
      const target = e.target as HTMLElement;
      const rowEl = target.closest('[data-id]');
      const rowId = rowEl?.getAttribute('data-id');
      if (!rowId) return;
      const row = rows.find((r) => r.id === rowId);
      if (row?.type === 'file') {
        onFileOpen?.(row.file);
      }
    },
    [rows, onFileOpen]
  );

  const handleRowContextMenu = React.useCallback(
    (e: React.MouseEvent) => {
      // DataGrid doesn't expose an onRowContextMenu, so we handle it via
      // the native event on the wrapper. Walk up from e.target to find
      // the row element and its data-id attribute.
      const target = e.target as HTMLElement;
      const rowEl = target.closest('[data-id]');
      if (!rowEl) return;
      const rowId = rowEl.getAttribute('data-id');
      if (!rowId) return;
      const row = rows.find((r) => r.id === rowId);
      if (!row) return;
      e.preventDefault();
      e.stopPropagation();
      if (row.type === 'file') {
        onContextMenu?.(e, { type: 'file', file: row.file });
      } else {
        onContextMenu?.(e, { type: 'folder', folder: row.folder });
      }
    },
    [rows, onContextMenu]
  );

  const selectionModel: GridRowSelectionModel = selectedItems
    ? Array.from(selectedItems)
    : [];

  return (
    <Box
      sx={{ width: '100%', height: '100%', minHeight: 280 }}
      onContextMenu={handleRowContextMenu}
      onDoubleClick={handleRowDoubleClick}
    >
      <DataGrid
        rows={rows}
        columns={columns}
        loading={loading}
        checkboxSelection={!!onSelectionChange}
        disableRowSelectionOnClick={!onSelectionChange}
        rowSelectionModel={selectionModel}
        onRowSelectionModelChange={(newModel) => {
          onSelectionChange?.(newModel as string[]);
        }}
        onRowClick={handleRowClick}
        pageSizeOptions={[5, 10, 20]}
        sx={{
          height: '100%',
          border: 'none',
          '& .MuiDataGrid-columnHeaders': {
            bgcolor: 'transparent',
            borderBottom: '1px solid',
            borderColor: 'divider'
          },
          '& .MuiDataGrid-columnHeaderTitle': {
            fontWeight: 600,
            color: 'text.secondary',
            fontSize: '0.8rem'
          },
          '& .MuiDataGrid-cell': { borderColor: 'divider' },
          '& .MuiDataGrid-footerContainer': { borderColor: 'divider' },
          '& .MuiDataGrid-row.Mui-selected': {
            bgcolor: 'transparent'
          },
          '& .MuiDataGrid-row.Mui-selected:hover': {
            bgcolor: 'action.hover'
          },
          '& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within': {
            outline: 'none'
          },
          '& .MuiDataGrid-columnHeader:focus, & .MuiDataGrid-columnHeader:focus-within': {
            outline: 'none'
          }
        }}
        initialState={{
          pagination: {
            paginationModel: { page: 0, pageSize: 10 }
          }
        }}
        slots={{
          toolbar: DensitySelectorToolbar,
          noRowsOverlay: () => (
            <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
              <Typography variant="body1" color="text.secondary">
                {empty
                  ? 'No files or folders yet. Upload something or create a folder.'
                  : 'No items to show.'}
              </Typography>
            </Stack>
          ),
          loadingOverlay: () => (
            <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
              <CircularProgress size={28} />
            </Stack>
          )
        }}
      />
    </Box>
  );
}
