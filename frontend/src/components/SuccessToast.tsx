import { Alert, Snackbar } from '@mui/material';

export interface SuccessToastProps {
  message: string;
  onClose: () => void;
  autoHideDuration?: number;
}

/** The shared bottom-center success snackbar (filled green alert). */
export default function SuccessToast({ message, onClose, autoHideDuration = 3000 }: SuccessToastProps) {
  return (
    <Snackbar
      open={message.length > 0}
      autoHideDuration={autoHideDuration}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    >
      <Alert onClose={onClose} severity="success" variant="filled" sx={{ width: '100%' }}>
        {message}
      </Alert>
    </Snackbar>
  );
}
