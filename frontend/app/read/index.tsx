import React, { useState } from 'react';
import { View, ScrollView, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { CefrBadge } from '@/src/components/CefrBadge';
import { Skeleton } from '@/src/components/Skeleton';
import { api } from '@/src/api/client';

type Article = { id: string; title: string; level: string; topic: string; minutes: number; excerpt: string };
const LEVELS = ['All', 'A2', 'B1', 'B2', 'C1'];

export default function ReadList() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [level, setLevel] = useState('All');

  const q = useQuery({
    queryKey: ['articles', level],
    queryFn: () => api<{ articles: Article[] }>(`/articles${level !== 'All' ? `?level=${level}` : ''}`),
  });

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable testID="read-back" onPress={() => router.back()} hitSlop={10}>
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={20}>Read & Learn</AppText>
        <View style={{ width: 28 }} />
      </View>
      <AppText size={14} color={colors.muted} style={styles.sub}>Tap any word while reading to learn and save it.</AppText>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow} style={styles.chipScroll}>
        {LEVELS.map((l) => (
          <Pressable key={l} testID={`read-level-${l}`} onPress={() => setLevel(l)} style={[styles.chip, level === l ? styles.chipActive : styles.chipInactive]}>
            <AppText weight="medium" size={14} color={level === l ? colors.onSurfaceInverse : colors.onSurfaceTertiary}>{l}</AppText>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={[styles.list, { paddingBottom: insets.bottom + 24 }]} showsVerticalScrollIndicator={false}>
        {q.isLoading ? (
          <View style={{ gap: 12 }}>{[0, 1, 2].map((i) => <Skeleton key={i} height={110} rounded={20} />)}</View>
        ) : (
          q.data?.articles.map((a) => (
            <Card key={a.id} style={styles.card} onPress={() => router.push(`/read/${a.id}`)} testID={`article-${a.id}`}>
              <View style={styles.cardTop}>
                <CefrBadge level={a.level} small />
                <View style={styles.metaPill}><Icon name="clock-outline" size={13} color={colors.muted} /><AppText size={12} color={colors.muted}>{a.minutes} min</AppText></View>
              </View>
              <AppText weight="medium" size={18} style={{ marginTop: 10 }}>{a.title}</AppText>
              <AppText size={14} color={colors.muted} style={{ marginTop: 4, lineHeight: 20 }}>{a.excerpt}</AppText>
            </Card>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: t.spacing.lg },
  sub: { paddingHorizontal: t.spacing.lg, marginTop: t.spacing.sm },
  chipScroll: { flexGrow: 0, marginTop: t.spacing.md },
  chipRow: { gap: t.spacing.sm, paddingHorizontal: t.spacing.lg },
  chip: { height: 36, paddingHorizontal: t.spacing.lg, borderRadius: t.radius.pill, alignItems: 'center', justifyContent: 'center', borderWidth: 1, flexShrink: 0 },
  chipActive: { backgroundColor: t.colors.surfaceInverse, borderColor: t.colors.surfaceInverse },
  chipInactive: { backgroundColor: t.colors.surface, borderColor: t.colors.border },
  list: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.lg, gap: 12 },
  card: {},
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  metaPill: { flexDirection: 'row', alignItems: 'center', gap: 5 },
}));
