import React, { useState } from 'react';
import { View, ScrollView, Pressable, RefreshControl, Alert } from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { useToast } from '@/src/components/Toast';
import { adminApi } from '@/src/api/admin';

export default function AdminEmbeddings() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);

  const statusQ = useQuery({
    queryKey: ['admin-embedding-status'],
    queryFn: adminApi.embeddingStatus,
    staleTime: 30_000,
  });

  const jobsQ = useQuery({
    queryKey: ['admin-embedding-jobs'],
    queryFn: adminApi.listEmbeddingJobs,
    staleTime: 15_000,
  });

  const startJob = async (mode: string) => {
    setCreating(true);
    try {
      await adminApi.createEmbeddingJob({ mode });
      toast.show(`Embedding job (${mode}) started`, 'success');
      qc.invalidateQueries({ queryKey: ['admin-embedding-jobs'] });
      qc.invalidateQueries({ queryKey: ['admin-embedding-status'] });
    } catch (err: any) {
      toast.show(err?.message || 'Failed to start job', 'error');
    } finally {
      setCreating(false);
    }
  };

  const stats = statusQ.data;
  const jobs = jobsQ.data?.jobs ?? [];

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Icon name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={18}>Embeddings</AppText>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={statusQ.isRefetching}
            onRefresh={() => {
              statusQ.refetch();
              jobsQ.refetch();
            }}
            tintColor={colors.brand}
          />
        }
      >
        {/* Coverage stats */}
        <AppText weight="semibold" size={16} style={{ marginBottom: 8 }}>Coverage</AppText>
        {statusQ.isLoading ? (
          <Skeleton height={120} rounded={16} />
        ) : stats ? (
          <Card style={styles.statsCard}>
            <View style={styles.statRow}>
              <StatItem label="Published" value={stats.total_published ?? 0} color={colors.onSurface} />
              <StatItem label="Embedded" value={stats.embedded ?? 0} color={colors.success} />
              <StatItem label="Missing" value={stats.missing ?? 0} color={stats.missing > 0 ? colors.warning : colors.muted} />
            </View>
            <View style={styles.progressBar}>
              <View style={[styles.progressFill, { width: `${stats.coverage_percent ?? 0}%` }]} />
            </View>
            <AppText size={12} color={colors.muted} style={{ marginTop: 4, textAlign: 'center' }}>
              {stats.coverage_percent ?? 0}% coverage · {stats.embedding_model} {stats.embedding_version}
            </AppText>
            {stats.error && (
              <AppText size={12} color={colors.warning} style={{ marginTop: 6, textAlign: 'center' }}>
                {stats.error}
              </AppText>
            )}
          </Card>
        ) : null}

        {/* Actions */}
        <AppText weight="semibold" size={16} style={{ marginTop: 16, marginBottom: 8 }}>Actions</AppText>
        <View style={styles.actionRow}>
          <Button
            label="Generate missing"
            variant="primary"
            onPress={() => startJob('missing')}
            disabled={creating}
            icon="plus-circle"
            style={{ flex: 1 }}
          />
          <Button
            label="Regenerate stale"
            variant="secondary"
            onPress={() => startJob('stale')}
            disabled={creating}
            icon="refresh"
            style={{ flex: 1 }}
          />
        </View>
        <Button
          label="Regenerate all"
          variant="secondary"
          onPress={() => {
            Alert.alert(
              'Regenerate all embeddings?',
              'This will regenerate embeddings for all published words. It may take a while.',
              [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Proceed', onPress: () => startJob('all') },
              ]
            );
          }}
          disabled={creating}
          icon="reload"
        />

        {/* Jobs history */}
        <AppText weight="semibold" size={16} style={{ marginTop: 20, marginBottom: 8 }}>Recent Jobs</AppText>
        {jobsQ.isLoading ? (
          <>
            <Skeleton height={80} rounded={12} />
            <Skeleton height={80} rounded={12} />
          </>
        ) : jobs.length === 0 ? (
          <AppText size={13} color={colors.muted}>No embedding jobs yet.</AppText>
        ) : (
          jobs.slice(0, 20).map((job: any) => (
            <Card key={job.id} style={styles.jobCard}>
              <View style={styles.jobHeader}>
                <AppText weight="medium" size={14}>{job.id}</AppText>
                <StatusChip status={job.status} />
              </View>
              <View style={styles.jobStats}>
                <AppText size={12} color={colors.muted}>Total: {job.total_words ?? 0}</AppText>
                <AppText size={12} color={colors.success}>OK: {job.successful ?? 0}</AppText>
                <AppText size={12} color={colors.error}>Failed: {job.failed ?? 0}</AppText>
                <AppText size={12} color={colors.muted}>Skipped: {job.skipped ?? 0}</AppText>
              </View>
              {job.duration_ms != null && (
                <AppText size={11} color={colors.muted}>Duration: {(job.duration_ms / 1000).toFixed(1)}s</AppText>
              )}
            </Card>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function StatItem({ label, value, color }: { label: string; value: number; color: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <AppText weight="semibold" size={22} color={color}>{value}</AppText>
      <AppText size={12} color={colors.muted}>{label}</AppText>
    </View>
  );
}

function StatusChip({ status }: { status: string }) {
  const { colors } = useTheme();
  const bg = status === 'COMPLETED' ? '#E7F5EC' : status === 'RUNNING' ? '#E0F0FF' : status === 'FAILED' ? '#FFE8E8' : '#F4F4F2';
  const fg = status === 'COMPLETED' ? colors.success : status === 'RUNNING' ? colors.info : status === 'FAILED' ? colors.error : colors.muted;
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: bg }}>
      <AppText size={11} weight="medium" color={fg}>{status}</AppText>
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
  statsCard: { gap: 8 },
  statRow: { flexDirection: 'row', justifyContent: 'space-around' },
  progressBar: {
    height: 6, borderRadius: 3, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 3 },
  actionRow: { flexDirection: 'row', gap: 10 },
  jobCard: { gap: 6 },
  jobHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  jobStats: { flexDirection: 'row', gap: 12 },
}));
