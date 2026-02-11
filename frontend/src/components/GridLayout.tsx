import React from 'react';
import { Box, Card, CardActionArea, CircularProgress, Stack, Typography } from '@mui/material';
import { FileActions } from './File';
import type { DriveFile } from './File';
import { FolderIcon } from './Folder';
import type { DriveFolder } from './Folder';
import { DynamicRenderedIcon } from './DynamicRenderedIcon';
import { ImageThumbnail } from './ImageThumbnail';
import { isImageFilename } from '../service/fileUtils';

export type GridSize = 'small' | 'medium' | 'large';

export const GRID_SIZE_CONFIG: Record<
  GridSize,
  { minColumnWidth: number; gap: number; mediaHeight: number; iconFontSize: number; padding: number }
> = {
  small: { minColumnWidth: 100, gap: 1, mediaHeight: 64, iconFontSize: 32, padding: 1 },
  medium: { minColumnWidth: 140, gap: 2, mediaHeight: 100, iconFontSize: 48, padding: 2 },
  large: { minColumnWidth: 180, gap: 2.5, mediaHeight: 128, iconFontSize: 56, padding: 2.5 }
};

export interface GridLayoutProps {
  files: DriveFile[];
  folders?: DriveFolder[];
  loading?: boolean;
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
  onFolderClick?: (folder: DriveFolder) => void;
  /** Required for image thumbnails; if provided, image files will show a preview. */
  getDownloadUrl?: (fileId: string) => Promise<string | undefined | null>;
  /** Card size in the grid. */
  gridSize?: GridSize;
}

export function GridLayout({
  files,
  folders = [],
  loading = false,
  onDownload,
  onDelete,
  onFolderClick,
  getDownloadUrl,
  gridSize = 'medium'
}: GridLayoutProps): React.ReactElement {
  const config = GRID_SIZE_CONFIG[gridSize];

  if (loading) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ py: 6 }}>
        <CircularProgress size={32} />
      </Stack>
    );
  }

  if (files.length === 0 && folders.length === 0) {
    return (
      <Stack alignItems="center" justifyContent="center" sx={{ py: 4 }}>
        <Typography variant="body1" color="text.secondary">
          No files or folders yet. Upload something or create a folder.
        </Typography>
      </Stack>
    );
  }

  const iconProps = {
    sx: { fontSize: config.iconFontSize, color: 'action.active', mb: 1 },
    'aria-hidden': true
  } as const;

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${config.minColumnWidth}px, 1fr))`,
        gap: config.gap
      }}
    >
      {folders.map((folder) => (
        <Card
          key={folder.folderId}
          variant="outlined"
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            borderRadius: 2
          }}
        >
          <CardActionArea
            onClick={() => onFolderClick?.(folder)}
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'flex-start',
              p: config.padding,
              '&.Mui-focusVisible': { outline: '2px solid', outlineColor: 'primary.main' }
            }}
          >
            <Box
              sx={{
                width: '100%',
                height: config.mediaHeight,
                minHeight: config.mediaHeight,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mb: 1
              }}
            >
              <FolderIcon size={config.iconFontSize} />
            </Box>
            <Typography
              variant="body2"
              fontWeight={600}
              noWrap
              title={folder.name}
              sx={{
                width: '100%',
                textAlign: 'center',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}
            >
              {folder.name}
            </Typography>
          </CardActionArea>
        </Card>
      ))}
      {files.map((file) => (
        <Card
          key={file.fileId}
          variant="outlined"
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            borderRadius: 2
          }}
        >
          <CardActionArea
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'flex-start',
              p: config.padding,
              '&.Mui-focusVisible': { outline: '2px solid', outlineColor: 'primary.main' }
            }}
          >
            <Box
              sx={{
                width: '100%',
                height: config.mediaHeight,
                minHeight: config.mediaHeight,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mb: 1
              }}
            >
              {getDownloadUrl && isImageFilename(file.filename) ? (
                <ImageThumbnail
                  fileId={file.fileId}
                  filename={file.filename}
                  getDownloadUrl={getDownloadUrl}
                  height={config.mediaHeight}
                />
              ) : (
                <DynamicRenderedIcon filename={file.filename} iconProps={iconProps} />
              )}
            </Box>
            <Typography
              variant="body2"
              fontWeight={600}
              noWrap
              title={file.filename}
              sx={{
                width: '100%',
                textAlign: 'center',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}
            >
              {file.filename}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
              {file.formattedSize}
            </Typography>
          </CardActionArea>
          <Stack
            direction="row"
            justifyContent="center"
            spacing={0.5}
            sx={{ py: 1, px: 1, borderTop: 1, borderColor: 'divider' }}
          >
            <FileActions
              file={file}
              onDownload={onDownload}
              onDelete={onDelete}
            />
          </Stack>
        </Card>
      ))}
    </Box>
  );
}
