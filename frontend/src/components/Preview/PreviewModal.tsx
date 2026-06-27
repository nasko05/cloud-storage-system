import React, { lazy, Suspense, useEffect, useState } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import DownloadRoundedIcon from '@mui/icons-material/DownloadRounded';
import type { DriveFile } from '../../types/drive';
import { previewKind } from '../../service/fileUtils';

// Heavy renderers (pdf.js, mammoth) are split out so they only load when a
// PDF/DOCX is actually opened.
const PdfRenderer = lazy(() => import('./PdfRenderer'));
const DocxRenderer = lazy(() => import('./DocxRenderer'));

type State =
  | { status: 'loading' }
  | { status: 'url'; url: string }
  | { status: 'bytes'; data: ArrayBuffer }
  | { status: 'error'; message: string }
  | { status: 'unsupported' };

export interface PreviewModalProps {
  /** The file to preview; null keeps the dialog closed. */
  file: DriveFile | null;
  onClose: () => void;
  getDownloadUrl: (fileId: string) => Promise<string | undefined | null>;
  onDownload: (file: DriveFile) => void;
}

export function PreviewModal({
  file,
  onClose,
  getDownloadUrl,
  onDownload
}: PreviewModalProps): React.ReactElement {
  const [state, setState] = useState<State>({ status: 'loading' });
  const kind = file ? previewKind(file.filename) : null;

  useEffect(() => {
    if (!file) return;
    const k = previewKind(file.filename);
    if (k == null) {
      setState({ status: 'unsupported' });
      return;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    (async () => {
      try {
        const url = await getDownloadUrl(file.fileId);
        if (cancelled) return;
        if (!url) {
          setState({ status: 'error', message: 'Could not get a download link for this file.' });
          return;
        }
        // Images and video stream straight from the signed URL.
        if (k === 'image' || k === 'video') {
          setState({ status: 'url', url });
          return;
        }
        // PDF/DOCX need the bytes in memory for the renderer.
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Download failed (${res.status})`);
        const data = await res.arrayBuffer();
        if (!cancelled) setState({ status: 'bytes', data });
      } catch (err) {
        if (!cancelled) {
          setState({
            status: 'error',
            message: err instanceof Error ? err.message : 'Could not load the file.'
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [file, getDownloadUrl]);

  const downloadFallback = file ? (
    <Button
      variant="outlined"
      startIcon={<DownloadRoundedIcon />}
      onClick={() => onDownload(file)}
    >
      Download
    </Button>
  ) : null;

  return (
    <Dialog
      open={file !== null}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{ sx: { height: '85vh', borderRadius: 2 } }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1.25 }}>
        <Typography
          variant="subtitle1"
          fontWeight={600}
          noWrap
          title={file?.filename}
          sx={{ flex: 1, minWidth: 0 }}
        >
          {file?.filename}
        </Typography>
        {file && (
          <Button size="small" startIcon={<DownloadRoundedIcon />} onClick={() => onDownload(file)}>
            Download
          </Button>
        )}
        <IconButton onClick={onClose} size="small" aria-label="Close preview">
          <CloseRoundedIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0, bgcolor: 'grey.100', overflow: 'auto' }}>
        {state.status === 'loading' && (
          <Stack alignItems="center" justifyContent="center" sx={{ height: '100%', py: 6 }}>
            <CircularProgress />
          </Stack>
        )}
        {state.status === 'error' && (
          <Stack alignItems="center" justifyContent="center" spacing={1.5} sx={{ height: '100%', py: 6 }}>
            <Typography color="error">{state.message}</Typography>
            {downloadFallback}
          </Stack>
        )}
        {state.status === 'unsupported' && (
          <Stack alignItems="center" justifyContent="center" spacing={1.5} sx={{ height: '100%', py: 6 }}>
            <Typography color="text.secondary">No in-app preview for this file type.</Typography>
            {downloadFallback}
          </Stack>
        )}
        {state.status === 'url' && kind === 'image' && (
          <Stack alignItems="center" justifyContent="center" sx={{ minHeight: '100%', p: 2 }}>
            <Box
              component="img"
              src={state.url}
              alt={file?.filename}
              sx={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
            />
          </Stack>
        )}
        {state.status === 'url' && kind === 'video' && (
          <Stack alignItems="center" justifyContent="center" sx={{ minHeight: '100%', p: 2 }}>
            <Box
              component="video"
              src={state.url}
              controls
              preload="metadata"
              sx={{ maxWidth: '100%', maxHeight: '100%' }}
            />
          </Stack>
        )}
        {state.status === 'bytes' && (
          <Suspense
            fallback={
              <Stack alignItems="center" justifyContent="center" sx={{ height: '100%', py: 6 }}>
                <CircularProgress />
              </Stack>
            }
          >
            {kind === 'pdf' && <PdfRenderer data={state.data} />}
            {kind === 'docx' && <DocxRenderer data={state.data} />}
          </Suspense>
        )}
      </DialogContent>
    </Dialog>
  );
}
