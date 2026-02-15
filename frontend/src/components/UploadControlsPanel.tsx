import React from 'react';
import CreateNewFolderRoundedIcon from '@mui/icons-material/CreateNewFolderRounded';
import CloudUploadRoundedIcon from '@mui/icons-material/CloudUploadRounded';
import { Button, Paper, Stack, Typography } from '@mui/material';

interface UploadControlsPanelProps {
  fileUploadInputRef: React.MutableRefObject<HTMLInputElement | null>;
  loading: boolean;
  isUploading: boolean;
  onUploadFilesChange: (event: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  onOpenFilePicker: () => void;
  onCreateFolder: () => void;
  onCancelUpload: () => void;
}

export function UploadControlsPanel({
  fileUploadInputRef,
  loading,
  isUploading,
  onUploadFilesChange,
  onOpenFilePicker,
  onCreateFolder,
  onCancelUpload
}: UploadControlsPanelProps): React.ReactElement {
  return (
    <Paper elevation={1} sx={{ borderRadius: 3, p: 2.5 }}>
      <input
        ref={fileUploadInputRef}
        type="file"
        hidden
        multiple
        onChange={(event) => {
          void onUploadFilesChange(event);
        }}
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="center" flexWrap="wrap">
        <Button
          variant="contained"
          startIcon={<CloudUploadRoundedIcon />}
          disabled={loading || isUploading}
          onClick={onOpenFilePicker}
        >
          Upload
        </Button>
        <Button
          variant="outlined"
          startIcon={<CreateNewFolderRoundedIcon />}
          onClick={onCreateFolder}
          disabled={loading || isUploading}
        >
          New folder
        </Button>
        {isUploading && (
          <Button variant="text" color="error" onClick={onCancelUpload}>
            Cancel upload
          </Button>
        )}
        <Typography variant="body2" color="text.secondary" sx={{ width: { xs: '100%', sm: 'auto' } }}>
          Shortcuts: `U` upload files, `N` new folder, `R` refresh.
        </Typography>
      </Stack>
    </Paper>
  );
}
