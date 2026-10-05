import React from 'react';
import { View, ScrollView, RefreshControl, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { adminApi } from '@/src/api/admin';
import { AdminHeader, Loading, StatusBadge, adminStyles } from '@/src/components/admin/AdminUI';

function StatBox({ value, label, color }: { value: number | string; label: string; color?: string }) {
  const { colors: c } = useTheme();
  return (
    <View style={boxStyles.box}>
      <AppText weight="semibold" size={22} color={color}>{value}</AppText>
      <AppText size={11} color={c.muted}>{label}</AppText>
    </View>
  );
}

const NAV = [
  // Vocabulary
  { href: '/admin/review', icon: 'clipboard-check-outline', title: 'Review Queue', sub: 'Approve AI-generated words', section: 'Vocabulary' },
  { href: '/admin/jobs', icon: 'cog-sync-outline', title: 'Vocabulary Generator', sub: 'Bulk AI generation & jobs', section: 'Vocabulary' },
  { href: '/admin/embeddings', icon: 'vector-combine', title: 'Embeddings', sub: 'Semantic search vectors', section: 'Vocabulary' },
  // AI
  { href: '/admin/insights', icon: 'chart-timeline-variant-shimmer', title: 'Model Insights', sub: 'Performance, latency, quality', section: 'AI' },
  { href: '/admin/models', icon: 'chip', title: 'Providers & Models', sub: 'NVIDIA + Emergent', section: 'AI' },
  { href: '/admin/routing', icon: 'call-split', title: 'Task Routing', sub: 'Model routing & fallback', section: 'AI' },
  { href: '/admin/usage', icon: 'chart-line', title: 'AI Usage', sub: 'Requests, tokens, events', section: 'AI' },
] as const;

export default function AdminDashboard() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const q = useQuery({ queryKey: ['admin-dashboard'], queryFn: adminApi.dashboard });
  const d = q.data;

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}
      refreshControl={<RefreshControl refreshing={q.isFetching && !q.isLoading} onRefresh={q.refetch} tintColor={c.brand} />}
    >
      <AdminHeader title="Admin Control Center" subtitle="Vocabist AI Platform" />

      {q.isLoading || !d ? <Loading /> : (
        <>
          {/* Vocabulary */}
          <AppText weight="medium" size={15} style={styles.sectionTitle}>Vocabulary</AppText>
          <Card padded style={{ padding: 12 }}>
            <View style={boxStyles.grid}>
              <StatBox value={d.vocabulary.total} label="Total" />
              <StatBox value={d.vocabulary.published} label="Published" color={c.success} />
              <StatBox value={d.vocabulary.review} label="In review" color={c.warning} />
              <StatBox value={d.vocabulary.ai_generated} label="AI-generated" />
              <StatBox value={d.vocabulary.draft} label="Draft" />
              <StatBox value={d.vocabulary.archived} label="Archived" />
            </View>
          </Card>

          {/* AI today */}
          <AppText weight="medium" size={15} style={styles.sectionTitle}>AI activity</AppText>
          <Card padded style={{ padding: 12 }}>
            <View style={boxStyles.grid}>
              <StatBox value={d.ai.requests_today} label="Requests today" />
              <StatBox value={`${d.ai.success_rate}%`} label="Success rate" color={c.success} />
              <StatBox value={`${d.ai.fallback_rate}%`} label="Fallback rate" color={c.warning} />
              <StatBox value={d.ai.avg_latency_ms ?? '—'} label="Avg ms" />
              <StatBox value={d.jobs.running} label="Jobs running" />
              <StatBox value={d.jobs.completed} label="Jobs done" color={c.success} />
            </View>
          </Card>

          {/* Provider health */}
          <AppText weight="medium" size={15} style={styles.sectionTitle}>Provider health</AppText>
          <Card padded style={{ padding: 12, gap: 8 }}>
            {d.providers.map((m) => (
              <View key={m.key} style={boxStyles.healthRow}>
                <View style={{ flex: 1 }}>
                  <AppText size={13} weight="medium">{m.display_name}</AppText>
                  <AppText size={11} color={c.muted}>{m.provider}</AppText>
                </View>
                <StatusBadge status={m.status} />
              </View>
            ))}
          </Card>

          {/* Navigation */}
          {['Vocabulary', 'AI'].map((section) => (
            <React.Fragment key={section}>
              <AppText weight="medium" size={15} style={styles.sectionTitle}>{section}</AppText>
              <View style={{ gap: 8 }}>
                {NAV.filter((n) => n.section === section).map((n) => (
                  <Card key={n.href} onPress={() => router.push(n.href as any)} style={boxStyles.navCard} testID={`admin-nav-${n.title}`}>
                    <View style={boxStyles.navIcon}><Icon name={n.icon as any} size={20} color={c.brand} /></View>
                    <View style={{ flex: 1 }}>
                      <AppText weight="medium" size={15}>{n.title}</AppText>
                      <AppText size={12} color={c.muted}>{n.sub}</AppText>
                    </View>
                    <Icon name="chevron-right" size={20} color={c.muted} />
                  </Card>
                ))}
              </View>
            </React.Fragment>
          ))}
        </>
      )}
    </ScrollView>
  );
}

const boxStyles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  box: { width: '33.3%', paddingVertical: 8, alignItems: 'center' },
  healthRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  navCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  navIcon: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#E7F0E9', alignItems: 'center', justifyContent: 'center' },
});
