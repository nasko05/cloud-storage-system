import React, { FormEvent, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography
} from '@mui/material';
import {
  login,
  register,
  confirmRegistration,
  loginWithPasskey,
  passkeySupported
} from '../auth';

type AuthMode = 'login' | 'register' | 'confirm';

export interface AuthFormProps {
  onAuthenticated: (token: string) => void;
}

export function AuthForm({ onAuthenticated }: AuthFormProps): React.ReactElement {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmCode, setConfirmCode] = useState('');
  const [authMode, setAuthMode] = useState<AuthMode>('login');
  const [pendingEmail, setPendingEmail] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const handleLogin = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError('');
    try {
      const authToken = await login(email, password);
      onAuthenticated(authToken);
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Login failed';
      setError(message);
    }
  };

  const handleRegister = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError('');
    setNotice('');
    try {
      const { confirmationRequired } = await register(email, password);
      setPendingEmail(email);
      setPassword('');
      if (confirmationRequired) {
        setAuthMode('confirm');
        setEmail('');
      } else {
        setAuthMode('login');
        setNotice('Account created. You can now log in.');
      }
    } catch (caughtError: unknown) {
      const message = caughtError instanceof Error ? caughtError.message : 'Registration failed';
      setError(message);
    }
  };

  const handlePasskeyLogin = async (): Promise<void> => {
    setError('');
    try {
      const authToken = await loginWithPasskey();
      onAuthenticated(authToken);
    } catch (caughtError: unknown) {
      const message =
        caughtError instanceof Error ? caughtError.message : 'Passkey sign-in failed';
      setError(message);
    }
  };

  const handleConfirm = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError('');
    try {
      await confirmRegistration(pendingEmail, confirmCode);
      setAuthMode('login');
      setConfirmCode('');
    } catch (caughtError: unknown) {
      const message =
        caughtError instanceof Error ? caughtError.message : 'Confirmation failed';
      setError(message);
    }
  };

  return (
    <Card sx={{ maxWidth: 460, mx: 'auto', mt: 12, borderRadius: 3 }}>
      <CardContent sx={{ p: 4 }}>
        <Stack spacing={2.5}>
          <Typography variant="h4" fontWeight={700}>
            Personal Drive
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {authMode === 'confirm'
              ? `Enter the verification code sent to ${pendingEmail}`
              : 'Authenticate to manage your files'}
          </Typography>
          <Box
            component="form"
            onSubmit={
              authMode === 'confirm'
                ? handleConfirm
                : authMode === 'login'
                  ? handleLogin
                  : handleRegister
            }
          >
            <Stack spacing={2}>
              {authMode !== 'confirm' && (
                <TextField
                  required
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              )}
              {authMode !== 'confirm' && (
                <TextField
                  required
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              )}
              {authMode === 'confirm' && (
                <TextField
                  required
                  label="Verification Code"
                  value={confirmCode}
                  onChange={(event) => setConfirmCode(event.target.value)}
                />
              )}

                      {notice && <Alert severity="success">{notice}</Alert>}
              {error && <Alert severity="error">{error}</Alert>}

              <Button type="submit" size="large" variant="contained">
                {authMode === 'login'
                  ? 'Login'
                  : authMode === 'register'
                    ? 'Register'
                    : 'Confirm'}
              </Button>

              {authMode === 'login' && passkeySupported() && (
                <Button
                  type="button"
                  size="large"
                  variant="outlined"
                  onClick={handlePasskeyLogin}
                >
                  Sign in with a passkey
                </Button>
              )}

              {authMode === 'confirm' ? (
                <Button variant="text" onClick={() => setAuthMode('login')}>
                  Back to login
                </Button>
              ) : (
                <Button
                  variant="text"
                  onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
                >
                  {authMode === 'login'
                    ? "Don't have an account? Register"
                    : 'Already have an account? Login'}
                </Button>
              )}
            </Stack>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
