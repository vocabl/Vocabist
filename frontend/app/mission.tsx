import React from 'react';
import { View, ScrollView, Pressable } from 'react-native';
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
import { EmptyState } from '@/src/components/EmptyState';
import { api } from '@/src/api/client';

type Mission = {
  total_words: number;
  review_count: number;
  new_count: number;
  estimated_minutes: number;
  streak: number;
  xp: number;
  daily_minutes: number;
  continue_word: { id: string; headword: string; simple_definition: string; cefr?: string } | null;
};

type Slipping = { count: number; words: { id: string; headword: string }[] };

/**
 * Daily Mission overview — the deliberate step between "I want to practise"
 * and the practice engine. Shows the real composition returned by the
 * backend's adaptive selector (/mission) so the learner understands *why*
 * today's session looks the way it does before they start.
 */
export default function MissionOverview() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const mQ = useQuery({ queryKey: ['mission'], queryFn: () => api<Mission>('/mission') });
  const sQ = useQuery({ queryKey: ['slipping'], queryFn: () => api<Slipping>('/review/slipping') });

  const m = mQ.data;
  const empty = !!m && m.total_words === 0;

  // Composition rows — only shown when the backend actually counted that bucket.
  const parts: { key: string; icon: React.ComponentProps<typeof Icon>['name']; label: string; sublabel: string; count: number; tint: string }[] = [];
  if (m) {
    const slippingCount = sQ.data?.count ?? 0;
    // Review bucket is reported as a single number; if slipping is a strict
    // subset we surface it as "including N slipping" without inventing new maths.
    if (m.review_count > 0) {
      parts.push({
        key: 'review',
        icon: 'refresh',
        label: 'Review',
        sublabel:
          slippingCount > 0
            ? `${slippingCount} slipping${slippingCount < m.review_count ? ` · ${m.review_count - slippingCount} other` : ''}`
            : 'Words due for recall',
        count: m.review_count,
        tint: colors.warning,
      });
    }
    if (m.new_count > 0) {
      parts.push({
        key: 'new',
        icon: 'star-four-points-outline',
        label: 'Learn',
        sublabel: 'New vocabulary for today',
        count: m.new_count,
        tint: colors.brand,
      });
    }
  }

  const totalExists = !!m && m.total_words > 0;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.topBar}>
        <Pressable
          testID="mission-back"
          onPress={() => router.back()}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Back"
          style={styles.backBtn}
        >
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={20}>Today&apos;s Mission</AppText>
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + (totalExists ? 110 : 24) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {mQ.isLoading ? (
          <View style={{ gap: 12 }}>
            <Skeleton height={80} rounded={16} />
            <Skeleton height={72} rounded={16} />
            <Skeleton height={72} rounded={16} />
          </View>
        ) : mQ.isError ? (
          <EmptyState
            icon="alert-circle-outline"
            title="Couldn't load your mission"
            description="Please check your connection and try again."
            action={{ label: 'Retry', onPress: () => mQ.refetch(), testID: 'mission-retry' }}
          />
        ) : empty ? (
          <EmptyState
            icon="check-all"
            title="You&apos;re all caught up"
            description="Nothing is due right now. Keep the momentum by discovering new vocabulary or practising saved words."
            action={{
              label: 'Discover words',
              onPress: () => router.push('/(tabs)/discover'),
              testID: 'mission-empty-discover',
            }}
            secondaryAction={{
              label: 'Open saved',
              onPress: () => router.push('/saved'),
              testID: 'mission-empty-saved',
            }}
          />
        ) : (
          <Animated.View entering={FadeInDown.duration(240)} style={{ gap: 16 }}>
            {/* Headline */}
            <Card style={styles.summary} testID="mission-summary">
              <View style={styles.summaryTopRow}>
                <View style={styles.summaryIcon}>
                  <Icon name="target" size={22} color={colors.onBrand} />
                </View>
                <View style={{ flex: 1 }}>
                  <AppText size={13} weight="medium" color={colors.brand}>Adaptive · for you</AppText>
                  <AppText weight="semibold" size={24} style={{ marginTop: 2 }}>
                    {m!.total_words} word{m!.total_words === 1 ? '' : 's'} · {m!.estimated_minutes} min
                  </AppText>
                </View>
              </View>
              <AppText size={14} color={colors.muted} style={{ marginTop: 10, lineHeight: 20 }}>
                Your mission is built from your current vocabulary state — review timing, recall strength and new words at your level.
              </AppText>
            </Card>

            {/* Composition rows — only real buckets */}
            <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionLabel}>
              WHAT YOU&apos;LL DO
            </AppText>
            <View style={{ gap: 10 }}>
              {parts.map((p) => (
                <View key={p.key} style={styles.partRow}>
                  <View style={[styles.partIcon, { backgroundColor: p.tint + '22' }]}>
                    <Icon name={p.icon} size={20} color={p.tint} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={styles.partHead}>
                      <AppText weight="medium" size={15}>{p.label}</AppText>
                      <View style={styles.countPill}>
                        <AppText size={12} weight="semibold" color={colors.onSurfaceTertiary}>
                          ×{p.count}
                        </AppText>
                      </View>
                    </View>
                    <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>
                      {p.sublabel}
                    </AppText>
                  </View>
                </View>
              ))}
            </View>

            {/* Continue card — only when a canonical continue word exists */}
            {m!.continue_word ? (
              <>
                <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionLabel}>
                  PICK UP WHERE YOU LEFT OFF
                </AppText>
                <Pressable
                  testID="mission-continue"
                  onPress={() => router.push(`/word/${m!.continue_word!.id}`)}
                  accessibilityRole="button"
                  accessibilityLabel={`Open ${m!.continue_word.headword}`}
                >
                  <Card style={styles.continueCard}>
                    <View style={styles.continueIcon}>
                      <Icon name="book-open-variant" size={20} color={colors.brand} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <AppText weight="medium" size={16}>{m!.continue_word.headword}</AppText>
                      <AppText size={13} color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>
                        {m!.continue_word.simple_definition}
                      </AppText>
                    </View>
                    <Icon name="chevron-right" size={22} color={colors.muted} />
                  </Card>
                </Pressable>
              </>
            ) : null}
          </Animated.View>
        )}
      </ScrollView>

      {/* Sticky Begin CTA when there is actual work */}
      {totalExists ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          <Button
            testID="mission-begin-button"
            label="Begin mission"
            icon="play"
            onPress={() => router.replace('/session?source=mission')}
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

  summary: {},
  summaryTopRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  summaryIcon: {
    width: 48, height: 48, borderRadius: t.radius.md,
    backgroundColor: t.colors.brand,
    alignItems: 'center', justifyContent: 'center',
  },

  sectionLabel: { letterSpacing: 0.5, marginTop: t.spacing.sm },

  partRow: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    backgroundColor: t.colors.surfaceSecondary,
    borderWidth: 1, borderColor: t.colors.border,
    borderRadius: t.radius.lg,
    padding: t.spacing.lg,
    minHeight: 64,
  },
  partIcon: {
    width: 40, height: 40, borderRadius: t.radius.md,
    alignItems: 'center', justifyContent: 'center',
  },
  partHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  countPill: {
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: t.radius.sm,
    backgroundColor: t.colors.surfaceTertiary,
  },

  continueCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  continueIcon: {
    width: 44, height: 44, borderRadius: t.radius.md,
    backgroundColor: t.colors.brandTertiary,
    alignItems: 'center', justifyContent: 'center',
  },

  cta: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md,
    backgroundColor: t.colors.surface,
    borderTopWidth: 1, borderTopColor: t.colors.divider,
  },
}));
