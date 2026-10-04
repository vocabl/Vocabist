import React, { useState } from 'react';
import { View, ScrollView, Pressable, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Input } from '@/src/components/Input';
import { Button } from '@/src/components/Button';
import { Chip } from '@/src/components/Chip';
import { Icon } from '@/src/components/Icon';
import { adminApi, Job } from '@/src/api/admin';
import { AdminHeader, Loading, StatusBadge, adminStyles } from '@/src/components/admin/AdminUI';

const CEFRS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
const LEVELS = ['minimal', 'standard', 'rich'];

export default function AdminJobs() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();

  const [count, setCount] = useState('10');
  const [cefr, setCefr] = useState<string | null>('B2');
  const [topic, setTopic] = useState('');
  const [enrichment, setEnrichment] = useState('standard');
  const [submitting, setSubmitting] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState('');

  const q = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: adminApi.jobs,
    refetchInterval: 4000,
  });

  const create = async () => {
    setError('');
    const n = parseInt(count, 10);
    if (!n || n < 1) { setError('Enter a valid count'); return; }
    setSubmitting(true);
    try {
      await adminApi.createJob({
        count: n,
        cefr: cefr || undefined,
        topic: topic.trim() || undefined,
        enrichment_level: enrichment,
      });
      await q.refetch();
    } catch (e: any) {
      setError(e?.message || 'Failed to create job');
    } finally { setSubmitting(false); }
  };

  const cancel = async (id: string) => { await adminApi.cancelJob(id); q.refetch(); };
  const jobs = q.data?.jobs ?? [];

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}>
      <AdminHeader title="Generation Jobs" subtitle="AI vocabulary → content pipeline → REVIEW" />

      {/* Create form */}
      <Card padded style={{ gap: 12 }} testID="job-form">
        <AppText weight="semibold" size={15}>New generation job</AppText>
        <Input label="How many words" keyboardType="number-pad" value={count} onChangeText={setCount} testID="job-count" />
        <View>
          <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>CEFR level</AppText>
          <View style={fStyles.chips}>
            {CEFRS.map((x) => <Chip key={x} label={x} selected={cefr === x} onPress={() => setCefr(cefr === x ? null : x)} />)}
          </View>
        </View>
        <Input label="Topic (optional)" placeholder="e.g. Academic, Business" value={topic} onChangeText={setTopic} testID="job-topic" />
        <View>
          <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>Enrichment</AppText>
          <View style={fStyles.chips}>
            {LEVELS.map((x) => <Chip key={x} label={x} selected={enrichment === x} onPress={() => setEnrichment(x)} />)}
          </View>
        </View>
        <AppText size={11} color={c.muted}>Model routing: Auto (Nemotron Lightning → GPT-OSS → Nemotron Super → Emergent). Output enters REVIEW, never auto-published.</AppText>
        {error ? <AppText size={12} color={c.error}>{error}</AppText> : null}
        <Button label="Generate" icon="auto-fix" loading={submitting} onPress={create} testID="job-generate" />
      </Card>

      {/* Jobs list */}
      <AppText weight="medium" size={15} style={styles.sectionTitle}>Jobs</AppText>
      {q.isLoading ? <Loading /> : jobs.length === 0 ? (
        <AppText size={13} color={c.muted}>No jobs yet.</AppText>
      ) : jobs.map((j: Job) => (
        <Card key={j.id} padded onPress={() => setOpen(open === j.id ? null : j.id)} style={{ gap: 6 }} testID={`job-${j.id}`}>
          <View style={fStyles.jobHead}>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={13}>{j.id}</AppText>
              <AppText size={11} color={c.muted}>
                {j.params?.cefr || 'any'} · {j.params?.topic || 'general'} · want {j.requested_count}
              </AppText>
            </View>
            <StatusBadge status={j.status} />
          </View>
          <View style={fStyles.counts}>
            <Count label="new" value={j.valid_count} color={c.success} />
            <Count label="dup" value={j.duplicate_count} color={c.muted} />
            <Count label="rejected" value={j.invalid_count} color={c.error} />
            <Count label="gen" value={j.generated_count} color={c.onSurface} />
          </View>
          {open === j.id && (
            <View style={{ gap: 6, marginTop: 4 }}>
              {j.model ? <AppText size={11} color={c.muted}>Model: {j.model} {j.fallback_used ? '(fallback used)' : ''}</AppText> : null}
              {(j.log || []).map((l, i) => <AppText key={i} size={11} color={c.onSurfaceTertiary}>• {l}</AppText>)}
              {j.error ? <AppText size={11} color={c.error}>{j.error}</AppText> : null}
              {(j.status === 'RUNNING' || j.status === 'QUEUED') && (
                <Pressable onPress={() => cancel(j.id)} style={fStyles.cancel} testID={`cancel-${j.id}`}>
                  <Icon name="close-circle-outline" size={16} color={c.error} />
                  <AppText size={12} color={c.error}>Cancel</AppText>
                </Pressable>
              )}
            </View>
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

function Count({ label, value, color }: { label: string; value: number; color: string }) {
  const { colors: c } = useTheme();
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <AppText weight="semibold" size={16} color={color}>{value}</AppText>
      <AppText size={10} color={c.muted}>{label}</AppText>
    </View>
  );
}

const fStyles = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  jobHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  counts: { flexDirection: 'row', marginTop: 4 },
  cancel: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start' },
});
