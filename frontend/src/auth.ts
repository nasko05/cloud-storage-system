import { config } from './config';

const TOKEN_KEY = 'drive.accessToken';
const EMAIL_KEY = 'drive.email';

interface RegisterResult {
  confirmationRequired: boolean;
}

async function authRequest<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${config.apiEndpoint}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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

export const logout = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
};

export const getToken = async (): Promise<string | null> => localStorage.getItem(TOKEN_KEY);
