import { useQuery } from '@tanstack/react-query';
import { api } from '@/src/api/client';

// ── Types ───────────────────────────────────────────────
export type AdminMe = { is_admin: boolean; email: string };

export type ModelInfo = {
  key: string;
  provider: string;
  model_id: string;
  display_name: string;
  capabilities: string[];
  modality: string;
  enabled: boolean;
  status: string;
  status_reason?: string;
  default_temperature?: number | null;
  context?: string | null;
  notes?: string;
  last_success?: string | null;
  failure_count?: number;
  last_latency_ms?: number | null;
};

export type ProviderGroup = { provider: string; configured: boolean; models: ModelInfo[] };

export type Dashboard = {
  vocabulary: { total: number; published: number; review: number; draft: number; archived: number; ai_generated: number };
  ai: UsageAgg;
  providers: ModelInfo[];
  jobs: { total: number; running: number; completed: number; partial: number; failed: number };
  nvidia_configured: boolean;
  emergent_configured: boolean;
};

export type UsageAgg = {
  requests_total: number; requests_today: number; requests_week: number;
  success: number; failure: number; fallback_events: number;
  success_rate: number; failure_rate: number; fallback_rate: number;
  avg_latency_ms: number | null;
  by_model: Record<string, number>; by_task: Record<string, number>; by_provider: Record<string, number>;
  total_tokens: number | null; token_info: string; estimated_cost: string;
};

export type RouteInfo = {
  task: string; required_capability: string; chain: string[];
  enabled: boolean; is_override: boolean; invalid_models: string[];
};

export type Job = {
  id: string; task: string; status: string; params: any;
  requested_count: number; generated_count: number; valid_count: number;
  invalid_count: number; duplicate_count: number; model?: string; provider?: string;
  fallback_used?: boolean; word_ids: string[]; error?: string | null;
  created_at: string; started_at?: string | null; completed_at?: string | null; log?: string[];
};

export type ReviewWord = {
  id: string; headword: string; cefr?: string; part_of_speech?: string;
  simple_definition?: string; example?: string; synonyms?: string[]; antonyms?: string[];
  word_family?: string[]; mnemonic?: string; common_mistakes?: string;
  provenance?: string; status?: string;
};

// ── API calls ───────────────────────────────────────────
export const adminApi = {
  me: () => api<AdminMe>('/admin/me'),
  dashboard: () => api<Dashboard>('/admin/dashboard'),
  providers: () => api<{ providers: ProviderGroup[] }>('/admin/ai/providers'),
  models: () => api<{ models: ModelInfo[] }>('/admin/ai/models'),
  toggleModel: (key: string, enabled: boolean) =>
    api<ModelInfo>(`/admin/ai/models/${key}/toggle`, { method: 'POST', body: { enabled } }),
  pingModel: (key: string) =>
    api<{ model: string; status: string; latency_ms?: number; error?: string }>(`/admin/ai/models/${key}/ping`, { method: 'POST' }),
  routing: () => api<{ routing: RouteInfo[]; tasks: string[] }>('/admin/ai/routing'),
  usage: () => api<UsageAgg>('/admin/ai/usage'),
  jobs: () => api<{ jobs: Job[] }>('/admin/ai/jobs'),
  job: (id: string) => api<Job>(`/admin/ai/jobs/${id}`),
  createJob: (body: any) => api<Job>('/admin/ai/jobs', { method: 'POST', body }),
  cancelJob: (id: string) => api<Job>(`/admin/ai/jobs/${id}/cancel`, { method: 'POST' }),
  reviewQueue: (search = '') =>
    api<{ total: number; words: ReviewWord[] }>(`/admin/vocabulary/review?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`),
  getWord: (id: string) => api<{ word: ReviewWord; validation: any }>(`/admin/vocabulary/${id}`),
  regenerate: (id: string, field: string, model?: string) =>
    api<{ field: string; value: any; model: string; word: ReviewWord }>(`/admin/vocabulary/${id}/regenerate`, { method: 'POST', body: { field, model } }),
  approve: (id: string) => api(`/admin/vocabulary/${id}/approve`, { method: 'POST' }),
  publish: (id: string) => api(`/admin/vocabulary/${id}/publish`, { method: 'POST' }),
  reject: (id: string, reason?: string) => api(`/admin/vocabulary/${id}/reject`, { method: 'POST', body: { reason } }),
  translate: (text: string, target_language: string, model?: string) =>
    api<{ translation: string; model_key: string }>('/admin/ai/translate', { method: 'POST', body: { text, target_language, model } }),
};

export function useIsAdmin() {
  const q = useQuery({
    queryKey: ['admin-me'],
    queryFn: adminApi.me,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  return { isAdmin: !!q.data?.is_admin, loading: q.isLoading };
}
