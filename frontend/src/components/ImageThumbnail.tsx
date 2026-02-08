import React, { useEffect, useState } from 'react';
import { Box, Skeleton } from '@mui/material';
import InsertDriveFileRoundedIcon from '@mui/icons-material/InsertDriveFileRounded';

export interface ImageThumbnailProps {
  fileId: string;
  filename: string;
  getDownloadUrl: (fileId: string) => Promise<string | undefined | null>;
}

export function ImageThumbnail({
  fileId,
  filename,
  getDownloadUrl
}: ImageThumbnailProps): React.ReactElement {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    getDownloadUrl(fileId)
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
        height: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'action.hover',
        borderRadius: 1
      }}
    >
      <InsertDriveFileRoundedIcon sx={{ fontSize: 48, color: 'action.active' }} aria-hidden />
    </Box>
  );

  if (loading) {
    return (
      <Skeleton
        variant="rectangular"
        width="100%"
        height={100}
        sx={{ borderRadius: 1, mb: 1 }}
      />
    );
  }

  if (error || !url) {
    return <Box sx={{ mb: 1 }}>{placeholder}</Box>;
  }

  return (
    <Box
      component="img"
      src={url}
      alt={filename}
      loading="lazy"
      sx={{
        width: '100%',
        height: 100,
        objectFit: 'cover',
        borderRadius: 1,
        mb: 1,
        display: 'block'
      }}
    />
  );
}
