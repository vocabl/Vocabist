import React, { useState } from 'react';
import { View, ScrollView, Pressable, StyleSheet, Alert } from 'react-native';
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
const POS_OPTIONS = ['noun', 'verb', 'adjective', 'adverb', 'mixed'];
const EXAM_OPTIONS = ['IELTS', 'TOEFL', 'GRE', 'SAT', 'GMAT', 'CEFR'];
const VOCAB_TYPES = ['academic', 'high-frequency', 'advanced', 'exam', 'contextual'];
const QUALITY_OPTIONS = ['standard', 'high', 'maximum'];

export default function AdminJobs() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();

  const [count, setCount] = useState('10');
  const [cefr, setCefr] = useState<string | null>('B2');
  const [topic, setTopic] = useState('');
  const [enrichment, setEnrichment] = useState('standard');
  const [pos, setPos] = useState<string | null>(null);
  const [exam, setExam] = useState<string | null>(null);
  const [vocabType, setVocabType] = useState<string | null>(null);
  const [quality, setQuality] = useState('standard');
  const [submitting, setSubmitting] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const q = useQuery({
    queryKey: ['admin-jobs'],
    queryFn: adminApi.jobs,
    refetchInterval: 4000,
  });

  const create = async () => {
    setError('');
    const n = parseInt(count, 10);
    if (!n || n < 1 || n > 500) { setError('Count must be 1-500'); return; }

    // Require confirmation for large jobs
    if (n > 50) {
      Alert.alert(
        `Generate ${n} words?`,
        `This will create a large vocabulary generation job. The words will enter REVIEW status and require explicit approval before publishing.`,
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Generate', onPress: () => doCreate(n) },
        ]
      );
      return;
    }
    await doCreate(n);
  };

  const doCreate = async (n: number) => {
    setSubmitting(true);
    try {
      const body: any = {
        count: n,
        cefr: cefr || undefined,
        topic: topic.trim() || undefined,
        enrichment_level: enrichment,
        confirmed: true,
      };
      if (pos) body.part_of_speech = pos;
      if (exam) body.exam = exam.toLowerCase();
      if (vocabType) body.vocabulary_type = vocabType;
      if (quality !== 'standard') body.quality = quality;

      // Use bulk-generate for large jobs, regular for small
      if (n > 30) {
        const res = await adminApi.bulkGenerate(body);
        if (res.requires_confirmation) {
          Alert.alert(res.message, undefined, [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Confirm', onPress: async () => {
              body.confirmed = true;
              await adminApi.bulkGenerate(body);
              await q.refetch();
            }},
          ]);
          setSubmitting(false);
          return;
        }
      } else {
        await adminApi.createJob(body);
      }
      await q.refetch();
    } catch (e: any) {
      setError(e?.message || 'Failed to create job');
    } finally { setSubmitting(false); }
  };

  const cancel = async (id: string) => { await adminApi.cancelJob(id); q.refetch(); };
  const jobs = q.data?.jobs ?? [];

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}>
      <AdminHeader title="Vocabulary Generator" subtitle="Bulk AI generation → validation → REVIEW pipeline" />

      {/* Create form */}
      <Card padded style={{ gap: 12 }} testID="job-form">
        <AppText weight="semibold" size={15}>New generation job</AppText>
        <Input label="How many words (1-500)" keyboardType="number-pad" value={count} onChangeText={setCount} testID="job-count" />
        <View>
          <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>CEFR level</AppText>
          <View style={fStyles.chips}>
            {CEFRS.map((x) => <Chip key={x} label={x} selected={cefr === x} onPress={() => setCefr(cefr === x ? null : x)} />)}
          </View>
        </View>
        <Input label="Topic" placeholder="e.g. Academic, Business, Science, Economics" value={topic} onChangeText={setTopic} testID="job-topic" />
        <View>
          <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>Part of Speech</AppText>
          <View style={fStyles.chips}>
            {POS_OPTIONS.map((x) => <Chip key={x} label={x} selected={pos === x} onPress={() => setPos(pos === x ? null : x)} />)}
          </View>
        </View>
        <View>
          <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>Exam</AppText>
          <View style={fStyles.chips}>
            {EXAM_OPTIONS.map((x) => <Chip key={x} label={x} selected={exam === x} onPress={() => setExam(exam === x ? null : x)} />)}
          </View>
        </View>

        {/* Advanced options toggle */}
        <Pressable onPress={() => setShowAdvanced(!showAdvanced)} style={fStyles.advancedToggle}>
          <AppText size={13} weight="medium" color={c.brand}>Advanced options</AppText>
          <Icon name={showAdvanced ? 'chevron-up' : 'chevron-down'} size={18} color={c.brand} />
        </Pressable>

        {showAdvanced && (
          <>
            <View>
              <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>Vocabulary Type</AppText>
              <View style={fStyles.chips}>
                {VOCAB_TYPES.map((x) => <Chip key={x} label={x} selected={vocabType === x} onPress={() => setVocabType(vocabType === x ? null : x)} />)}
              </View>
            </View>
            <View>
              <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>Enrichment</AppText>
              <View style={fStyles.chips}>
                {LEVELS.map((x) => <Chip key={x} label={x} selected={enrichment === x} onPress={() => setEnrichment(x)} />)}
              </View>
            </View>
            <View>
              <AppText size={13} weight="medium" color={c.onSurfaceTertiary} style={{ marginBottom: 6 }}>Quality</AppText>
              <View style={fStyles.chips}>
                {QUALITY_OPTIONS.map((x) => <Chip key={x} label={x} selected={quality === x} onPress={() => setQuality(x)} />)}
              </View>
            </View>
          </>
        )}

        <AppText size={11} color={c.muted}>
          Model routing: Auto. Batched internally for safety. All output enters REVIEW — never auto-published.
        </AppText>
        {error ? <AppText size={12} color={c.error}>{error}</AppText> : null}
        <Button label={`Generate ${count || '?'} words`} icon="auto-fix" loading={submitting} onPress={create} testID="job-generate" />
      </Card>

      {/* Jobs list */}
      <AppText weight="medium" size={15} style={styles.sectionTitle}>Generation History</AppText>
      {q.isLoading ? <Loading /> : jobs.length === 0 ? (
        <AppText size={13} color={c.muted}>No jobs yet.</AppText>
      ) : jobs.map((j: Job) => (
        <Card key={j.id} padded onPress={() => setOpen(open === j.id ? null : j.id)} style={{ gap: 6 }} testID={`job-${j.id}`}>
          <View style={fStyles.jobHead}>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={13}>{j.id}</AppText>
              <AppText size={11} color={c.muted}>
                {j.params?.cefr || 'any'} · {j.params?.topic || 'general'}{j.params?.exam ? ` · ${j.params.exam}` : ''}{j.params?.part_of_speech ? ` · ${j.params.part_of_speech}` : ''} · want {j.requested_count}
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
              {j.provider ? <AppText size={11} color={c.muted}>Provider: {j.provider}</AppText> : null}
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
  advancedToggle: { flexDirection: 'row', alignItems: 'center', gap: 4 },
});
