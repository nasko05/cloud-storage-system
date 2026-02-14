import React, { useEffect, useState } from 'react';
import { Box, Skeleton } from '@mui/material';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';
import { getCachedDownloadUrl } from '../service/thumbnailCache';

export interface ImageThumbnailProps {
  fileId: string;
  filename: string;
  getDownloadUrl: (fileId: string) => Promise<string | undefined | null>;
  /** Thumbnail height in px; used when grid size is configurable. */
  height?: number;
}

const DEFAULT_THUMBNAIL_HEIGHT = 100;

export function ImageThumbnail({
  fileId,
  filename,
  getDownloadUrl,
  height = DEFAULT_THUMBNAIL_HEIGHT
}: ImageThumbnailProps): React.ReactElement {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    const fetcher = (id: string) =>
      getDownloadUrl(id).then((u) => u ?? null);
    getCachedDownloadUrl(fileId, fetcher)
      .then((downloadUrl) => {
        if (!cancelled && downloadUrl) setUrl(downloadUrl);
        else if (!cancelled) setError(true);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fileId, getDownloadUrl]);

  const placeholder = (
    <Box
      sx={{
        width: '100%',
        height,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'action.hover',
        borderRadius: 1
      }}
    >
      <InsertDriveFileRoundedIcon sx={{ fontSize: Math.min(48, height * 0.48), color: 'action.active' }} aria-hidden />
    </Box>
  );

  if (loading) {
    return (
      <Skeleton
        variant="rectangular"
        width="100%"
        height={height}
        sx={{ borderRadius: 1 }}
      />
    );
  }

  if (error || !url) {
    return placeholder;
  }

  return (
    <Box
      component="img"
      src={url}
      alt={filename}
      loading="lazy"
      sx={{
        width: '100%',
        height,
        objectFit: 'cover',
        borderRadius: 1,
        display: 'block'
      }}
    />
  );
}
