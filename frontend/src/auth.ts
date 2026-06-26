import { startAuthentication, startRegistration } from '@simplewebauthn/browser';
import { config } from './config';

const TOKEN_KEY = 'drive.accessToken';
const EMAIL_KEY = 'drive.email';

interface RegisterResult {
  confirmationRequired: boolean;
}

interface PasskeyOptions {
  options: Record<string, unknown>;
  challengeToken: string;
}

async function authRequest<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const resp = await fetch(`${config.apiEndpoint}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body)
  });

  const data = (await resp.json().catch(() => ({}))) as T & { error?: string };
  if (!resp.ok) {
    throw new Error(data.error || `Request failed with status ${resp.status}`);
  }
  return data;
}

export const register = async (email: string, password: string): Promise<RegisterResult> => {
  const result = await authRequest<RegisterResult>('/v2/auth/register', { email, password });
  return { confirmationRequired: Boolean(result.confirmationRequired) };
};

export const confirmRegistration = async (email: string, code: string): Promise<void> => {
  await authRequest<{ confirmed: boolean }>('/v2/auth/confirm', { email, code });
};

export const login = async (email: string, password: string): Promise<string> => {
  const result = await authRequest<{ token: string }>('/v2/auth/login', { email, password });
  localStorage.setItem(TOKEN_KEY, result.token);
  localStorage.setItem(EMAIL_KEY, email);
  return result.token;
};

/** Returns true when the browser supports the WebAuthn APIs passkeys need. */
export const passkeySupported = (): boolean =>
  typeof window !== 'undefined' && !!window.PublicKeyCredential;

/**
 * Register a new passkey for the currently logged-in user. Requires the active
 * access token because the credential is bound to the authenticated account.
 */
export const registerPasskey = async (token: string, name?: string): Promise<void> => {
  const start = await authRequest<PasskeyOptions>(
    '/v2/auth/passkey/register/options',
    {},
    token
  );
  const credential = await startRegistration({ optionsJSON: start.options as never });
  await authRequest(
    '/v2/auth/passkey/register/verify',
    { credential, challengeToken: start.challengeToken, name },
    token
  );
};

/**
 * Usernameless ("one-tap") passkey sign-in: the authenticator supplies the user
 * handle, so no email is needed. Stores the returned token like password login.
 */
export const loginWithPasskey = async (): Promise<string> => {
  const start = await authRequest<PasskeyOptions>('/v2/auth/passkey/login/options', {});
  const credential = await startAuthentication({ optionsJSON: start.options as never });
  const result = await authRequest<{ token: string; email: string }>(
    '/v2/auth/passkey/login/verify',
    { credential, challengeToken: start.challengeToken }
  );
  localStorage.setItem(TOKEN_KEY, result.token);
  if (result.email) localStorage.setItem(EMAIL_KEY, result.email);
  return result.token;
};

export const logout = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
};

export const getToken = async (): Promise<string | null> => localStorage.getItem(TOKEN_KEY);
