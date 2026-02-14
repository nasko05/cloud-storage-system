import React, { useState } from 'react';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import RadioButtonUncheckedRoundedIcon from '@mui/icons-material/RadioButtonUncheckedRounded';
import {
  Box,
  Card,
  CardActionArea,
  Checkbox,
  CircularProgress,
  Stack,
  Typography
} from '@mui/material';
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
  selectedItems?: Set<string>;
  onDownload: (file: DriveFile) => void;
  onDelete: (file: DriveFile) => void;
  onFolderClick?: (folder: DriveFolder) => void;
  onDeleteFolder?: (folder: DriveFolder) => void;
  onContextMenu?: (
    e: React.MouseEvent,
    target: { type: 'file'; file: DriveFile } | { type: 'folder'; folder: DriveFolder }
  ) => void;
  onSelectionChange?: (id: string, multi: boolean) => void;
  onDrop?: (
    targetFolder: DriveFolder,
    dragData: { type: 'file' | 'folder'; id: string }
  ) => void;
  /** Required for image thumbnails; if provided, image files will show a preview. */
  getDownloadUrl?: (fileId: string) => Promise<string | undefined | null>;
  /** Card size in the grid. */
  gridSize?: GridSize;
}

export function GridLayout({
  files,
  folders = [],
  loading = false,
  selectedItems,
  onDownload,
  onDelete,
  onFolderClick,
  onDeleteFolder,
  onContextMenu,
  onSelectionChange,
  onDrop,
  getDownloadUrl,
  gridSize = 'medium'
}: GridLayoutProps): React.ReactElement {
  const config = GRID_SIZE_CONFIG[gridSize];
  const [dragOverId, setDragOverId] = useState<string | null>(null);

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

  const handleDragStart = (
    e: React.DragEvent,
    type: 'file' | 'folder',
    id: string
  ): void => {
    e.dataTransfer.setData(
      'application/x-drive-item',
      JSON.stringify({ type, id })
    );
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent, folderId: string): void => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverId(folderId);
  };

  const handleDragLeave = (): void => {
    setDragOverId(null);
  };

  const handleDropOnFolder = (
    e: React.DragEvent,
    folder: DriveFolder
  ): void => {
    e.preventDefault();
    setDragOverId(null);
    try {
      const raw = e.dataTransfer.getData('application/x-drive-item');
      if (!raw) return;
      const data = JSON.parse(raw) as { type: 'file' | 'folder'; id: string };
      // Don't drop a folder on itself
      if (data.type === 'folder' && data.id === folder.folderId) return;
      onDrop?.(folder, data);
    } catch {
      // ignore malformed drag data
    }
  };

  const isSelected = (id: string): boolean => selectedItems?.has(id) ?? false;

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
          draggable
          onDragStart={(e) => handleDragStart(e, 'folder', folder.folderId)}
          onDragOver={(e) => handleDragOver(e, folder.folderId)}
          onDragLeave={handleDragLeave}
          onDrop={(e) => handleDropOnFolder(e, folder)}
          onContextMenu={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onContextMenu?.(e, { type: 'folder', folder });
          }}
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            borderRadius: 2,
            position: 'relative',
            outline: dragOverId === folder.folderId ? '2px solid' : undefined,
            outlineColor: dragOverId === folder.folderId ? 'primary.main' : undefined,
            bgcolor: dragOverId === folder.folderId ? 'action.hover' : undefined,
            ...(isSelected(folder.folderId) && {
              borderColor: 'primary.main',
              bgcolor: 'primary.50'
            })
          }}
        >
          {onSelectionChange && (
            <Checkbox
              checked={isSelected(folder.folderId)}
              onChange={(e) =>
                onSelectionChange(folder.folderId, e.nativeEvent instanceof MouseEvent && (e.nativeEvent.metaKey || e.nativeEvent.ctrlKey))
              }
              icon={<RadioButtonUncheckedRoundedIcon />}
              checkedIcon={<CheckCircleRoundedIcon />}
              size="small"
              sx={{
                position: 'absolute',
                top: 4,
                left: 4,
                zIndex: 1,
                opacity: isSelected(folder.folderId) ? 1 : 0,
                transition: 'opacity 0.15s',
                '&:hover, .MuiCard-root:hover &': { opacity: 1 }
              }}
              onClick={(e) => e.stopPropagation()}
            />
          )}
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
            {folder.createdAt && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.25 }}
              >
                {new Date(folder.createdAt).toLocaleDateString()}
              </Typography>
            )}
          </CardActionArea>
        </Card>
      ))}
      {files.map((file) => (
        <Card
          key={file.fileId}
          variant="outlined"
          draggable
          onDragStart={(e) => handleDragStart(e, 'file', file.fileId)}
          onContextMenu={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onContextMenu?.(e, { type: 'file', file });
          }}
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            borderRadius: 2,
            position: 'relative',
            ...(isSelected(file.fileId) && {
              borderColor: 'primary.main',
              bgcolor: 'primary.50'
            })
          }}
        >
          {onSelectionChange && (
            <Checkbox
              checked={isSelected(file.fileId)}
              onChange={(e) =>
                onSelectionChange(file.fileId, e.nativeEvent instanceof MouseEvent && (e.nativeEvent.metaKey || e.nativeEvent.ctrlKey))
              }
              icon={<RadioButtonUncheckedRoundedIcon />}
              checkedIcon={<CheckCircleRoundedIcon />}
              size="small"
              sx={{
                position: 'absolute',
                top: 4,
                left: 4,
                zIndex: 1,
                opacity: isSelected(file.fileId) ? 1 : 0,
                transition: 'opacity 0.15s',
                '&:hover, .MuiCard-root:hover &': { opacity: 1 }
              }}
              onClick={(e) => e.stopPropagation()}
            />
          )}
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
