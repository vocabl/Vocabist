import React, { useEffect, useState } from 'react';
import { View, ScrollView, FlatList, Pressable, TextInput } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { CefrBadge } from '@/src/components/CefrBadge';
import { Skeleton } from '@/src/components/Skeleton';
import { api } from '@/src/api/client';

const CEFR = ['All', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
const EMPTY_IMG = 'https://images.unsplash.com/photo-1765854540946-838b653c3a76?crop=entropy&cs=srgb&fm=jpg&w=500&q=80';

type Word = { id: string; headword: string; simple_definition: string; cefr?: string; part_of_speech?: string; saved?: boolean };
type Topic = { slug: string; name: string; icon: string; word_count: number };

export default function Discover() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();

  const params = useLocalSearchParams<{ q?: string }>();
  const [search, setSearch] = useState('');
  const [cefr, setCefr] = useState('All');
  const [topic, setTopic] = useState<string | null>(null);

  useEffect(() => {
    if (params.q) setSearch(String(params.q));
  }, [params.q]);

  const topicsQ = useQuery({ queryKey: ['topics'], queryFn: () => api<{ topics: Topic[] }>('/topics') });

  const filtering = !!search || cefr !== 'All' || !!topic;
  const wordsQ = useQuery({
    queryKey: ['words', search, cefr, topic],
    queryFn: () => {
      const params = new URLSearchParams({ limit: '50' });
      if (search) params.set('search', search);
      if (cefr !== 'All') params.set('cefr', cefr);
      if (topic) params.set('topic', topic);
      return api<{ words: Word[]; total: number }>(`/words?${params.toString()}`);
    },
    placeholderData: keepPreviousData,
  });

  const toggleSave = async (w: Word) => {
    try {
      if (w.saved) await api(`/words/${w.id}/save`, { method: 'DELETE' });
      else await api(`/words/${w.id}/save`, { method: 'POST' });
      qc.invalidateQueries({ queryKey: ['words'] });
      qc.invalidateQueries({ queryKey: ['saved'] });
    } catch { /* ignore */ }
  };

  const renderWord = ({ item }: { item: Word }) => (
    <Card style={styles.wordRow} onPress={() => router.push(`/word/${item.id}`)} testID={`word-row-${item.id}`}>
      <View style={{ flex: 1 }}>
        <View style={styles.wordHead}>
          <AppText weight="medium" size={17}>{item.headword}</AppText>
          <CefrBadge level={item.cefr} small />
        </View>
        <AppText size={14} color={colors.muted} numberOfLines={1} style={{ marginTop: 3 }}>{item.simple_definition}</AppText>
      </View>
      <Pressable testID={`save-word-${item.id}`} onPress={() => toggleSave(item)} hitSlop={8} style={styles.saveBtn}>
        <Icon name={item.saved ? 'bookmark' : 'bookmark-outline'} size={22} color={item.saved ? colors.brand : colors.muted} />
      </Pressable>
    </Card>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top + 12 }]}>
      {/* sticky header */}
      <View style={styles.header}>
        <AppText weight="semibold" size={28} style={{ marginBottom: 12 }}>Discover</AppText>
        <View style={styles.searchBar}>
          <Icon name="magnify" size={20} color={colors.muted} />
          <TextInput
            testID="search-input"
            value={search}
            onChangeText={setSearch}
            placeholder="Search words or meanings"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
            autoCapitalize="none"
          />
          {search ? (
            <Pressable onPress={() => setSearch('')} hitSlop={8}><Icon name="close-circle" size={18} color={colors.muted} /></Pressable>
          ) : null}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {CEFR.map((c) => (
            <Pressable key={c} testID={`cefr-chip-${c}`} onPress={() => setCefr(c)} style={[styles.chip, cefr === c ? styles.chipActive : styles.chipInactive]}>
              <AppText weight="medium" size={14} color={cefr === c ? colors.onSurfaceInverse : colors.onSurfaceTertiary}>{c}</AppText>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      {filtering ? (
        <FlatList
          data={wordsQ.data?.words ?? []}
          keyExtractor={(w) => w.id}
          renderItem={renderWord}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          ListHeaderComponent={
            topic ? (
              <Pressable onPress={() => setTopic(null)} style={styles.clearTopic}>
                <Icon name="close" size={16} color={colors.brand} />
                <AppText size={13} weight="medium" color={colors.brand}>{topicsQ.data?.topics.find((t) => t.slug === topic)?.name}</AppText>
              </Pressable>
            ) : null
          }
          ListEmptyComponent={
            wordsQ.isLoading ? (
              <View style={{ gap: 12 }}>{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={72} rounded={16} />)}</View>
            ) : (
              <View style={styles.empty}>
                <Image source={EMPTY_IMG} style={styles.emptyImg} contentFit="cover" />
                <AppText weight="medium" size={16} style={{ marginTop: 12 }}>No words found</AppText>
                <AppText size={14} color={colors.muted} style={{ marginTop: 4 }}>Try another search or level.</AppText>
              </View>
            )
          }
        />
      ) : (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          <AppText weight="medium" size={16} style={styles.section}>Browse by topic</AppText>
          {topicsQ.isLoading ? (
            <View style={styles.grid}>{[0, 1, 2, 3].map((i) => <Skeleton key={i} width="47%" height={120} rounded={16} />)}</View>
          ) : (
            <View style={styles.grid}>
              {topicsQ.data?.topics.map((t) => (
                <Pressable key={t.slug} testID={`topic-${t.slug}`} onPress={() => setTopic(t.slug)} style={styles.topicCard}>
                  <View style={styles.topicIcon}><Icon name={t.icon as any} size={24} color={colors.brand} /></View>
                  <AppText weight="medium" size={15} style={{ marginTop: 10 }}>{t.name}</AppText>
                  <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>{t.word_count} words</AppText>
                </Pressable>
              ))}
            </View>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: { paddingHorizontal: t.spacing.lg, paddingBottom: t.spacing.md, borderBottomWidth: 1, borderBottomColor: t.colors.divider },
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm, backgroundColor: t.colors.surfaceTertiary, borderRadius: t.radius.md, paddingHorizontal: t.spacing.md, height: 48 },
  searchInput: { flex: 1, fontFamily: t.fontFamily.regular, fontSize: 15, color: t.colors.onSurface, height: '100%' },
  chipRow: { gap: t.spacing.sm, paddingTop: t.spacing.md, paddingRight: t.spacing.lg },
  chip: { height: 36, paddingHorizontal: t.spacing.lg, borderRadius: t.radius.pill, alignItems: 'center', justifyContent: 'center', borderWidth: 1, flexShrink: 0 },
  chipActive: { backgroundColor: t.colors.surfaceInverse, borderColor: t.colors.surfaceInverse },
  chipInactive: { backgroundColor: t.colors.surface, borderColor: t.colors.border },
  list: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.lg, paddingBottom: 32, gap: 12 },
  section: { marginBottom: 4 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md },
  topicCard: { width: '47%', flexGrow: 1, backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.lg, borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg, ...t.shadow.sm },
  topicIcon: { width: 48, height: 48, borderRadius: t.radius.md, backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center' },
  wordRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  wordHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  saveBtn: { padding: 4 },
  clearTopic: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', backgroundColor: t.colors.brandTertiary, paddingHorizontal: t.spacing.md, paddingVertical: 6, borderRadius: t.radius.pill, marginBottom: 4 },
  empty: { alignItems: 'center', paddingTop: 48 },
  emptyImg: { width: 120, height: 120, borderRadius: 60 },
}));
