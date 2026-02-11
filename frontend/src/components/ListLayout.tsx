import React from 'react';
import { Box, CircularProgress, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef } from '@mui/x-data-grid';
import { DensitySelectorToolbar } from './DensitySelectorToolbar';
import type { DriveFolder } from './Folder';
import type { DriveListRow } from './File';

export interface ListLayoutProps {
  /** Unified rows: folders and files in one list. */
  rows: DriveListRow[];
  columns: GridColDef<DriveListRow>[];
  loading?: boolean;
  /** When set, clicking a folder row opens that folder (navigates). */
  onFolderClick?: (folder: DriveFolder) => void;
}

export function ListLayout({
  rows,
  columns,
  loading = false,
  onFolderClick
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

  return (
    <Box sx={{ width: '100%' }}>
      <DataGrid
        rows={rows}
        columns={columns}
        autoHeight
        loading={loading}
        disableRowSelectionOnClick
        onRowClick={handleRowClick}
        pageSizeOptions={[5, 10, 20]}
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
