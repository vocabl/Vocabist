import React, { useRef, useState } from 'react';
import { View, Pressable, ScrollView, TextInput, Platform, Keyboard } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import Animated, { FadeIn, FadeInUp, SlideInRight } from 'react-native-reanimated';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { CefrBadge } from '@/src/components/CefrBadge';
import { api } from '@/src/api/client';

type Question = {
  word_id: string; headword: string; mode: string; prompt: string; options: string[]; answer: string;
  input?: string; hint?: string; teach?: boolean;
  card: { headword: string; phonetic?: string; simple_definition: string; easy_meaning?: string; example?: string; cefr?: string; part_of_speech?: string; synonyms: string[] };
};

export default function Session() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { source = 'mission', ref } = useLocalSearchParams<{ source?: string; ref?: string }>();

  const startQ = useQuery({
    queryKey: ['practice-start', source, ref],
    queryFn: () => {
      const params = new URLSearchParams({ source: String(source) });
      if (ref) params.set('ref', String(ref));
      return api<{ questions: Question[]; count: number }>(`/practice/start?${params.toString()}`, { method: 'POST' });
    },
    staleTime: 0,
    gcTime: 0,
  });

  const questions = startQ.data?.questions ?? [];
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<'teach' | 'question' | 'feedback'>('teach');
  const [selected, setSelected] = useState<string | null>(null);
  const [typed, setTyped] = useState('');
  const [isCorrect, setIsCorrect] = useState(false);
  const [xpGain, setXpGain] = useState(0);
  const [stats, setStats] = useState({ answered: 0, correct: 0 });
  const [done, setDone] = useState(false);
  const [lastAnswer, setLastAnswer] = useState<{
    mastery_score?: number;
    status?: string;
    just_mastered?: boolean;
  } | null>(null);
  const [missedIds, setMissedIds] = useState<string[]>([]);
  const [masteredCount, setMasteredCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const startedAt = useRef(Date.now());
  const sessionStart = useRef(Date.now());

  // Pre-fetch slipping word IDs so we can give each question honest context
  // ("Let's strengthen this one") WITHOUT fabricating a status client-side.
  const slippingQ = useQuery({
    queryKey: ['slipping'],
    queryFn: () => api<{ count: number; words: { id: string }[] }>('/review/slipping'),
    staleTime: 60_000,
  });
  const slippingSet = React.useMemo(
    () => new Set((slippingQ.data?.words ?? []).map((w) => w.id)),
    [slippingQ.data],
  );

  const q = questions[index];
  const showTeach = phase === 'teach' && q?.teach;

  const beginQuestion = () => {
    startedAt.current = Date.now();
    setPhase('question');
  };

  const check = async () => {
    if (!q || isSubmitting || phase !== 'question') return;
    const ans = q.mode === 'spelling' ? typed.trim() : selected;
    if (!ans) return;
    setIsSubmitting(true);
    Keyboard.dismiss();
    const correct = ans.toLowerCase() === q.answer.toLowerCase();
    setIsCorrect(correct);
    setPhase('feedback');
    setStats((s) => ({ answered: s.answered + 1, correct: s.correct + (correct ? 1 : 0) }));
    setLastAnswer(null);
    if (Platform.OS !== 'web') {
      Haptics.notificationAsync(correct ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Error).catch(() => {});
    }
    try {
      const res = await api<{
        xp_gain: number;
        mastery_score: number;
        status: string;
        just_mastered: boolean;
      }>('/practice/answer', {
        method: 'POST',
        body: { word_id: q.word_id, mode: q.mode, correct, response_time_ms: Date.now() - startedAt.current },
      });
      setXpGain(res.xp_gain);
      setLastAnswer({
        mastery_score: res.mastery_score,
        status: res.status,
        just_mastered: res.just_mastered,
      });
      if (res.just_mastered) setMasteredCount((c) => c + 1);
    } catch { /* server ignored — still show local correct/incorrect */ }
    if (!correct) {
      setMissedIds((ids) => (ids.includes(q.word_id) ? ids : [...ids, q.word_id]));
    }
    setIsSubmitting(false);
  };

  const nextQuestion = async () => {
    if (index + 1 >= questions.length) {
      try {
        await api('/practice/complete', {
          method: 'POST',
          body: { answered: stats.answered, correct: stats.correct, duration_ms: Date.now() - sessionStart.current, source },
        });
      } catch { /* ignore */ }
      qc.invalidateQueries({ queryKey: ['mission'] });
      qc.invalidateQueries({ queryKey: ['progress'] });
      qc.invalidateQueries({ queryKey: ['exams'] });
      qc.invalidateQueries({ queryKey: ['slipping'] });
      qc.invalidateQueries({ queryKey: ['words'] });
      qc.invalidateQueries({ queryKey: ['saved'] });
      setDone(true);
      return;
    }
    setIndex((i) => i + 1);
    setSelected(null);
    setTyped('');
    setXpGain(0);
    setLastAnswer(null);
    setPhase('teach');
  };

  // ---- states ----
  if (startQ.isLoading) {
    return <View style={styles.center}><Icon name="loading" size={30} color={colors.brand} /><AppText size={14} color={colors.muted} style={{ marginTop: 8 }}>Preparing your session…</AppText></View>;
  }

  if (done || questions.length === 0) {
    const pct = stats.answered ? Math.round((stats.correct / stats.answered) * 100) : 0;
    const xpEarned = stats.correct * 10 + (stats.answered - stats.correct) * 2;

    // Adaptive "next action" — chosen from real signals only, never fabricated.
    const missedCsv = missedIds.join(',');
    const hasMissed = missedIds.length > 0;
    const sourceWasSlipping = String(source) === 'slipping';
    const nextActions: { label: string; icon: React.ComponentProps<typeof Icon>['name']; onPress: () => void; testID: string }[] = [];
    if (hasMissed) {
      nextActions.push({
        testID: 'completion-practise-missed',
        label: `Practise ${missedIds.length} missed`,
        icon: 'refresh',
        onPress: () => router.replace(`/session?source=list&ref=${missedCsv}`),
      });
    } else if (sourceWasSlipping) {
      nextActions.push({
        testID: 'completion-discover',
        label: 'Discover new words',
        icon: 'compass-outline',
        onPress: () => router.replace('/(tabs)/discover'),
      });
    } else {
      // Clean session with no misses — point to the remaining review backlog
      // if any (count already in cache), else discovery.
      nextActions.push({
        testID: 'completion-open-review',
        label: 'Open Review',
        icon: 'clock-outline',
        onPress: () => router.replace('/review'),
      });
    }

    return (
      <View style={[styles.summary, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }]}>
        <Animated.View entering={FadeInUp} style={styles.summaryInner}>
          <View style={styles.summaryIcon}>
            <Icon name={questions.length === 0 ? 'check-all' : 'trophy'} size={40} color={colors.brand} />
          </View>
          <AppText weight="semibold" size={26} style={{ marginTop: 20, textAlign: 'center' }}>
            {questions.length === 0
              ? 'All caught up!'
              : masteredCount > 0
              ? `${masteredCount} mastered`
              : 'Session complete'}
          </AppText>
          {questions.length === 0 ? (
            <AppText size={15} color={colors.muted} style={styles.summarySub}>Nothing to practise here right now.</AppText>
          ) : (
            <>
              <AppText size={15} color={colors.muted} style={styles.summarySub}>
                You answered {stats.correct} of {stats.answered} correctly.
                {masteredCount > 0 ? ` New word${masteredCount === 1 ? '' : 's'} mastered today.` : ''}
              </AppText>
              <View style={styles.summaryStats}>
                <View style={styles.sStat}>
                  <AppText weight="semibold" size={24} color={colors.brand}>{pct}%</AppText>
                  <AppText size={12} color={colors.muted}>accuracy</AppText>
                </View>
                <View style={styles.sDivider} />
                <View style={styles.sStat}>
                  <AppText weight="semibold" size={24} color={colors.warning}>+{xpEarned}</AppText>
                  <AppText size={12} color={colors.muted}>XP earned</AppText>
                </View>
                {masteredCount > 0 ? (
                  <>
                    <View style={styles.sDivider} />
                    <View style={styles.sStat}>
                      <AppText weight="semibold" size={24} color={colors.success}>{masteredCount}</AppText>
                      <AppText size={12} color={colors.muted}>mastered</AppText>
                    </View>
                  </>
                ) : null}
              </View>
            </>
          )}
        </Animated.View>
        <View style={{ gap: 10 }}>
          {nextActions.map((a) => (
            <Button
              key={a.testID}
              testID={a.testID}
              label={a.label}
              icon={a.icon}
              onPress={a.onPress}
            />
          ))}
          <Button
            testID="session-done-button"
            label="Done"
            variant="ghost"
            onPress={() => router.replace('/(tabs)/home')}
          />
        </View>
      </View>
    );
  }

  const progress = (index + (phase === 'feedback' ? 1 : 0)) / questions.length;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      {/* top bar */}
      <View style={styles.topBar}>
        <Pressable
          testID="close-session-button"
          onPress={() => router.replace('/(tabs)/home')}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Close session"
        >
          <Icon name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <AppText size={12} weight="medium" color={colors.onSurfaceTertiary} style={styles.sessionTitle}>
            {sessionTitle(String(source))}
          </AppText>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.max(4, progress * 100)}%` }]} />
          </View>
        </View>
        <AppText size={13} weight="medium" color={colors.muted}>{index + 1}/{questions.length}</AppText>
      </View>

      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        {showTeach ? (
          <Animated.View key={`teach-${index}`} entering={FadeIn.duration(200)} style={styles.teachCard} testID="teach-card">
            <View style={styles.teachTop}>
              <AppText size={13} weight="medium" color={colors.brand}>NEW WORD</AppText>
              <CefrBadge level={q.card.cefr} small />
            </View>
            <AppText weight="semibold" size={36} style={{ marginTop: 12 }}>{q.card.headword}</AppText>
            {q.card.phonetic ? <AppText size={16} color={colors.muted} style={{ marginTop: 4 }}>{q.card.phonetic}</AppText> : null}
            <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>{q.card.part_of_speech}</AppText>
            <View style={styles.teachDef}>
              <AppText size={18} style={{ lineHeight: 26 }}>{q.card.simple_definition}</AppText>
            </View>
            {q.card.example ? (
              <View style={styles.exampleBox}>
                <Icon name="format-quote-open" size={18} color={colors.brandSecondary} />
                <AppText size={15} color={colors.onSurfaceTertiary} style={{ flex: 1, fontStyle: 'italic', lineHeight: 22 }}>{q.card.example}</AppText>
              </View>
            ) : null}
          </Animated.View>
        ) : (
          <Animated.View key={`q-${index}`} entering={SlideInRight.duration(220)}>
            {/* Adaptive context header — real signal, no fabrication */}
            <View style={styles.contextRow}>
              {slippingSet.has(q.word_id) ? (
                <>
                  <Icon name="clock-alert-outline" size={14} color={colors.warning} />
                  <AppText size={12} weight="medium" color={colors.warning} style={styles.contextText}>
                    LET&apos;S STRENGTHEN THIS ONE
                  </AppText>
                </>
              ) : (
                <>
                  <Icon name="refresh" size={14} color={colors.onSurfaceTertiary} />
                  <AppText size={12} weight="medium" color={colors.onSurfaceTertiary} style={styles.contextText}>
                    REVIEW
                  </AppText>
                </>
              )}
            </View>
            <AppText size={13} weight="medium" color={colors.muted} style={{ marginBottom: 8 }}>{modeLabel(q.mode)}</AppText>
            <AppText weight="medium" size={22} style={styles.prompt}>{q.prompt}</AppText>

            {q.mode === 'spelling' ? (
              <View>
                <TextInput
                  testID="spelling-input"
                  value={typed}
                  onChangeText={setTyped}
                  editable={phase !== 'feedback' && !isSubmitting}
                  autoCapitalize="none"
                  autoCorrect={false}
                  placeholder="Type the word"
                  placeholderTextColor={colors.muted}
                  accessibilityLabel="Type the spelling of the word"
                  returnKeyType="done"
                  onSubmitEditing={() => check()}
                  style={[styles.spellInput, phase === 'feedback' && (isCorrect ? styles.optCorrect : styles.optWrong)]}
                />
                {q.hint ? <AppText size={14} color={colors.muted} style={{ marginTop: 10 }}>Hint: {q.hint}</AppText> : null}
              </View>
            ) : (
              <View style={{ gap: 12 }}>
                {q.options.map((opt) => {
                  const isSel = selected === opt;
                  const isAns = opt.toLowerCase() === q.answer.toLowerCase();
                  let optStyle = styles.opt;
                  if (phase === 'feedback') {
                    if (isAns) optStyle = { ...styles.opt, ...styles.optCorrect };
                    else if (isSel) optStyle = { ...styles.opt, ...styles.optWrong };
                  } else if (isSel) {
                    optStyle = { ...styles.opt, ...styles.optSelected };
                  }
                  return (
                    <Pressable
                      key={opt}
                      testID={`option-${opt}`}
                      disabled={phase === 'feedback' || isSubmitting}
                      onPress={() => setSelected(opt)}
                      style={optStyle}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: isSel, disabled: phase === 'feedback' || isSubmitting }}
                      accessibilityLabel={opt}
                    >
                      <AppText size={16} weight="medium" color={colors.onSurface} style={{ flex: 1 }}>{opt}</AppText>
                      {phase === 'feedback' && isAns ? <Icon name="check-circle" size={20} color={colors.success} /> : null}
                      {phase === 'feedback' && isSel && !isAns ? <Icon name="close-circle" size={20} color={colors.error} /> : null}
                    </Pressable>
                  );
                })}
              </View>
            )}
          </Animated.View>
        )}
      </ScrollView>

      {/* bottom banner */}
      <View style={[
        styles.banner,
        { paddingBottom: insets.bottom + 16 },
        phase === 'feedback' && (isCorrect ? styles.bannerCorrect : styles.bannerWrong),
      ]}>
        {phase === 'feedback' ? (
          <Animated.View entering={FadeInUp.duration(180)} style={styles.feedback}>
            <View style={styles.feedbackRow}>
              <Icon name={isCorrect ? 'check-circle' : 'close-circle'} size={22} color={isCorrect ? colors.success : colors.error} />
              <AppText weight="semibold" size={17} color={isCorrect ? colors.success : colors.error}>
                {isCorrect ? `Correct! +${xpGain} XP` : 'Not quite'}
              </AppText>
              {lastAnswer?.just_mastered ? (
                <View style={styles.masteredPill}>
                  <Icon name="check-decagram" size={12} color={colors.onBrand} />
                  <AppText size={11} weight="semibold" color={colors.onBrand}>MASTERED</AppText>
                </View>
              ) : null}
            </View>
            {!isCorrect ? (
              <AppText size={14} color={colors.onSurfaceTertiary} style={{ marginTop: 4 }}>
                Answer: <AppText size={14} weight="medium" color={colors.onSurface}>{q.answer}</AppText>
              </AppText>
            ) : null}
            {q?.card?.simple_definition ? (
              <AppText size={13} color={colors.muted} numberOfLines={2} style={{ marginTop: 4, lineHeight: 19 }}>
                <AppText size={13} weight="medium" color={colors.onSurfaceTertiary}>{q.card.headword}</AppText>
                {' — '}{q.card.simple_definition}
              </AppText>
            ) : null}
            {lastAnswer?.mastery_score != null ? (
              <View
                style={styles.masteryRow}
                accessibilityRole="progressbar"
                accessibilityLabel="Mastery"
                accessibilityValue={{
                  min: 0,
                  max: 100,
                  now: Math.round(lastAnswer.mastery_score),
                }}
              >
                <AppText size={12} weight="medium" color={colors.onSurfaceTertiary} style={{ minWidth: 64 }}>
                  Mastery
                </AppText>
                <View style={styles.masteryTrack}>
                  <View
                    style={[
                      styles.masteryFill,
                      {
                        width: `${Math.min(100, Math.max(2, Math.round(lastAnswer.mastery_score)))}%`,
                        backgroundColor: isCorrect ? colors.success : colors.warning,
                      },
                    ]}
                  />
                </View>
                <AppText size={12} weight="medium" color={colors.onSurfaceTertiary}>
                  {Math.round(lastAnswer.mastery_score)}%
                </AppText>
              </View>
            ) : null}
          </Animated.View>
        ) : null}

        {showTeach ? (
          <Button
            testID="teach-continue-button"
            label="Practice this word"
            onPress={beginQuestion}
            accessibilityLabel={`Start practising ${q.card.headword}`}
          />
        ) : phase === 'question' ? (
          <Button
            testID="check-button"
            label={isSubmitting ? 'Checking…' : 'Check'}
            onPress={check}
            disabled={isSubmitting || (q.mode === 'spelling' ? !typed.trim() : !selected)}
            accessibilityLabel="Submit answer"
          />
        ) : (
          <Button
            testID="next-button"
            label={index + 1 >= questions.length ? 'Finish' : 'Continue'}
            onPress={nextQuestion}
            accessibilityLabel={index + 1 >= questions.length ? 'Finish session' : 'Next question'}
          />
        )}
      </View>
    </View>
  );
}

function sessionTitle(source: string): string {
  switch (source) {
    case 'slipping':
    case 'review':
      return 'REVIEW';
    case 'mission':
      return "TODAY'S MISSION";
    case 'word':
      return 'WORD PRACTICE';
    case 'topic':
      return 'TOPIC PRACTICE';
    case 'exam':
      return 'EXAM PRACTICE';
    case 'saved':
      return 'SAVED WORDS';
    case 'list':
      return 'PRACTICE';
    default:
      return 'PRACTICE';
  }
}

function modeLabel(mode: string) {
  return (
    ({
      multiple_choice: 'Choose the meaning',
      synonym_select: 'Pick the synonym',
      antonym_select: 'Pick the opposite',
      true_false: 'True or false',
      spelling: 'Spell it',
      fill_blank: 'Fill the blank',
      definition_recall: 'Recall the meaning',
      sentence_completion: 'Complete the sentence',
      context_choice: 'Which fits best?',
      word_usage: 'How is it used?',
      confusing_words: "Don't mix these up",
      word_family: 'Explore the word family',
      mixed_adaptive: 'Adaptive practice',
    } as Record<string, string>)[mode] ?? 'Question'
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: t.colors.surface },
  topBar: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, paddingHorizontal: t.spacing.lg, paddingBottom: t.spacing.md },
  progressTrack: { flex: 1, height: 8, borderRadius: 4, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 4 },
  sessionTitle: { letterSpacing: 0.5, marginBottom: 4 },
  body: { padding: t.spacing.lg, paddingTop: t.spacing.md, flexGrow: 1 },
  teachCard: { backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.lg, borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.xl, ...t.shadow.sm },
  teachTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  teachDef: { marginTop: t.spacing.lg },
  exampleBox: { flexDirection: 'row', gap: t.spacing.sm, backgroundColor: t.colors.surfaceTertiary, borderRadius: t.radius.md, padding: t.spacing.lg, marginTop: t.spacing.lg },
  prompt: { marginBottom: t.spacing.xl, lineHeight: 30 },
  contextRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginBottom: t.spacing.sm,
  },
  contextText: { letterSpacing: 0.5 },
  opt: { flexDirection: 'row', alignItems: 'center', backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1.5, borderColor: t.colors.border, paddingVertical: t.spacing.lg, paddingHorizontal: t.spacing.lg, minHeight: 56 },
  optSelected: { borderColor: t.colors.brand, backgroundColor: t.colors.brandTertiary },
  optCorrect: { borderColor: t.colors.success, backgroundColor: '#E8F2EC' },
  optWrong: { borderColor: t.colors.error, backgroundColor: '#F7E9E9' },
  spellInput: { backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1.5, borderColor: t.colors.border, paddingHorizontal: t.spacing.lg, height: 58, fontFamily: t.fontFamily.medium, fontSize: 20, color: t.colors.onSurface },
  banner: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.lg, borderTopWidth: 1, borderTopColor: t.colors.divider, backgroundColor: t.colors.surface },
  bannerCorrect: { backgroundColor: '#EEF6F0', borderTopColor: '#D5E8DC' },
  bannerWrong: { backgroundColor: '#FBF0F0', borderTopColor: '#EFD9D9' },
  feedback: { marginBottom: t.spacing.md, gap: 2 },
  feedbackRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  masteredPill: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: t.colors.brand,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: t.radius.pill,
    marginLeft: 'auto',
  },
  masteryRow: {
    flexDirection: 'row', alignItems: 'center',
    gap: t.spacing.sm, marginTop: 10,
  },
  masteryTrack: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: t.colors.surfaceTertiary,
    overflow: 'hidden',
  },
  masteryFill: { height: '100%', borderRadius: 3 },
  summary: { flex: 1, backgroundColor: t.colors.surface, paddingHorizontal: t.spacing.xl, justifyContent: 'space-between' },
  summaryInner: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  summaryIcon: { width: 88, height: 88, borderRadius: 44, backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center' },
  summarySub: { marginTop: 8, textAlign: 'center' },
  summaryStats: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.xl, marginTop: t.spacing.xxl },
  sStat: { alignItems: 'center', gap: 2 },
  sDivider: { width: 1, height: 40, backgroundColor: t.colors.border },
}));
