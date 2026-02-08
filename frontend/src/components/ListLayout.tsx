import React from 'react';
import { Box, CircularProgress, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import type { GridColDef } from '@mui/x-data-grid';
import { DensitySelectorToolbar } from './DensitySelectorToolbar';
import type { FileGridRow } from './File';

export interface ListLayoutProps {
  rows: FileGridRow[];
  columns: GridColDef<FileGridRow>[];
  loading?: boolean;
}

export function ListLayout({ rows, columns, loading = false }: ListLayoutProps): React.ReactElement {
  return (
    <Box sx={{ width: '100%' }}>
      <DataGrid
        rows={rows}
        columns={columns}
        autoHeight
        loading={loading}
        disableRowSelectionOnClick
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
                No files yet. Upload something to get started.
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
