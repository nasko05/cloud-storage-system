import React, { useEffect, useRef, useState } from 'react';
import { Box, Typography } from '@mui/material';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

interface Props {
  data: ArrayBuffer;
}

/** Renders every page of a PDF to a canvas. Ported from the space-io editor. */
export default function PdfRenderer({ data }: Props): React.ReactElement {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;
    container.innerHTML = '';

    (async () => {
      try {
        const doc = await pdfjsLib.getDocument({ data: data.slice(0) }).promise;
        if (cancelled) {
          doc.destroy();
          return;
        }
        setPageCount(doc.numPages);
        const scale = Math.min(2, window.devicePixelRatio || 1) * 1.2;
        for (let pageNumber = 1; pageNumber <= doc.numPages; pageNumber += 1) {
          if (cancelled) break;
          const page = await doc.getPage(pageNumber);
          const viewport = page.getViewport({ scale });
          const canvas = document.createElement('canvas');
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.style.maxWidth = '100%';
          canvas.style.height = 'auto';
          canvas.style.display = 'block';
          canvas.style.margin = '0 auto 12px';
          canvas.style.boxShadow = '0 1px 6px rgba(0,0,0,0.18)';
          container.appendChild(canvas);
          const context = canvas.getContext('2d');
          if (!context) continue;
          await page.render({ canvasContext: context, viewport, canvas }).promise;
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'failed to render PDF');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [data]);

  return (
    <Box sx={{ p: 2 }}>
      {error && (
        <Typography color="error" sx={{ textAlign: 'center', py: 2 }}>
          {error}
        </Typography>
      )}
      <Box ref={containerRef} />
      {pageCount > 0 && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', textAlign: 'center', py: 1 }}
        >
          {pageCount} {pageCount === 1 ? 'page' : 'pages'}
        </Typography>
      )}
    </Box>
  );
}
