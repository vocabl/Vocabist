import React from 'react';
import { View, ScrollView, Pressable } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { CefrBadge } from '@/src/components/CefrBadge';
import { Skeleton } from '@/src/components/Skeleton';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

const HEADER_IMG = 'https://images.unsplash.com/photo-1661264083807-5e6a54fb12da?crop=entropy&cs=srgb&fm=jpg&w=900&q=80';

type ExamDetail = {
  exam: { slug: string; name: string; full_name: string; description: string };
  words: any[]; total_words: number; mastered: number; learning: number;
  days_left: number | null; is_active: boolean; target_score: number | null; words_per_day: number | null; locked?: boolean;
};

export default function ExamDetail() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { slug } = useLocalSearchParams<{ slug: string }>();

  const q = useQuery({ queryKey: ['exam', slug], queryFn: () => api<ExamDetail>(`/exams/${slug}`) });
  const d = q.data;

  const setActive = async () => {
    try {
      await api('/profile/exam-goal', { method: 'POST', body: { exam_slug: slug } });
      qc.invalidateQueries({ queryKey: ['exam', slug] });
      qc.invalidateQueries({ queryKey: ['exams'] });
      qc.invalidateQueries({ queryKey: ['mission'] });
      toast.show(`${d?.exam.name} set as your goal`, 'success');
    } catch { toast.show('Could not set goal', 'error'); }
  };

  const pct = d && d.total_words ? Math.round((d.mastered / d.total_words) * 100) : 0;

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 100 }} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <Image source={HEADER_IMG} style={styles.heroImg} contentFit="cover" />
          <View style={styles.heroOverlay} />
          <Pressable testID="exam-back-button" onPress={() => router.back()} hitSlop={10} style={[styles.back, { top: insets.top + 8 }]}>
            <Icon name="chevron-left" size={26} color={colors.onSurface} />
          </Pressable>
        </View>

        {q.isLoading ? (
          <View style={styles.body}><Skeleton width={160} height={32} /><Skeleton height={90} rounded={16} /></View>
        ) : q.isError || !d ? (
          <View style={styles.body}><AppText color={colors.muted} style={{ marginBottom: 12 }}>Couldn't load this exam.</AppText><Button label="Retry" variant="secondary" size="md" onPress={() => q.refetch()} /></View>
        ) : (
          <View style={styles.body}>
            <View style={styles.titleRow}>
              <View style={styles.initials}><AppText weight="semibold" size={18} color={colors.onBrandTertiary}>{d.exam.name.slice(0, 3).toUpperCase()}</AppText></View>
              <View style={{ flex: 1 }}>
                <AppText weight="semibold" size={26}>{d.exam.name}</AppText>
                <AppText size={13} color={colors.muted} numberOfLines={2} style={{ marginTop: 2 }}>{d.exam.full_name}</AppText>
              </View>
            </View>

            {/* status row */}
            <View style={styles.statRow}>
              {d.is_active && d.days_left != null ? (
                <View style={styles.statBox}><AppText weight="semibold" size={22} color={colors.warning}>{d.days_left}</AppText><AppText size={12} color={colors.muted}>days left</AppText></View>
              ) : (
                <View style={styles.statBox}><AppText weight="semibold" size={22}>{d.total_words}</AppText><AppText size={12} color={colors.muted}>key words</AppText></View>
              )}
              <View style={styles.statBox}><AppText weight="semibold" size={22} color={colors.success}>{d.mastered}</AppText><AppText size={12} color={colors.muted}>mastered</AppText></View>
              <View style={styles.statBox}><AppText weight="semibold" size={22} color={colors.brand}>{d.words_per_day ?? Math.max(5, 12)}</AppText><AppText size={12} color={colors.muted}>words/day</AppText></View>
            </View>

            {/* progress */}
            <View style={styles.progressCard}>
              <View style={styles.progressHead}>
                <AppText weight="medium" size={15}>Mastery progress</AppText>
                <AppText size={14} weight="medium" color={colors.brand}>{pct}%</AppText>
              </View>
              <View style={styles.track}><View style={[styles.fill, { width: `${pct}%` }]} /></View>
              <AppText size={13} color={colors.muted} style={{ marginTop: 8 }}>{d.mastered} of {d.total_words} words mastered</AppText>
            </View>

            {!d.is_active ? (
              <Button label="Set as my exam goal" icon="target" variant="secondary" onPress={setActive} style={{ marginTop: 16 }} testID="set-exam-goal-button" />
            ) : null}

            <AppText weight="medium" size={16} style={styles.section}>Vocabulary ({d.total_words})</AppText>
            <View style={{ gap: 10 }}>
              {d.words.map((w) => (
                <Pressable key={w.id} onPress={() => router.push(`/word/${w.id}`)} style={styles.wordRow} testID={`exam-word-${w.id}`}>
                  <View style={{ flex: 1 }}>
                    <View style={styles.wordHead}>
                      <AppText weight="medium" size={16}>{w.headword}</AppText>
                      <CefrBadge level={w.cefr} small />
                      {w.status === 'MASTERED' ? <Icon name="check-decagram" size={16} color={colors.success} /> : null}
                    </View>
                    <AppText size={13} color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>{w.simple_definition}</AppText>
                  </View>
                  <Icon name="chevron-right" size={20} color={colors.muted} />
                </Pressable>
              ))}
            </View>
          </View>
        )}
      </ScrollView>

      {d && d.total_words > 0 ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          {d.locked ? (
            <Button label="Unlock with Pro" icon="crown-outline" onPress={() => router.push('/paywall')} testID="exam-unlock-button" />
          ) : (
            <Button label="Start practice" icon="play" onPress={() => router.push(`/session?source=exam&ref=${slug}`)} testID="exam-practice-button" />
          )}
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  hero: { height: 160, backgroundColor: t.colors.surfaceTertiary },
  heroImg: { width: '100%', height: '100%' },
  heroOverlay: { ...({ position: 'absolute' } as any), top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(253,253,251,0.35)' },
  back: { position: 'absolute', left: 16, width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.9)', alignItems: 'center', justifyContent: 'center' },
  body: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.lg, gap: t.spacing.md },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  initials: { width: 56, height: 56, borderRadius: t.radius.md, backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center' },
  statRow: { flexDirection: 'row', gap: t.spacing.md, marginTop: t.spacing.sm },
  statBox: { flex: 1, alignItems: 'center', backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border, paddingVertical: t.spacing.lg, gap: 2 },
  progressCard: { backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg, marginTop: t.spacing.sm },
  progressHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: t.spacing.md },
  track: { height: 8, borderRadius: 4, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 4 },
  section: { marginTop: t.spacing.lg },
  wordRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg },
  wordHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  cta: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md, backgroundColor: t.colors.surface, borderTopWidth: 1, borderTopColor: t.colors.divider },
}));
