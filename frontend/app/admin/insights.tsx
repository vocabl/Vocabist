import React, { useState } from 'react';
import { View, ScrollView, Pressable, RefreshControl } from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { adminApi } from '@/src/api/admin';

const PERIODS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
];

export default function ModelInsights() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [days, setDays] = useState(30);
  const [selectedModel, setSelectedModel] = useState<string | undefined>(undefined);

  const insightsQ = useQuery({
    queryKey: ['admin-insights', days, selectedModel],
    queryFn: () => adminApi.insights({ days, model: selectedModel }),
    staleTime: 30_000,
  });

  const data = insightsQ.data;
  const models = data?.models ?? [];
  const tasks = data?.tasks ?? [];

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Icon name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={18}>Model Insights</AppText>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={insightsQ.isRefetching} onRefresh={() => insightsQ.refetch()} tintColor={colors.brand} />
        }
      >
        {/* Period selector */}
        <View style={styles.periodRow}>
          {PERIODS.map((p) => (
            <Pressable
              key={p.value}
              onPress={() => setDays(p.value)}
              style={[styles.periodChip, days === p.value && styles.periodActive]}
            >
              <AppText size={13} weight="medium" color={days === p.value ? colors.onSurfaceInverse : colors.muted}>
                {p.label}
              </AppText>
            </Pressable>
          ))}
          {selectedModel && (
            <Pressable onPress={() => setSelectedModel(undefined)} style={styles.clearFilter}>
              <AppText size={12} color={colors.brand}>Clear filter</AppText>
              <Icon name="close" size={14} color={colors.brand} />
            </Pressable>
          )}
        </View>

        {insightsQ.isLoading ? (
          <View style={{ gap: 12 }}>
            <Skeleton height={100} rounded={16} />
            <Skeleton height={160} rounded={16} />
            <Skeleton height={160} rounded={16} />
          </View>
        ) : data ? (
          <>
            {/* Summary */}
            <Card style={styles.summaryCard}>
              <View style={styles.summaryRow}>
                <SummaryItem label="Requests" value={data.total_requests} />
                <SummaryItem label="Success" value={`${data.overall_success_rate}%`} color={colors.success} />
                <SummaryItem label="Fallbacks" value={data.total_fallback} color={colors.warning} />
                <SummaryItem label="Avg Latency" value={data.overall_avg_latency_ms != null ? `${data.overall_avg_latency_ms}ms` : '—'} />
              </View>
            </Card>

            {/* Model Comparison Table */}
            <AppText weight="semibold" size={16} style={{ marginTop: 16, marginBottom: 8 }}>
              Model Performance
            </AppText>
            {models.length === 0 ? (
              <AppText size={13} color={colors.muted}>No usage data recorded yet.</AppText>
            ) : (
              models.map((m: any) => (
                <Pressable key={m.model} onPress={() => setSelectedModel(m.model === selectedModel ? undefined : m.model)}>
                  <Card style={[styles.modelCard, m.model === selectedModel && styles.modelCardSelected]}>
                    <View style={styles.modelHeader}>
                      <View style={{ flex: 1 }}>
                        <AppText weight="semibold" size={14} numberOfLines={1}>{m.model}</AppText>
                        <AppText size={11} color={colors.muted}>{m.provider}</AppText>
                      </View>
                      <View style={styles.reqBadge}>
                        <AppText size={12} weight="medium">{m.requests} req</AppText>
                      </View>
                    </View>

                    <View style={styles.metricGrid}>
                      <MetricCell label="Success" value={`${m.success_rate}%`} color={m.success_rate >= 90 ? colors.success : colors.warning} />
                      <MetricCell label="Failed" value={String(m.failed)} color={m.failed > 0 ? colors.error : colors.muted} />
                      <MetricCell label="Fallback" value={`${m.fallback_rate}%`} color={m.fallback_rate > 10 ? colors.warning : colors.muted} />
                      <MetricCell label="Avg Latency" value={m.avg_latency_ms != null ? `${m.avg_latency_ms}ms` : '—'} />
                      <MetricCell label="P50" value={m.p50_latency_ms != null ? `${m.p50_latency_ms}ms` : '—'} />
                      <MetricCell label="P95" value={m.p95_latency_ms != null ? `${m.p95_latency_ms}ms` : '—'} />
                    </View>

                    {/* Token usage */}
                    {m.tokens?.available && (
                      <View style={styles.tokenRow}>
                        <Icon name="counter" size={14} color={colors.muted} />
                        <AppText size={11} color={colors.muted}>
                          Tokens: {m.tokens.total.toLocaleString()} (prompt: {m.tokens.prompt.toLocaleString()}, completion: {m.tokens.completion.toLocaleString()})
                        </AppText>
                      </View>
                    )}

                    {/* Cost */}
                    <View style={styles.tokenRow}>
                      <Icon name="currency-usd" size={14} color={colors.muted} />
                      <AppText size={11} color={colors.muted}>Cost: {m.cost}</AppText>
                    </View>

                    {/* Tasks */}
                    {Object.keys(m.tasks || {}).length > 0 && (
                      <View style={styles.taskChips}>
                        {Object.entries(m.tasks).map(([task, count]) => (
                          <View key={task} style={styles.taskChip}>
                            <AppText size={10} color={colors.muted}>{task}: {String(count)}</AppText>
                          </View>
                        ))}
                      </View>
                    )}
                  </Card>
                </Pressable>
              ))
            )}

            {/* Task Breakdown */}
            <AppText weight="semibold" size={16} style={{ marginTop: 20, marginBottom: 8 }}>
              Task Breakdown
            </AppText>
            {tasks.length === 0 ? (
              <AppText size={13} color={colors.muted}>No task data.</AppText>
            ) : (
              tasks.map((t: any) => (
                <Card key={t.task} style={styles.taskCard}>
                  <View style={styles.taskHeader}>
                    <AppText weight="medium" size={14}>{t.task}</AppText>
                    <AppText size={12} color={colors.muted}>{t.requests} req</AppText>
                  </View>
                  <View style={styles.taskMetrics}>
                    <AppText size={12} color={colors.success}>✓ {t.successful}</AppText>
                    <AppText size={12} color={colors.error}>✗ {t.failed}</AppText>
                    <AppText size={12} color={colors.warning}>↻ {t.fallback_count}</AppText>
                    {t.avg_latency_ms != null && (
                      <AppText size={12} color={colors.muted}>{t.avg_latency_ms}ms avg</AppText>
                    )}
                  </View>
                  {t.models_used?.length > 0 && (
                    <AppText size={11} color={colors.muted} numberOfLines={1}>
                      Models: {t.models_used.join(', ')}
                    </AppText>
                  )}
                </Card>
              ))
            )}
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

function SummaryItem({ label, value, color }: { label: string; value: any; color?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <AppText weight="semibold" size={18} color={color || colors.onSurface}>{String(value)}</AppText>
      <AppText size={11} color={colors.muted}>{label}</AppText>
    </View>
  );
}

function MetricCell({ label, value, color }: { label: string; value: string; color?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ alignItems: 'center', width: '33%', paddingVertical: 4 }}>
      <AppText weight="medium" size={13} color={color || colors.onSurface}>{value}</AppText>
      <AppText size={10} color={colors.muted}>{label}</AppText>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: t.spacing.lg, paddingVertical: t.spacing.md,
    borderBottomWidth: 1, borderBottomColor: t.colors.divider,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: t.spacing.lg, paddingBottom: 40, gap: 12 },
  periodRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  periodChip: {
    paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20,
    borderWidth: 1, borderColor: t.colors.border,
  },
  periodActive: { backgroundColor: t.colors.surfaceInverse, borderColor: t.colors.surfaceInverse },
  clearFilter: { flexDirection: 'row', alignItems: 'center', gap: 4, marginLeft: 'auto' },
  summaryCard: { gap: 4 },
  summaryRow: { flexDirection: 'row', justifyContent: 'space-around' },
  modelCard: { gap: 8 },
  modelCardSelected: { borderColor: t.colors.brand, borderWidth: 2 },
  modelHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  reqBadge: {
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10,
    backgroundColor: t.colors.surfaceTertiary,
  },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center' },
  tokenRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  taskChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  taskChip: {
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
    backgroundColor: t.colors.surfaceTertiary,
  },
  taskCard: { gap: 4 },
  taskHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  taskMetrics: { flexDirection: 'row', gap: 16 },
}));
