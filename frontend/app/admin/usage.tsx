import React from 'react';
import { View, ScrollView, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { adminApi } from '@/src/api/admin';
import { AdminHeader, Loading, KeyValue, adminStyles } from '@/src/components/admin/AdminUI';

function DistBars({ data, color }: { data: Record<string, number>; color: string }) {
  const { colors: c } = useTheme();
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (entries.length === 0) return <AppText size={12} color={c.muted}>No data yet.</AppText>;
  return (
    <View style={{ gap: 6 }}>
      {entries.map(([k, v]) => (
        <View key={k} style={bStyles.row}>
          <AppText size={12} style={{ width: 130 }} numberOfLines={1}>{k}</AppText>
          <View style={bStyles.track}>
            <View style={[bStyles.fill, { width: `${(v / max) * 100}%`, backgroundColor: color }]} />
          </View>
          <AppText size={12} weight="medium" style={{ width: 32, textAlign: 'right' }}>{v}</AppText>
        </View>
      ))}
    </View>
  );
}

export default function AdminUsage() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey: ['admin-usage'], queryFn: adminApi.usage, refetchInterval: 8000 });
  const u = q.data;

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}>
      <AdminHeader title="AI Usage" subtitle="Observability (real data only)" />
      {q.isLoading || !u ? <Loading /> : (
        <>
          <Card padded style={{ gap: 2 }}>
            <KeyValue k="Requests total" v={u.requests_total} />
            <KeyValue k="Requests today" v={u.requests_today} />
            <KeyValue k="Requests this week" v={u.requests_week} />
            <KeyValue k="Success rate" v={`${u.success_rate}%`} color={c.success} />
            <KeyValue k="Failure rate" v={`${u.failure_rate}%`} color={c.error} />
            <KeyValue k="Fallback rate" v={`${u.fallback_rate}%`} color={c.warning} />
            <KeyValue k="Avg latency" v={u.avg_latency_ms != null ? `${u.avg_latency_ms} ms` : '—'} />
            <KeyValue k="Tokens" v={u.total_tokens != null ? u.total_tokens : u.token_info} />
            <KeyValue k="Estimated cost" v={u.estimated_cost} />
          </Card>

          <AppText weight="medium" size={15} style={styles.sectionTitle}>By model</AppText>
          <Card padded><DistBars data={u.by_model} color={c.brand} /></Card>

          <AppText weight="medium" size={15} style={styles.sectionTitle}>By task</AppText>
          <Card padded><DistBars data={u.by_task} color={c.brandSecondary} /></Card>

          <AppText weight="medium" size={15} style={styles.sectionTitle}>By provider</AppText>
          <Card padded><DistBars data={u.by_provider} color={c.info} /></Card>
        </>
      )}
    </ScrollView>
  );
}

const bStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  track: { flex: 1, height: 10, borderRadius: 5, backgroundColor: '#F4F4F2', overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 5 },
});
