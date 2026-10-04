import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useRouter } from 'expo-router';
import { api } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthContext';

export type Entitlement = {
  plan: 'free' | 'pro';
  tier: string;
  is_pro: boolean;
  status: string;
  source: string;
  subscription_plan: string | null;
  started_at: string | null;
  cancelled_at: string | null;
  provider_connected: boolean;
  limits: {
    daily_new_words: number;
    ai_coach_per_day: number;
    locked_exams: string[];
    unlimited: boolean;
  };
  ai_coach_used_today: number;
  pricing: Record<string, { price_display: string; period: string; interval_months: number }>;
};

export function useEntitlement() {
  const { user } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ['entitlements'],
    queryFn: () => api<Entitlement>('/entitlements'),
    enabled: !!user,
    staleTime: 60_000,
  });

  const isPro = q.data?.is_pro ?? false;
  const plan = q.data?.plan ?? 'free';
  const status = q.data?.status ?? 'none';
  const providerConnected = q.data?.provider_connected ?? false;
  const pricing = q.data?.pricing ?? {};
  const limits = q.data?.limits;

  const openPaywall = useCallback((context?: string) => {
    router.push('/paywall');
  }, [router]);

  const requirePro = useCallback((featureLabel?: string): boolean => {
    if (isPro) return true;
    openPaywall(featureLabel);
    return false;
  }, [isPro, openPaywall]);

  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['entitlements'] });
  }, [qc]);

  return {
    data: q.data,
    isPro,
    plan,
    status,
    providerConnected,
    pricing,
    limits,
    loading: q.isLoading,
    error: q.error,
    openPaywall,
    requirePro,
    refresh,
  };
}
