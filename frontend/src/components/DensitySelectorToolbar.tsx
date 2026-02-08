import React from 'react';
import {
  GridToolbarContainer,
  GridToolbarDensitySelector
} from '@mui/x-data-grid';

/**
 * Toolbar slot that shows only the density selector (compact / standard / comfortable).
 * Use as DataGrid slots.toolbar so it runs inside the grid context.
 */
export function DensitySelectorToolbar(): React.ReactElement {
  return (
    <GridToolbarContainer>
      <GridToolbarDensitySelector />
    </GridToolbarContainer>
  );
}
