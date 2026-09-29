import React, { useState } from 'react';
import { View, Pressable, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInRight } from 'react-native-reanimated';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { useAuth } from '@/src/auth/AuthContext';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

const REASONS = [
  { key: 'School', icon: 'school-outline' },
  { key: 'Competitive exams', icon: 'trophy-outline' },
  { key: 'IELTS', icon: 'earth' },
  { key: 'TOEFL', icon: 'airplane' },
  { key: 'SAT', icon: 'book-education-outline' },
  { key: 'GRE', icon: 'graduation-cap' },
  { key: 'Study abroad', icon: 'passport' },
  { key: 'Career', icon: 'briefcase-outline' },
  { key: 'Everyday English', icon: 'coffee-outline' },
  { key: 'Academic English', icon: 'library-outline' },
];
const LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'Not sure'];
const MINUTES = [5, 10, 15, 30];
const EXAMS = [
  { slug: 'ielts', name: 'IELTS' },
  { slug: 'toefl', name: 'TOEFL' },
  { slug: 'gre', name: 'GRE' },
  { slug: 'sat', name: 'SAT' },
  { slug: 'gmat', name: 'GMAT' },
  { slug: 'cefr', name: 'CEFR' },
];
const TIMELINES = [
  { key: '1m', label: 'In 1 month', months: 1 },
  { key: '3m', label: 'In 3 months', months: 3 },
  { key: '6m', label: 'In 6 months', months: 6 },
  { key: 'none', label: 'No exam / no date', months: 0 },
];

export default function Onboarding() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { refresh } = useAuth();
  const toast = useToast();

  const [step, setStep] = useState(0);
  const [reason, setReason] = useState<string | null>(null);
  const [level, setLevel] = useState<string | null>(null);
  const [minutes, setMinutes] = useState<number | null>(null);
  const [examSlug, setExamSlug] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const totalSteps = 4;
  const canNext = [reason, level, minutes, true][step];

  const next = async () => {
    if (step < totalSteps - 1) {
      setStep((s) => s + 1);
      return;
    }
    setSaving(true);
    try {
      let examDate: string | null = null;
      const tl = TIMELINES.find((t) => t.key === timeline);
      if (examSlug && tl && tl.months > 0) {
        const d = new Date();
        d.setMonth(d.getMonth() + tl.months);
        examDate = d.toISOString().slice(0, 10);
      }
      await api('/onboarding', {
        method: 'POST',
        body: {
          reason,
          level: level === 'Not sure' ? 'B1' : level,
          daily_minutes: minutes,
          exam_slug: examSlug,
          exam_date: examDate,
          target_score: null,
        },
      });
      await refresh();
      router.replace('/(tabs)/home');
    } catch {
      toast.show('Could not save. Try again.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const back = () => {
    if (step === 0) router.back();
    else setStep((s) => s - 1);
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable testID="onboarding-back" onPress={back} hitSlop={10} style={styles.backBtn}>
          <Icon name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={styles.dots}>
          {Array.from({ length: totalSteps }).map((_, i) => (
            <View key={i} style={[styles.dot, i <= step && styles.dotActive]} />
          ))}
        </View>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {step === 0 && (
          <Animated.View entering={FadeInRight.duration(220)}>
            <AppText weight="semibold" size={26} style={styles.q}>Why are you learning English?</AppText>
            <AppText size={15} color={colors.muted} style={styles.hint}>Pick your main goal. You can change it later.</AppText>
            <View style={styles.grid}>
              {REASONS.map((r) => (
                <Pressable
                  key={r.key}
                  testID={`reason-${r.key}`}
                  onPress={() => setReason(r.key)}
                  style={[styles.gridItem, reason === r.key && styles.gridItemActive]}
                >
                  <Icon name={r.icon as any} size={22} color={reason === r.key ? colors.brand : colors.onSurfaceTertiary} />
                  <AppText size={14} weight="medium" color={reason === r.key ? colors.onSurface : colors.onSurfaceTertiary}>{r.key}</AppText>
                </Pressable>
              ))}
            </View>
          </Animated.View>
        )}

        {step === 1 && (
          <Animated.View entering={FadeInRight.duration(220)}>
            <AppText weight="semibold" size={26} style={styles.q}>What's your current level?</AppText>
            <AppText size={15} color={colors.muted} style={styles.hint}>CEFR level — not sure is fine.</AppText>
            <View style={styles.pills}>
              {LEVELS.map((l) => (
                <Pressable key={l} testID={`level-${l}`} onPress={() => setLevel(l)} style={[styles.pill, level === l && styles.pillActive]}>
                  <AppText size={16} weight="medium" color={level === l ? colors.onBrand : colors.onSurface}>{l}</AppText>
                </Pressable>
              ))}
            </View>
          </Animated.View>
        )}

        {step === 2 && (
          <Animated.View entering={FadeInRight.duration(220)}>
            <AppText weight="semibold" size={26} style={styles.q}>Daily study time</AppText>
            <AppText size={15} color={colors.muted} style={styles.hint}>How many minutes a day can you commit?</AppText>
            <View style={styles.timeList}>
              {MINUTES.map((m) => (
                <Pressable key={m} testID={`minutes-${m}`} onPress={() => setMinutes(m)} style={[styles.timeItem, minutes === m && styles.timeItemActive]}>
                  <AppText size={18} weight="medium" color={colors.onSurface}>{m} minutes</AppText>
                  <AppText size={13} color={colors.muted}>~{Math.max(5, Math.round(m * 1.2))} words / day</AppText>
                  {minutes === m ? <View style={styles.check}><Icon name="check" size={16} color={colors.onBrand} /></View> : null}
                </Pressable>
              ))}
            </View>
          </Animated.View>
        )}

        {step === 3 && (
          <Animated.View entering={FadeInRight.duration(220)}>
            <AppText weight="semibold" size={26} style={styles.q}>Target an exam? (optional)</AppText>
            <AppText size={15} color={colors.muted} style={styles.hint}>We'll build a schedule and countdown for it.</AppText>
            <View style={styles.pills}>
              {EXAMS.map((e) => (
                <Pressable key={e.slug} testID={`exam-${e.slug}`} onPress={() => setExamSlug(examSlug === e.slug ? null : e.slug)} style={[styles.pill, examSlug === e.slug && styles.pillActive]}>
                  <AppText size={15} weight="medium" color={examSlug === e.slug ? colors.onBrand : colors.onSurface}>{e.name}</AppText>
                </Pressable>
              ))}
            </View>
            {examSlug ? (
              <View style={{ marginTop: 8 }}>
                <AppText size={15} weight="medium" style={{ marginBottom: 12 }}>When is it?</AppText>
                <View style={styles.timeList}>
                  {TIMELINES.map((t) => (
                    <Pressable key={t.key} testID={`timeline-${t.key}`} onPress={() => setTimeline(t.key)} style={[styles.timeItem, timeline === t.key && styles.timeItemActive]}>
                      <AppText size={16} weight="medium" color={colors.onSurface}>{t.label}</AppText>
                      {timeline === t.key ? <View style={styles.check}><Icon name="check" size={16} color={colors.onBrand} /></View> : null}
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}
          </Animated.View>
        )}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
        <Button
          testID="onboarding-continue"
          label={step === totalSteps - 1 ? 'Build my plan' : 'Continue'}
          onPress={next}
          loading={saving}
          disabled={!canNext}
        />
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: t.spacing.md, marginBottom: t.spacing.lg },
  backBtn: { width: 40, height: 40, justifyContent: 'center' },
  dots: { flex: 1, flexDirection: 'row', justifyContent: 'center', gap: t.spacing.sm },
  dot: { width: 28, height: 5, borderRadius: 3, backgroundColor: t.colors.border },
  dotActive: { backgroundColor: t.colors.brand },
  scroll: { paddingHorizontal: t.spacing.xl, paddingBottom: t.spacing.xl },
  q: { marginBottom: t.spacing.sm },
  hint: { marginBottom: t.spacing.xl, lineHeight: 21 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md },
  gridItem: {
    width: '47%', flexGrow: 1, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border,
    backgroundColor: t.colors.surfaceSecondary, padding: t.spacing.lg, gap: t.spacing.sm, minHeight: 88, justifyContent: 'center',
  },
  gridItemActive: { borderColor: t.colors.brand, backgroundColor: t.colors.brandTertiary },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md },
  pill: {
    paddingHorizontal: t.spacing.xl, height: 52, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border,
    backgroundColor: t.colors.surfaceSecondary, alignItems: 'center', justifyContent: 'center', minWidth: 72,
  },
  pillActive: { backgroundColor: t.colors.brand, borderColor: t.colors.brand },
  timeList: { gap: t.spacing.md },
  timeItem: {
    borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border, backgroundColor: t.colors.surfaceSecondary,
    paddingVertical: t.spacing.lg, paddingHorizontal: t.spacing.xl, gap: 2,
  },
  timeItemActive: { borderColor: t.colors.brand, backgroundColor: t.colors.brandTertiary },
  check: { position: 'absolute', right: 16, top: 18, width: 24, height: 24, borderRadius: 12, backgroundColor: t.colors.brand, alignItems: 'center', justifyContent: 'center' },
  footer: { paddingHorizontal: t.spacing.xl, paddingTop: t.spacing.sm, borderTopWidth: 1, borderTopColor: t.colors.divider, backgroundColor: t.colors.surface },
}));
