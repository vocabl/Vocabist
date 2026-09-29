import React from 'react';
import { View, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Button } from '@/src/components/Button';
import { Skeleton } from '@/src/components/Skeleton';
import { useAuth } from '@/src/auth/AuthContext';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

type Achievement = { key: string; title: string; desc: string; goal: number; value: number; unlocked: boolean; progress: number };
type Progress = {
  words_learned: number; words_mastered: number; accuracy: number; streak: number; longest_streak: number;
  xp: number; level: number; xp_into_level: number; xp_per_level: number; study_minutes: number;
  weak_areas: { topic: string; avg_mastery: number }[]; achievements: Achievement[];
};

export default function Profile() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { user, signOut } = useAuth();
  const toast = useToast();

  const pQ = useQuery({ queryKey: ['progress'], queryFn: () => api<Progress>('/progress') });
  const p = pQ.data;

  const stats = [
    { label: 'Mastered', value: p?.words_mastered ?? 0, icon: 'check-decagram', color: colors.success },
    { label: 'Learned', value: p?.words_learned ?? 0, icon: 'book-open-variant', color: colors.brand },
    { label: 'Day streak', value: p?.streak ?? 0, icon: 'fire', color: colors.warning },
    { label: 'Accuracy', value: `${p?.accuracy ?? 0}%`, icon: 'target', color: colors.info },
  ];

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 12, paddingBottom: 40 }]}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.headerRow}>
        <View style={styles.avatar}>
          <AppText weight="semibold" size={24} color={colors.onBrand}>{(user?.name || 'U').slice(0, 1).toUpperCase()}</AppText>
        </View>
        <View style={{ flex: 1 }}>
          <AppText weight="semibold" size={22}>{user?.name}</AppText>
          <AppText size={14} color={colors.muted} style={{ marginTop: 2 }}>{user?.email}</AppText>
        </View>
      </View>

      {/* Level */}
      <Card style={styles.levelCard} testID="level-progress-card">
        <View style={styles.levelTop}>
          <View style={styles.levelBadge}><Icon name="lightning-bolt" size={18} color={colors.onBrand} /></View>
          <View style={{ flex: 1 }}>
            <AppText weight="medium" size={16}>Level {p?.level ?? 1}</AppText>
            <AppText size={13} color={colors.muted}>{p?.xp ?? 0} total XP</AppText>
          </View>
          <AppText size={13} color={colors.muted}>{p?.xp_into_level ?? 0}/{p?.xp_per_level ?? 500}</AppText>
        </View>
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${p ? Math.round((p.xp_into_level / p.xp_per_level) * 100) : 0}%` }]} />
        </View>
      </Card>

      {/* Stats grid */}
      {pQ.isLoading ? (
        <View style={styles.grid}>{[0, 1, 2, 3].map((i) => <Skeleton key={i} width="47%" height={90} rounded={16} />)}</View>
      ) : (
        <View style={styles.grid}>
          {stats.map((s) => (
            <Card key={s.label} style={styles.statCard} testID={`stat-${s.label}`}>
              <Icon name={s.icon as any} size={22} color={s.color} />
              <AppText weight="semibold" size={22} style={{ marginTop: 8 }}>{s.value}</AppText>
              <AppText size={12} color={colors.muted}>{s.label}</AppText>
            </Card>
          ))}
        </View>
      )}

      {/* Achievements */}
      <AppText weight="medium" size={16} style={styles.section}>Achievements</AppText>
      <View style={{ gap: 10 }}>
        {(p?.achievements ?? []).map((a) => (
          <Card key={a.key} style={styles.achRow} testID={`achievement-${a.key}`}>
            <View style={[styles.achIcon, { backgroundColor: a.unlocked ? colors.brandTertiary : colors.surfaceTertiary }]}>
              <Icon name={a.unlocked ? 'trophy' : 'trophy-outline'} size={20} color={a.unlocked ? colors.brand : colors.muted} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={15} color={a.unlocked ? colors.onSurface : colors.onSurfaceTertiary}>{a.title}</AppText>
              <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>{a.desc}</AppText>
              {!a.unlocked ? (
                <View style={styles.achTrack}><View style={[styles.achFill, { width: `${a.progress}%` }]} /></View>
              ) : null}
            </View>
            {a.unlocked ? <Icon name="check-circle" size={20} color={colors.success} /> : null}
          </Card>
        ))}
      </View>

      {/* Upgrade */}
      <Card style={styles.proCard} testID="upgrade-pro-card">
        <View style={styles.proHead}>
          <Icon name="crown" size={22} color={colors.warning} />
          <AppText weight="semibold" size={17}>Vocably Pro</AppText>
        </View>
        <AppText size={14} color={colors.onSurfaceTertiary} style={{ marginTop: 6, lineHeight: 20 }}>
          Unlimited adaptive learning, full exam libraries, advanced analytics and AI features.
        </AppText>
        <Button label="Upgrade to Pro" icon="crown-outline" onPress={() => toast.show('Pro plans are coming soon!', 'info')} style={{ marginTop: 14 }} testID="upgrade-button" />
      </Card>

      <Button label="Log out" variant="ghost" icon="logout" onPress={signOut} style={{ marginTop: 20 }} testID="logout-button" />
    </ScrollView>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  content: { paddingHorizontal: t.spacing.lg, gap: t.spacing.lg },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, marginTop: t.spacing.sm },
  avatar: { width: 60, height: 60, borderRadius: 30, backgroundColor: t.colors.brand, alignItems: 'center', justifyContent: 'center' },
  levelCard: { gap: t.spacing.md },
  levelTop: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  levelBadge: { width: 40, height: 40, borderRadius: t.radius.md, backgroundColor: t.colors.brand, alignItems: 'center', justifyContent: 'center' },
  track: { height: 8, borderRadius: 4, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 4 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md },
  statCard: { width: '47%', flexGrow: 1 },
  section: { marginBottom: -4 },
  achRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  achIcon: { width: 44, height: 44, borderRadius: t.radius.md, alignItems: 'center', justifyContent: 'center' },
  achTrack: { height: 5, borderRadius: 3, backgroundColor: t.colors.surfaceTertiary, marginTop: 8, overflow: 'hidden' },
  achFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 3 },
  proCard: { borderColor: t.colors.brandSecondary },
  proHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
}));
