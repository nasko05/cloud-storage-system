import React, { useEffect, useState } from 'react';
import { Box, Typography } from '@mui/material';
import mammoth from 'mammoth';
import { sanitizeHtml } from './sanitizeHtml';

interface Props {
  data: ArrayBuffer;
}

/** Renders a .docx as sanitised HTML via mammoth. Ported from the space-io
 *  editor (the HTML is run through sanitizeHtml before it reaches the DOM). */
export default function DocxRenderer({ data }: Props): React.ReactElement {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await mammoth.convertToHtml({ arrayBuffer: data.slice(0) });
        if (!cancelled) setHtml(sanitizeHtml(result.value));
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'failed to render DOCX');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [data]);

  if (error) {
    return (
      <Typography color="error" sx={{ textAlign: 'center', py: 4 }}>
        {error}
      </Typography>
    );
  }
  if (html === null) {
    return (
      <Typography color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
        Rendering…
      </Typography>
    );
  }
  return (
    <Box sx={{ py: 3, px: { xs: 1, sm: 2 } }}>
      <Box
        sx={{
          maxWidth: 760,
          mx: 'auto',
          p: { xs: 2.5, sm: 5 },
          bgcolor: 'background.paper',
          boxShadow: '0 1px 6px rgba(0,0,0,0.12)',
          fontFamily: 'Georgia, "Times New Roman", serif',
          color: 'text.primary',
          '& h1, & h2, & h3, & h4': { mt: 2, mb: 1, lineHeight: 1.3 },
          '& p': { my: 1, lineHeight: 1.7 },
          '& ul, & ol': { pl: 3, my: 1 },
          '& li': { my: 0.5 },
          '& table': { borderCollapse: 'collapse', my: 2, width: '100%' },
          '& td, & th': { border: '1px solid', borderColor: 'divider', p: 1 },
          '& img': { maxWidth: '100%', height: 'auto' },
          '& a': { color: 'primary.main' }
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </Box>
  );
}
