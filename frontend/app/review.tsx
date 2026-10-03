import React, { useMemo, useState } from 'react';
import { View, ScrollView, Pressable, RefreshControl, FlatList } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { WordRow, WordRowItem } from '@/src/components/WordRow';
import { EmptyState } from '@/src/components/EmptyState';
import { api } from '@/src/api/client';

type SlippingResponse = { count: number; words: WordRowItem[] };
type Progress = {
  words_learned: number;
  words_mastered: number;
  accuracy: number;
  streak: number;
  longest_streak: number;
};

type Filter = 'all' | 'recall' | 'reinforce' | 'near';

// Mastery threshold used *only* for visual grouping within a response the
// backend has already returned. We never invent a new mastery score or decide
// whether a word is slipping — only how to label words the server flagged.
const NEAR_MASTERED_THRESHOLD = 75;

/**
 * Review & Master hub.
 *
 * Honest buckets, derived deterministically from fields the backend already
 * returns on /review/slipping ({status, mastery_score, overdue_days}):
 *
 *   - "Needs recall"      → status ∈ {LEARNING, RECALLING} and mastery < threshold
 *   - "Near mastered"     → mastery_score ≥ NEAR_MASTERED_THRESHOLD and status ≠ MASTERED
 *   - "Keep fresh"        → status === MASTERED (mastery slipping on an already
 *                            mastered word; the backend put it in /review/slipping)
 *
 * Everything else (mastered count, learning count, accuracy) comes verbatim
 * from /progress. No frontend formulas compete with adaptive_learning.
 */
export default function Review() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const [filter, setFilter] = useState<Filter>('all');

  const slippingQ = useQuery({
    queryKey: ['slipping'],
    queryFn: () => api<SlippingResponse>('/review/slipping'),
  });
  const progressQ = useQuery({
    queryKey: ['progress'],
    queryFn: () => api<Progress>('/progress'),
  });

  const items = useMemo(() => slippingQ.data?.words ?? [], [slippingQ.data]);
  const totalDue = slippingQ.data?.count ?? 0;

  // Deterministic grouping — no synthetic numbers, no re-scoring.
  const groups = useMemo(() => {
    const recall: WordRowItem[] = [];
    const reinforce: WordRowItem[] = [];
    const near: WordRowItem[] = [];
    for (const w of items) {
      const m = typeof w.mastery_score === 'number' ? w.mastery_score : 0;
      const s = (w.status ?? '').toUpperCase();
      if (s === 'MASTERED') {
        reinforce.push(w);
      } else if (m >= NEAR_MASTERED_THRESHOLD) {
        near.push(w);
      } else {
        recall.push(w);
      }
    }
    return { recall, reinforce, near };
  }, [items]);

  const filteredItems: WordRowItem[] =
    filter === 'recall' ? groups.recall :
    filter === 'reinforce' ? groups.reinforce :
    filter === 'near' ? groups.near :
    items;

  const overdueCount = useMemo(
    () => items.filter((w) => typeof w.overdue_days === 'number' && w.overdue_days > 0).length,
    [items],
  );

  const chips: { key: Filter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: totalDue },
    { key: 'recall', label: 'Needs recall', count: groups.recall.length },
    { key: 'reinforce', label: 'Keep fresh', count: groups.reinforce.length },
    { key: 'near', label: 'Near mastered', count: groups.near.length },
  ].filter((c) => c.key === 'all' || c.count > 0);

  const refreshing = slippingQ.isRefetching || progressQ.isRefetching;
  const onRefresh = () => {
    slippingQ.refetch();
    progressQ.refetch();
  };

  const loading = slippingQ.isLoading || progressQ.isLoading;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      {/* top bar */}
      <View style={styles.topBar}>
        <Pressable
          testID="review-back"
          onPress={() => router.back()}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Back"
          style={styles.backBtn}
        >
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={20}>Review &amp; Master</AppText>
        <View style={styles.backBtn} />
      </View>

      <FlatList
        data={filteredItems}
        keyExtractor={(w) => w.id}
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + (totalDue > 0 ? 110 : 24) },
        ]}
        ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />
        }
        ListHeaderComponent={
          <View style={{ gap: 16 }}>
            {/* Headline */}
            <Animated.View entering={FadeInDown.duration(240)}>
              <Card style={styles.hero} testID="review-hero">
                <View style={styles.heroHead}>
                  <View style={styles.heroIcon}>
                    <Icon
                      name={totalDue > 0 ? 'clock-outline' : 'check-all'}
                      size={22}
                      color={colors.onBrand}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <AppText size={13} weight="medium" color={colors.brand}>
                      {totalDue > 0 ? 'Keep the words you know' : 'All caught up'}
                    </AppText>
                    <AppText weight="semibold" size={24} style={{ marginTop: 2 }}>
                      {loading
                        ? '…'
                        : totalDue > 0
                        ? `${totalDue} word${totalDue === 1 ? '' : 's'} to review`
                        : "You're on top of review"}
                    </AppText>
                  </View>
                </View>
                {totalDue > 0 ? (
                  <AppText size={14} color={colors.muted} style={{ marginTop: 10, lineHeight: 20 }}>
                    {overdueCount > 0
                      ? `${overdueCount} overdue · a short review now protects your long-term memory.`
                      : 'A short review now will keep these words active.'}
                  </AppText>
                ) : null}
              </Card>
            </Animated.View>

            {/* Mastery context — real /progress values only */}
            {progressQ.data ? (
              <Card style={styles.statCard} testID="review-mastery-summary">
                <View style={styles.statGrid}>
                  <View style={styles.statCell}>
                    <Icon name="check-decagram" size={18} color={colors.success} />
                    <AppText weight="semibold" size={22} style={{ marginTop: 4 }}>
                      {progressQ.data.words_mastered}
                    </AppText>
                    <AppText size={12} color={colors.muted}>Mastered</AppText>
                  </View>
                  <View style={styles.statDivider} />
                  <View style={styles.statCell}>
                    <Icon name="book-open-variant" size={18} color={colors.brand} />
                    <AppText weight="semibold" size={22} style={{ marginTop: 4 }}>
                      {progressQ.data.words_learned}
                    </AppText>
                    <AppText size={12} color={colors.muted}>Learning+</AppText>
                  </View>
                  <View style={styles.statDivider} />
                  <View style={styles.statCell}>
                    <Icon name="target" size={18} color={colors.info} />
                    <AppText weight="semibold" size={22} style={{ marginTop: 4 }}>
                      {progressQ.data.accuracy}%
                    </AppText>
                    <AppText size={12} color={colors.muted}>Accuracy</AppText>
                  </View>
                </View>
                <AppText size={12} color={colors.onSurfaceTertiary} style={{ marginTop: 10 }}>
                  Mastered means you&apos;re recalling it well right now — review keeps it that way.
                </AppText>
              </Card>
            ) : loading ? (
              <Skeleton height={120} rounded={16} />
            ) : null}

            {/* Filter chips — only buckets with real items */}
            {totalDue > 0 ? (
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.chipRow}
              >
                {chips.map((c) => {
                  const active = filter === c.key;
                  return (
                    <Pressable
                      key={c.key}
                      testID={`review-chip-${c.key}`}
                      onPress={() => setFilter(c.key)}
                      style={[styles.chip, active ? styles.chipActive : styles.chipInactive]}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      accessibilityLabel={`${c.label} filter · ${c.count} words`}
                    >
                      <AppText
                        weight="medium"
                        size={13}
                        color={active ? colors.onSurfaceInverse : colors.onSurfaceTertiary}
                      >
                        {c.label} · {c.count}
                      </AppText>
                    </Pressable>
                  );
                })}
              </ScrollView>
            ) : null}

            {/* Section header for the list */}
            {totalDue > 0 ? (
              <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionLabel}>
                {filter === 'all'
                  ? 'DUE NOW'
                  : filter === 'recall'
                  ? 'NEEDS RECALL'
                  : filter === 'reinforce'
                  ? 'KEEP FRESH'
                  : 'NEAR MASTERED'}
              </AppText>
            ) : null}
          </View>
        }
        renderItem={({ item }) => (
          <WordRow
            item={item}
            onPress={() => router.push(`/word/${item.id}`)}
            trailing="chevron"
            testID={`review-word-${item.id}`}
          />
        )}
        ListEmptyComponent={
          loading ? (
            <View style={{ gap: 12, paddingTop: 8 }}>
              {[0, 1, 2].map((i) => <Skeleton key={i} height={76} rounded={16} />)}
            </View>
          ) : slippingQ.isError ? (
            <EmptyState
              icon="alert-circle-outline"
              title="Couldn't load your review"
              description="Please check your connection and try again."
              action={{ label: 'Retry', onPress: () => slippingQ.refetch(), testID: 'review-retry' }}
            />
          ) : totalDue === 0 ? (
            <EmptyState
              icon="check-all"
              title="Nothing slipping"
              description="Your recent recall is holding up. Discover new words or practise what you're learning."
              action={{
                label: 'Discover words',
                onPress: () => router.push('/(tabs)/discover'),
                testID: 'review-empty-discover',
              }}
              secondaryAction={{
                label: 'Open Learn',
                onPress: () => router.push('/(tabs)/learn'),
                testID: 'review-empty-learn',
              }}
            />
          ) : (
            // totalDue > 0 but current filter has 0 — honest, non-dead-end state
            <EmptyState
              compact
              icon="filter-variant"
              title="Nothing in this group"
              description="Switch to another group or tap All to see every word."
              action={{
                label: 'Show all',
                onPress: () => setFilter('all'),
                testID: 'review-filter-reset',
              }}
            />
          )
        }
      />

      {/* Sticky Start Review CTA */}
      {!loading && totalDue > 0 ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          <Button
            testID="review-start-button"
            label={`Start review · ${totalDue}`}
            icon="play"
            onPress={() => router.push('/session?source=slipping')}
          />
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: t.spacing.sm, paddingBottom: t.spacing.sm,
  },
  backBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  content: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.sm },

  hero: {},
  heroHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  heroIcon: {
    width: 48, height: 48, borderRadius: t.radius.md,
    backgroundColor: t.colors.brand,
    alignItems: 'center', justifyContent: 'center',
  },

  statCard: {},
  statGrid: { flexDirection: 'row', alignItems: 'center' },
  statCell: { flex: 1, alignItems: 'center' },
  statDivider: { width: 1, height: 40, backgroundColor: t.colors.border },

  chipRow: { gap: t.spacing.sm, paddingRight: t.spacing.lg },
  chip: {
    height: 36,
    paddingHorizontal: t.spacing.lg,
    borderRadius: t.radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    flexShrink: 0,
  },
  chipActive: { backgroundColor: t.colors.surfaceInverse, borderColor: t.colors.surfaceInverse },
  chipInactive: { backgroundColor: t.colors.surface, borderColor: t.colors.border },

  sectionLabel: { letterSpacing: 0.5, marginTop: t.spacing.xs },

  cta: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md,
    backgroundColor: t.colors.surface,
    borderTopWidth: 1, borderTopColor: t.colors.divider,
  },
}));
