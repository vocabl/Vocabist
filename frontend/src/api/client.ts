import { storage } from '@/src/utils/storage';

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL as string;
export const API = `${BASE_URL}/api`;
const TOKEN_KEY = 'vocably.token';

let inMemoryToken: string | null = null;

export async function loadToken(): Promise<string | null> {
  if (inMemoryToken) return inMemoryToken;
  inMemoryToken = await storage.getItem(TOKEN_KEY);
  return inMemoryToken;
}

export async function setToken(token: string | null): Promise<void> {
  inMemoryToken = token;
  if (token) await storage.setItem(TOKEN_KEY, token);
  else await storage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Options = {
  method?: string;
  body?: unknown;
  auth?: boolean;
};

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = opts;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = await loadToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new ApiError(res.status, typeof msg === 'string' ? msg : 'Request failed');
  }
  return data as T;
}
