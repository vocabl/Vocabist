import React from 'react';
import { View, ScrollView, Pressable, RefreshControl, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { BlurView } from 'expo-blur';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { ProgressRing } from '@/src/components/ProgressRing';
import { Skeleton } from '@/src/components/Skeleton';
import { useAuth } from '@/src/auth/AuthContext';
import { api } from '@/src/api/client';

const HERO_BG = 'https://images.unsplash.com/photo-1619252584172-a83a949b6efd?crop=entropy&cs=srgb&fm=jpg&w=900&q=80';
// BlurView on Android/web is expensive and inconsistent — iOS only, soft wash elsewhere.
const USE_BLUR = Platform.OS === 'ios';

type Mission = {
  total_words: number; review_count: number; new_count: number; estimated_minutes: number;
  streak: number; xp: number; daily_minutes: number;
  continue_word: { id: string; headword: string; simple_definition: string; cefr?: string } | null;
};
type Progress = {
  words_learned: number; words_mastered: number; accuracy: number; streak: number;
  xp: number; level: number; xp_into_level: number; xp_per_level: number;
};

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function Home() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();

  const missionQ = useQuery({ queryKey: ['mission'], queryFn: () => api<Mission>('/mission') });
  const progressQ = useQuery({ queryKey: ['progress'], queryFn: () => api<Progress>('/progress') });
  const examsQ = useQuery({ queryKey: ['exams'], queryFn: () => api<any>('/exams') });
  const slippingQ = useQuery({ queryKey: ['slipping'], queryFn: () => api<{ count: number; words: any[] }>('/review/slipping') });

  const refreshing = missionQ.isRefetching || progressQ.isRefetching;
  const onRefresh = () => { missionQ.refetch(); progressQ.refetch(); examsQ.refetch(); };

  const m = missionQ.data;
  const p = progressQ.data;
  const firstName = (user?.name || 'there').split(' ')[0];
  const target = 500;
  const activeExam = examsQ.data?.exams?.find((e: any) => e.active);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 12, paddingBottom: 32 }]}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
    >
      <AppText size={15} color={colors.muted}>{greeting()},</AppText>
      <AppText weight="semibold" size={28} style={styles.name}>{firstName}</AppText>

      {/* Mission hero — big only when there's actual work */}
      {missionQ.isLoading ? (
        <Skeleton height={200} rounded={20} style={{ marginTop: 8 }} />
      ) : missionQ.isError ? (
        <Card style={{ marginTop: 8 }}>
          <AppText size={15} color={colors.muted} style={{ marginBottom: 12 }}>Couldn't load your mission.</AppText>
          <Button label="Tap to retry" variant="secondary" size="md" onPress={() => missionQ.refetch()} />
        </Card>
      ) : m && m.total_words > 0 ? (
        <Animated.View entering={FadeInDown.duration(280)} style={styles.heroWrap} testID="today-mission-card">
          <Image source={HERO_BG} style={styles.heroBg} contentFit="cover" transition={200} />
          {USE_BLUR ? (
            <BlurView intensity={28} tint="light" style={styles.heroBlur}>
              <View style={styles.heroInner}>
                <HeroContent m={m} onStart={() => router.push('/session?source=mission')} />
              </View>
            </BlurView>
          ) : (
            <View style={styles.heroInnerFallback}>
              <HeroContent m={m} onStart={() => router.push('/session?source=mission')} />
            </View>
          )}
        </Animated.View>
      ) : (
        // Compact caught-up state — not a dominant hero
        <Animated.View entering={FadeInDown.duration(240)}>
          <Card style={styles.caughtUpCard} testID="today-mission-card">
            <View style={styles.caughtUpIcon}>
              <Icon name="check-all" size={22} color={colors.success} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={17}>You're all caught up</AppText>
              <AppText size={14} color={colors.muted} style={{ marginTop: 2 }}>
                No reviews due. Discover new words to keep growing.
              </AppText>
            </View>
            <Button
              testID="discover-button"
              label="Discover"
              variant="secondary"
              size="md"
              onPress={() => router.push('/(tabs)/discover')}
            />
          </Card>
        </Animated.View>
      )}

      {/* Smart review nudge — urgency first, above stats */}
      {slippingQ.data && slippingQ.data.count > 0 ? (
        <Card style={styles.slipCard} onPress={() => router.push('/session?source=slipping')} testID="slipping-card">
          <View style={[styles.statIcon, { backgroundColor: '#FBEAEA', marginBottom: 0 }]}>
            <Icon name="clock-alert-outline" size={20} color={colors.error} />
          </View>
          <View style={{ flex: 1 }}>
            <AppText weight="medium" size={16}>Slipping from memory</AppText>
            <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>
              {slippingQ.data.count} word{slippingQ.data.count === 1 ? '' : 's'} to review before you forget
            </AppText>
          </View>
          <Icon name="chevron-right" size={22} color={colors.muted} />
        </Card>
      ) : null}

      {/* Stats row */}
      <View style={styles.statsRow}>
        <Card style={styles.statCard} testID="streak-card">
          <View style={[styles.statIcon, { backgroundColor: '#FBEEDD' }]}>
            <Icon name="fire" size={20} color={colors.warning} />
          </View>
          <AppText weight="semibold" size={22}>{p?.streak ?? m?.streak ?? 0}</AppText>
          <AppText size={12} color={colors.muted}>day streak</AppText>
        </Card>
        <Card style={styles.statCard} testID="level-card">
          <View style={[styles.statIcon, { backgroundColor: colors.brandTertiary }]}>
            <Icon name="lightning-bolt" size={20} color={colors.brand} />
          </View>
          <AppText weight="semibold" size={22}>{p?.xp ?? m?.xp ?? 0}</AppText>
          <AppText size={12} color={colors.muted}>XP · Level {p?.level ?? 1}</AppText>
        </Card>
      </View>

      {/* Vocabulary progress */}
      <Card style={styles.progressCard} testID="vocab-progress-card">
        <View style={{ flex: 1 }}>
          <AppText weight="medium" size={16}>Vocabulary progress</AppText>
          <AppText size={13} color={colors.muted} style={{ marginTop: 4 }}>
            {p?.words_mastered ?? 0} mastered · {p?.words_learned ?? 0} learned
          </AppText>
          <View style={styles.miniStat}>
            <Icon name="check-decagram-outline" size={16} color={colors.success} />
            <AppText size={13} color={colors.onSurfaceTertiary}>{p?.accuracy ?? 0}% accuracy</AppText>
          </View>
        </View>
        <ProgressRing
          size={92}
          strokeWidth={10}
          progress={(p?.words_mastered ?? 0) / target}
          centerLabel={`${p?.words_mastered ?? 0}`}
          centerSub={`/ ${target}`}
        />
      </Card>

      {/* Active exam */}
      {activeExam ? (
        <Card style={styles.examCard} onPress={() => router.push(`/exam/${activeExam.slug}`)} testID="active-exam-card">
          <View style={styles.examBadge}>
            <AppText weight="semibold" size={13} color={colors.onBrandTertiary}>{activeExam.name}</AppText>
          </View>
          <View style={{ flex: 1 }}>
            <AppText weight="medium" size={16}>{activeExam.name} goal</AppText>
            <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>{activeExam.word_count} key words to master</AppText>
          </View>
          <Icon name="chevron-right" size={22} color={colors.muted} />
        </Card>
      ) : null}

      {/* Continue */}
      {m?.continue_word ? (
        <Pressable testID="continue-word-card" onPress={() => router.push(`/word/${m.continue_word!.id}`)}>
          <Card style={styles.continueCard}>
            <View style={[styles.statIcon, { backgroundColor: colors.brandTertiary }]}>
              <Icon name="book-open-variant" size={20} color={colors.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText size={12} color={colors.muted}>Continue learning</AppText>
              <AppText weight="medium" size={17} style={{ marginTop: 2 }}>{m.continue_word.headword}</AppText>
            </View>
            <Icon name="chevron-right" size={22} color={colors.muted} />
          </Card>
        </Pressable>
      ) : null}
    </ScrollView>
  );
}

function HeroContent({ m, onStart }: { m: Mission; onStart: () => void }) {
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <>
      <View style={styles.missionTag}>
        <Icon name="target" size={16} color={colors.brand} />
        <AppText size={13} weight="medium" color={colors.brand}>Today's Mission</AppText>
      </View>
      <AppText weight="semibold" size={26} style={styles.heroTitle}>
        {m.total_words} words · {m.estimated_minutes} min
      </AppText>
      <View style={styles.missionRow}>
        {m.review_count > 0 ? (
          <View style={styles.missionPill}>
            <Icon name="refresh" size={15} color={colors.onSurfaceTertiary} />
            <AppText size={13} color={colors.onSurfaceTertiary}>{m.review_count} to review</AppText>
          </View>
        ) : null}
        {m.new_count > 0 ? (
          <View style={styles.missionPill}>
            <Icon name="star-four-points-outline" size={15} color={colors.onSurfaceTertiary} />
            <AppText size={13} color={colors.onSurfaceTertiary}>{m.new_count} new</AppText>
          </View>
        ) : null}
      </View>
      <Button
        testID="start-mission-button"
        label="Start"
        icon="play"
        onPress={onStart}
        style={{ marginTop: 16 }}
      />
    </>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  content: { paddingHorizontal: t.spacing.lg, gap: t.spacing.md },
  name: { marginTop: -2, marginBottom: t.spacing.sm },
  heroWrap: { borderRadius: t.radius.lg, overflow: 'hidden', borderWidth: 1, borderColor: t.colors.border, ...t.shadow.md },
  heroBg: { ...({ position: 'absolute' } as any), width: '100%', height: '100%' },
  heroBlur: { padding: 2 },
  heroInner: { padding: t.spacing.xl, backgroundColor: 'rgba(253,253,251,0.55)', borderRadius: t.radius.lg },
  heroInnerFallback: { padding: t.spacing.xl, backgroundColor: 'rgba(253,253,251,0.82)', borderRadius: t.radius.lg },
  caughtUpCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  caughtUpIcon: {
    width: 44, height: 44, borderRadius: t.radius.md,
    backgroundColor: '#E8F2EC',
    alignItems: 'center', justifyContent: 'center',
  },
  missionTag: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: t.spacing.md },
  heroTitle: { marginBottom: t.spacing.md },
  missionRow: { flexDirection: 'row', gap: t.spacing.sm, flexWrap: 'wrap' },
  missionPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: t.colors.surfaceSecondary, paddingHorizontal: t.spacing.md, paddingVertical: 7, borderRadius: t.radius.pill, borderWidth: 1, borderColor: t.colors.border },
  statsRow: { flexDirection: 'row', gap: t.spacing.md },
  slipCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  statCard: { flex: 1, gap: 4 },
  statIcon: { width: 40, height: 40, borderRadius: t.radius.md, alignItems: 'center', justifyContent: 'center', marginBottom: t.spacing.sm },
  progressCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  miniStat: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: t.spacing.md },
  examCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  examBadge: { backgroundColor: t.colors.brandTertiary, paddingHorizontal: t.spacing.md, paddingVertical: 8, borderRadius: t.radius.sm },
  continueCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
}));
