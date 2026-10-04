import React from 'react';
import { View, ScrollView, Pressable, RefreshControl, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { makeStyles, useTheme, colors, spacing, radius } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Button } from '@/src/components/Button';
import { Skeleton } from '@/src/components/Skeleton';
import { useAuth } from '@/src/auth/AuthContext';
import { useEntitlement } from '@/src/hooks/useEntitlement';
import { useIsAdmin } from '@/src/api/admin';
import { api } from '@/src/api/client';

type Achievement = {
  key: string; title: string; desc: string; goal: number;
  value: number; unlocked: boolean; progress: number;
};
type WeakArea = {
  topic: string; name: string; avg_mastery: number;
  mastered_count: number; total_count: number; mastery_percent: number;
};
type RecentlyMastered = {
  word_id: string; headword: string; cefr?: string;
  mastery_score: number; mastered_at: string;
};
type MasteryDist = { SEEN: number; LEARNING: number; RECALLING: number; MASTERED: number };
type Progress = {
  words_learned: number; words_mastered: number; in_progress: number;
  accuracy: number; streak: number; longest_streak: number;
  xp: number; level: number; xp_into_level: number; xp_per_level: number;
  study_minutes: number; total_sessions: number;
  mastery_distribution: MasteryDist;
  recently_mastered: RecentlyMastered[];
  weak_areas: WeakArea[];
  cefr_level?: string;
  achievements: Achievement[];
};
type SlippingData = { count: number; words: any[] };

// ─── Mastery bar colors ──────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  MASTERED: '#3E7B51',
  RECALLING: '#4A7C59',
  LEARNING: '#D19036',
  SEEN: '#B8B8B3',
};
const STATUS_LABELS: Record<string, string> = {
  MASTERED: 'Mastered',
  RECALLING: 'Recalling',
  LEARNING: 'Learning',
  SEEN: 'Seen',
};

export default function ProfileProgress() {
  const styles = useStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();
  const { user, signOut } = useAuth();
  const router = useRouter();

  const pQ = useQuery({ queryKey: ['progress'], queryFn: () => api<Progress>('/progress') });
  const slipQ = useQuery({ queryKey: ['slipping'], queryFn: () => api<SlippingData>('/review/slipping') });
  const ent = useEntitlement();
  const { isAdmin } = useIsAdmin();
  const p = pQ.data;
  const slip = slipQ.data;

  const onRefresh = () => { pQ.refetch(); slipQ.refetch(); };

  const xpPercent = p ? Math.min(100, Math.round((p.xp_into_level / p.xp_per_level) * 100)) : 0;

  // Mastery distribution bar
  const dist = p?.mastery_distribution;
  const totalDist = dist ? dist.SEEN + dist.LEARNING + dist.RECALLING + dist.MASTERED : 0;

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={pQ.isFetching && !pQ.isLoading} onRefresh={onRefresh} tintColor={c.brand} />}
    >
      {/* ─── HEADER ─── */}
      <View style={styles.header} testID="progress-header">
        <View style={styles.avatar}>
          <AppText weight="semibold" size={24} color={c.onBrand}>
            {(user?.name || 'U').slice(0, 1).toUpperCase()}
          </AppText>
        </View>
        <View style={{ flex: 1 }}>
          <AppText weight="semibold" size={22} testID="progress-user-name">{user?.name}</AppText>
          <AppText size={13} color={c.muted} style={{ marginTop: 2 }}>
            {p ? (p.words_mastered > 0
              ? `${p.words_mastered} word${p.words_mastered === 1 ? '' : 's'} mastered`
              : 'Start learning to track your progress') : ''}
          </AppText>
        </View>
      </View>

      {/* ─── LEVEL + XP ─── */}
      {pQ.isLoading ? (
        <Skeleton width="100%" height={72} rounded={16} />
      ) : (
        <View style={styles.levelCard} testID="level-progress-card">
          <View style={styles.levelRow}>
            <View style={styles.levelBadge}>
              <AppText weight="semibold" size={16} color={c.onBrand}>{p?.level ?? 1}</AppText>
            </View>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={15}>Level {p?.level ?? 1}</AppText>
              <AppText size={12} color={c.muted}>{p?.xp ?? 0} XP total</AppText>
            </View>
            <AppText size={12} color={c.muted}>{p?.xp_into_level ?? 0} / {p?.xp_per_level ?? 500}</AppText>
          </View>
          <View style={styles.xpTrack}>
            <View style={[styles.xpFill, { width: `${xpPercent}%` }]} />
          </View>
        </View>
      )}

      {/* ─── CORE STATS 2×2 ─── */}
      {pQ.isLoading ? (
        <View style={styles.statsGrid}>
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} width="47%" height={86} rounded={14} />)}
        </View>
      ) : (
        <View style={styles.statsGrid}>
          <StatTile testID="stat-mastered" icon="check-decagram" iconColor={c.success}
            value={p?.words_mastered ?? 0} label="Mastered" />
          <StatTile testID="stat-in-progress" icon="book-open-variant" iconColor={c.brand}
            value={p?.in_progress ?? 0} label="In progress" />
          <StatTile testID="stat-streak" icon="fire" iconColor={c.warning}
            value={p?.streak ?? 0} label="Day streak"
            sub={p && p.longest_streak > (p.streak ?? 0) ? `Best: ${p.longest_streak}` : undefined} />
          <StatTile testID="stat-accuracy" icon="target" iconColor={c.info}
            value={`${p?.accuracy ?? 0}%`} label="Practice accuracy" />
        </View>
      )}

      {/* ─── MASTERY DISTRIBUTION ─── */}
      {!pQ.isLoading && totalDist > 0 && (
        <View style={styles.section} testID="mastery-distribution">
          <AppText weight="medium" size={16} style={styles.sectionTitle}>Mastery breakdown</AppText>
          <View style={styles.distBar}>
            {(['MASTERED', 'RECALLING', 'LEARNING', 'SEEN'] as const).map((s) => {
              const count = dist![s];
              if (!count) return null;
              const pct = Math.max(2, (count / totalDist) * 100);
              return (
                <View key={s} style={[styles.distSegment, { width: `${pct}%`, backgroundColor: STATUS_COLORS[s] }]} />
              );
            })}
          </View>
          <View style={styles.distLegend}>
            {(['MASTERED', 'RECALLING', 'LEARNING', 'SEEN'] as const).map((s) => (
              <View key={s} style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: STATUS_COLORS[s] }]} />
                <AppText size={12} color={c.muted}>{STATUS_LABELS[s]}</AppText>
                <AppText size={12} weight="medium" style={{ marginLeft: 2 }}>{dist![s]}</AppText>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* ─── REVIEW HEALTH ─── */}
      <View style={styles.section} testID="review-health">
        <AppText weight="medium" size={16} style={styles.sectionTitle}>Review health</AppText>
        {slipQ.isLoading ? (
          <Skeleton width="100%" height={64} rounded={14} />
        ) : slip && slip.count > 0 ? (
          <Pressable
            testID="review-health-cta"
            style={styles.reviewCard}
            onPress={() => router.push('/review')}
            accessibilityRole="button"
            accessibilityLabel={`${slip.count} words need review`}
          >
            <View style={styles.reviewIcon}>
              <Icon name="clock-alert-outline" size={20} color={c.warning} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={14}>{slip.count} word{slip.count === 1 ? '' : 's'} slipping</AppText>
              <AppText size={12} color={c.muted}>Review now to strengthen retention</AppText>
            </View>
            <Icon name="chevron-right" size={20} color={c.muted} />
          </Pressable>
        ) : (
          <View style={styles.reviewOk}>
            <Icon name="check-circle-outline" size={20} color={c.success} />
            <AppText size={14} color={c.onSurfaceTertiary} style={{ flex: 1 }}>
              You&apos;re all caught up — no words need review right now.
            </AppText>
          </View>
        )}
      </View>

      {/* ─── WHAT TO DO NEXT ─── */}
      <View style={styles.section} testID="next-actions">
        <AppText weight="medium" size={16} style={styles.sectionTitle}>What to do next</AppText>
        <View style={styles.actionsRow}>
          {slip && slip.count > 0 && (
            <ActionChip testID="action-review" icon="refresh" label="Review"
              sub={`${slip.count} slipping`} onPress={() => router.push('/review')} />
          )}
          <ActionChip testID="action-mission" icon="lightning-bolt" label="Daily mission"
            sub="Continue learning" onPress={() => router.push('/mission')} />
          <ActionChip testID="action-discover" icon="compass-outline" label="Discover"
            sub="Explore words" onPress={() => router.push('/(tabs)/discover')} />
        </View>
      </View>

      {/* ─── RECENTLY MASTERED ─── */}
      <View style={styles.section} testID="recently-mastered">
        <AppText weight="medium" size={16} style={styles.sectionTitle}>Recently mastered</AppText>
        {pQ.isLoading ? (
          <Skeleton width="100%" height={56} rounded={14} />
        ) : p?.recently_mastered && p.recently_mastered.length > 0 ? (
          <View style={{ gap: 8 }}>
            {p.recently_mastered.map((w) => (
              <Pressable
                key={w.word_id}
                testID={`mastered-word-${w.word_id}`}
                style={styles.masteredRow}
                onPress={() => router.push(`/word/${w.word_id}` as any)}
                accessibilityRole="button"
                accessibilityLabel={`View ${w.headword}`}
              >
                <View style={styles.masteredBadge}>
                  <Icon name="check-decagram" size={16} color={c.success} />
                </View>
                <View style={{ flex: 1 }}>
                  <AppText weight="medium" size={15}>{w.headword}</AppText>
                  {w.cefr ? <AppText size={11} color={c.muted}>{w.cefr}</AppText> : null}
                </View>
                <AppText size={12} color={c.success}>{w.mastery_score}%</AppText>
                <Icon name="chevron-right" size={16} color={c.border} />
              </Pressable>
            ))}
          </View>
        ) : (
          <View style={styles.emptyMastered}>
            <Icon name="trophy-outline" size={24} color={c.borderStrong} />
            <AppText size={13} color={c.muted} style={{ textAlign: 'center', marginTop: 8 }}>
              Your mastered words will appear here as you progress.
            </AppText>
          </View>
        )}
      </View>

      {/* ─── FOCUS AREAS ─── */}
      {p?.weak_areas && p.weak_areas.length > 0 && (
        <View style={styles.section} testID="focus-areas">
          <AppText weight="medium" size={16} style={styles.sectionTitle}>Focus areas</AppText>
          <AppText size={12} color={c.muted} style={{ marginBottom: 10 }}>Topics needing the most work</AppText>
          {p.weak_areas.map((wa) => (
            <View key={wa.topic} style={styles.focusRow} testID={`focus-${wa.topic}`}>
              <View style={{ flex: 1 }}>
                <AppText weight="medium" size={14}>{wa.name}</AppText>
                <AppText size={11} color={c.muted}>
                  {wa.mastered_count}/{wa.total_count} mastered · {wa.avg_mastery}% avg
                </AppText>
              </View>
              <View style={styles.focusTrack}>
                <View style={[styles.focusFill, { width: `${Math.min(100, wa.mastery_percent)}%` }]} />
              </View>
            </View>
          ))}
        </View>
      )}

      {/* ─── PRACTICE ACTIVITY ─── */}
      {!pQ.isLoading && (p?.total_sessions ?? 0) > 0 && (
        <View style={styles.section} testID="practice-activity">
          <AppText weight="medium" size={16} style={styles.sectionTitle}>Practice activity</AppText>
          <View style={styles.activityGrid}>
            <View style={styles.activityItem}>
              <AppText weight="semibold" size={20}>{p?.total_sessions ?? 0}</AppText>
              <AppText size={11} color={c.muted}>Sessions</AppText>
            </View>
            <View style={styles.activityDivider} />
            <View style={styles.activityItem}>
              <AppText weight="semibold" size={20}>{p?.study_minutes ?? 0}</AppText>
              <AppText size={11} color={c.muted}>Minutes</AppText>
            </View>
            <View style={styles.activityDivider} />
            <View style={styles.activityItem}>
              <AppText weight="semibold" size={20}>{p?.words_learned ?? 0}</AppText>
              <AppText size={11} color={c.muted}>Learned</AppText>
            </View>
          </View>
        </View>
      )}

      {/* ─── ACHIEVEMENTS ─── */}
      <View style={styles.section} testID="achievements">
        <AppText weight="medium" size={16} style={styles.sectionTitle}>Achievements</AppText>
        <View style={{ gap: 8 }}>
          {(p?.achievements ?? []).map((a) => (
            <View key={a.key} style={styles.achRow} testID={`achievement-${a.key}`}>
              <View style={[styles.achIcon, { backgroundColor: a.unlocked ? '#E7F0E9' : c.surfaceTertiary }]}>
                <Icon name={a.unlocked ? 'trophy' : 'trophy-outline'} size={18}
                  color={a.unlocked ? c.brand : c.muted} />
              </View>
              <View style={{ flex: 1 }}>
                <AppText weight="medium" size={14} color={a.unlocked ? c.onSurface : c.onSurfaceTertiary}>
                  {a.title}
                </AppText>
                <AppText size={11} color={c.muted}>{a.desc}</AppText>
                {!a.unlocked && (
                  <View style={styles.achTrack}>
                    <View style={[styles.achFill, { width: `${a.progress}%` }]} />
                  </View>
                )}
              </View>
              {a.unlocked && <Icon name="check-circle" size={18} color={c.success} />}
            </View>
          ))}
        </View>
      </View>

      {/* ─── ADMIN ─── */}
      {isAdmin && (
        <View style={styles.section} testID="admin-section">
          <AppText weight="medium" size={16} style={styles.sectionTitle}>Internal</AppText>
          <Card onPress={() => router.push('/admin' as any)} style={styles.adminCard} testID="admin-entry">
            <View style={styles.adminIcon}>
              <Icon name="shield-crown-outline" size={20} color={c.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={15}>Admin Control Center</AppText>
              <AppText size={12} color={c.muted}>AI platform, generation & review</AppText>
            </View>
            <Icon name="chevron-right" size={20} color={c.muted} />
          </Card>
        </View>
      )}

      {/* ─── ACCOUNT ─── */}
      <View style={styles.section} testID="account-section">
        <AppText weight="medium" size={16} style={styles.sectionTitle}>Account</AppText>

        {/* Plan status */}
        <View style={styles.planStatus} testID="plan-status">
          <View style={styles.planStatusIcon}>
            <Icon name={ent.isPro ? 'crown' : 'crown-outline'} size={18}
              color={ent.isPro ? c.warning : c.muted} />
          </View>
          <View style={{ flex: 1 }}>
            <AppText weight="medium" size={14}>
              {ent.isPro ? 'Vocabist Pro' : 'Vocabist Free'}
            </AppText>
            <AppText size={12} color={c.muted}>
              {ent.isPro
                ? `${ent.data?.subscription_plan ?? 'Pro'} plan${ent.data?.source === 'mock' ? ' · Preview' : ''}`
                : 'Core learning features included'}
            </AppText>
          </View>
        </View>

        {!ent.isPro && (
          <Card style={styles.proCard} testID="upgrade-pro-card">
            <View style={styles.proHead}>
              <Icon name="crown-outline" size={20} color={c.warning} />
              <AppText weight="semibold" size={16}>Upgrade to Pro</AppText>
            </View>
            <AppText size={13} color={c.onSurfaceTertiary} style={{ marginTop: 4, lineHeight: 18 }}>
              Unlimited learning, all exam libraries, and advanced AI features.
            </AppText>
            <Button
              label="See plans"
              icon="crown-outline"
              onPress={() => router.push('/paywall')}
              style={{ marginTop: 12 }}
              testID="upgrade-button"
            />
          </Card>
        )}

        {ent.isPro && (
          <Button
            label="Manage subscription"
            variant="ghost"
            icon="cog-outline"
            onPress={() => router.push('/paywall')}
            style={{ marginTop: 8 }}
            testID="manage-subscription-button"
          />
        )}
        <View style={styles.accountInfo}>
          <AppText size={13} color={c.muted}>{user?.email}</AppText>
        </View>
        <Button label="Log out" variant="ghost" icon="logout" onPress={signOut}
          style={{ marginTop: 8 }} testID="logout-button" />
      </View>
    </ScrollView>
  );
}

// ─── Sub-components ────────────────────────────────────

function StatTile({ icon, iconColor, value, label, sub, testID }: {
  icon: string; iconColor: string; value: number | string; label: string; sub?: string; testID: string;
}) {
  const { colors: c } = useTheme();
  return (
    <View style={statStyles.tile} testID={testID}>
      <Icon name={icon as any} size={20} color={iconColor} />
      <AppText weight="semibold" size={22} style={{ marginTop: 6 }}>{value}</AppText>
      <AppText size={11} color={c.muted}>{label}</AppText>
      {sub ? <AppText size={10} color={c.onSurfaceTertiary} style={{ marginTop: 1 }}>{sub}</AppText> : null}
    </View>
  );
}

function ActionChip({ icon, label, sub, onPress, testID }: {
  icon: string; label: string; sub: string; onPress: () => void; testID: string;
}) {
  const { colors: c } = useTheme();
  return (
    <Pressable testID={testID} style={actionStyles.chip} onPress={onPress}
      accessibilityRole="button" accessibilityLabel={label}>
      <View style={actionStyles.chipIcon}>
        <Icon name={icon as any} size={18} color={c.brand} />
      </View>
      <AppText weight="medium" size={13}>{label}</AppText>
      <AppText size={11} color={c.muted}>{sub}</AppText>
    </Pressable>
  );
}

// ─── Styles ────────────────────────────────────────────

const statStyles = StyleSheet.create({
  tile: {
    width: '47%',
    flexGrow: 1,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
});

const actionStyles = StyleSheet.create({
  chip: {
    flex: 1,
    minWidth: 100,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: 4,
  },
  chipIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
});

const useStyles = makeStyles((t) => ({
  scroll: { flex: 1, backgroundColor: t.colors.surface },
  content: { paddingHorizontal: t.spacing.lg, gap: t.spacing.lg },

  // Header
  header: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, marginTop: 4 },
  avatar: {
    width: 56, height: 56, borderRadius: 28, backgroundColor: t.colors.brand,
    alignItems: 'center', justifyContent: 'center',
  },

  // Level
  levelCard: {
    backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md,
    borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg, gap: 10,
  },
  levelRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  levelBadge: {
    width: 38, height: 38, borderRadius: t.radius.sm, backgroundColor: t.colors.brand,
    alignItems: 'center', justifyContent: 'center',
  },
  xpTrack: { height: 6, borderRadius: 3, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden' },
  xpFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 3 },

  // Stats grid
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md },

  // Sections
  section: {},
  sectionTitle: { marginBottom: t.spacing.sm },

  // Distribution bar
  distBar: { flexDirection: 'row', height: 10, borderRadius: 5, overflow: 'hidden', gap: 2 },
  distSegment: { borderRadius: 5 },
  distLegend: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md, marginTop: t.spacing.sm },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },

  // Review health
  reviewCard: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    backgroundColor: '#FFF8EE', borderRadius: t.radius.md,
    borderWidth: 1, borderColor: '#F0D8A8', padding: t.spacing.lg,
  },
  reviewIcon: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: '#FFF0D4',
    alignItems: 'center', justifyContent: 'center',
  },
  reviewOk: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    backgroundColor: '#F0F8F2', borderRadius: t.radius.md,
    borderWidth: 1, borderColor: '#D4E8D9', padding: t.spacing.lg,
  },

  // Actions
  actionsRow: { flexDirection: 'row', gap: t.spacing.sm },

  // Recently mastered
  masteredRow: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md,
    borderWidth: 1, borderColor: t.colors.border, paddingVertical: 10, paddingHorizontal: t.spacing.md,
  },
  masteredBadge: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: '#E7F0E9',
    alignItems: 'center', justifyContent: 'center',
  },
  emptyMastered: {
    alignItems: 'center', paddingVertical: t.spacing.xxl,
    backgroundColor: t.colors.surfaceTertiary, borderRadius: t.radius.md,
  },

  // Focus areas
  focusRow: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: t.colors.divider,
  },
  focusTrack: {
    width: 60, height: 6, borderRadius: 3, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden',
  },
  focusFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 3 },

  // Activity
  activityGrid: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md,
    borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg,
  },
  activityItem: { flex: 1, alignItems: 'center' },
  activityDivider: { width: 1, height: 32, backgroundColor: t.colors.divider },

  // Achievements
  achRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  achIcon: {
    width: 40, height: 40, borderRadius: t.radius.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  achTrack: { height: 4, borderRadius: 2, backgroundColor: t.colors.surfaceTertiary, marginTop: 6, overflow: 'hidden' },
  achFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 2 },

  // Account
  planStatus: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md,
    borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg, marginBottom: t.spacing.sm,
  },
  planStatusIcon: {
    width: 36, height: 36, borderRadius: 18, backgroundColor: '#FBF3E2',
    alignItems: 'center', justifyContent: 'center',
  },
  proCard: { borderColor: t.colors.brandSecondary },
  proHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  accountInfo: { marginTop: t.spacing.md },
  adminCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, padding: t.spacing.lg },
  adminIcon: {
    width: 40, height: 40, borderRadius: t.radius.sm, backgroundColor: '#E7F0E9',
    alignItems: 'center', justifyContent: 'center',
  },
}));
