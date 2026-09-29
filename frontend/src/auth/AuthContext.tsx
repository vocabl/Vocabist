import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Platform, Linking } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as ExpoLinking from 'expo-linking';
import { api, loadToken, setToken } from '@/src/api/client';

WebBrowser.maybeCompleteAuthSession();

export type User = {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  onboarded: boolean;
  tier: string;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  signInEmail: (email: string, password: string) => Promise<void>;
  signUpEmail: (email: string, password: string, name: string) => Promise<void>;
  signInGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(AuthContext);

const processedSessionIds = new Set<string>();

function extractSessionId(url: string | null): string | null {
  if (!url) return null;
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const exchangeSessionId = useCallback(async (sessionId: string) => {
    if (!sessionId || processedSessionIds.has(sessionId)) return;
    processedSessionIds.add(sessionId);
    const data = await api<{ token: string; user: User }>('/auth/session', {
      method: 'POST',
      auth: false,
      body: { session_id: sessionId },
    });
    await setToken(data.token);
    setUser(data.user);
  }, []);

  const checkExisting = useCallback(async () => {
    try {
      const token = await loadToken();
      if (!token) {
        setUser(null);
        return;
      }
      const data = await api<{ user: User }>('/auth/me');
      setUser(data.user);
    } catch {
      await setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let sub: { remove: () => void } | undefined;
    (async () => {
      try {
        if (Platform.OS === 'web') {
          const sid = extractSessionId(window.location.hash) || extractSessionId(window.location.search);
          if (sid) {
            try {
              await exchangeSessionId(sid);
              const url = new URL(window.location.href);
              url.hash = '';
              url.searchParams.delete('session_id');
              window.history.replaceState(window.history.state, '', url.toString());
            } catch {
              /* fall through to existing session */
            }
          }
        } else {
          sub = Linking.addEventListener('url', ({ url }) => {
            const sid = extractSessionId(url);
            if (sid) exchangeSessionId(sid).catch(() => {});
          });
          const initial = await Linking.getInitialURL();
          const sid = extractSessionId(initial);
          if (sid) {
            try {
              await exchangeSessionId(sid);
            } catch {
              /* ignore */
            }
          }
        }
        if (!user) await checkExisting();
      } finally {
        setLoading(false);
      }
    })();
    return () => sub?.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signInEmail = useCallback(async (email: string, password: string) => {
    const data = await api<{ token: string; user: User }>('/auth/login', {
      method: 'POST',
      auth: false,
      body: { email, password },
    });
    await setToken(data.token);
    setUser(data.user);
  }, []);

  const signUpEmail = useCallback(async (email: string, password: string, name: string) => {
    const data = await api<{ token: string; user: User }>('/auth/register', {
      method: 'POST',
      auth: false,
      body: { email, password, name },
    });
    await setToken(data.token);
    setUser(data.user);
  }, []);

  const signInGoogle = useCallback(async () => {
    const redirectUrl =
      Platform.OS === 'web' ? window.location.origin + '/' : ExpoLinking.createURL('');
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    if (Platform.OS === 'web') {
      window.location.href = authUrl;
      return;
    }
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    let sid: string | null = null;
    if (result.type === 'success' && result.url) sid = extractSessionId(result.url);
    if (!sid) sid = extractSessionId(await Linking.getInitialURL());
    if (sid) await exchangeSessionId(sid);
  }, [exchangeSessionId]);

  const signOut = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch {
      /* ignore */
    }
    await setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, signInEmail, signUpEmail, signInGoogle, signOut, refresh: checkExisting }}
    >
      {children}
    </AuthContext.Provider>
  );
}
