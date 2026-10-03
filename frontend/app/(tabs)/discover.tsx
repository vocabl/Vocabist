import React, { useEffect, useState } from 'react';
import { View, ScrollView, FlatList, Pressable, TextInput, RefreshControl } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { WordRow, WordRowItem } from '@/src/components/WordRow';
import { EmptyState } from '@/src/components/EmptyState';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

const CEFR = ['All', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

type Topic = { slug: string; name: string; icon: string; word_count: number };

export default function Discover() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

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
      const sp = new URLSearchParams({ limit: '50' });
      if (search) sp.set('search', search);
      if (cefr !== 'All') sp.set('cefr', cefr);
      if (topic) sp.set('topic', topic);
      return api<{ words: WordRowItem[]; total: number }>(`/words?${sp.toString()}`);
    },
    placeholderData: keepPreviousData,
    enabled: filtering,
  });

  const toggleSave = async (w: WordRowItem) => {
    try {
      if (w.saved) {
        await api(`/words/${w.id}/save`, { method: 'DELETE' });
      } else {
        await api(`/words/${w.id}/save`, { method: 'POST' });
        toast.show('Saved to your words', 'success');
      }
      qc.invalidateQueries({ queryKey: ['words'] });
      qc.invalidateQueries({ queryKey: ['saved'] });
    } catch {
      toast.show('Could not update', 'error');
    }
  };

  const clearFilters = () => {
    setSearch('');
    setCefr('All');
    setTopic(null);
  };

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
            accessibilityLabel="Search vocabulary"
          />
          {search ? (
            <Pressable
              onPress={() => setSearch('')}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel="Clear search"
            >
              <Icon name="close-circle" size={18} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {CEFR.map((c) => (
            <Pressable
              key={c}
              testID={`cefr-chip-${c}`}
              onPress={() => setCefr(c)}
              style={[styles.chip, cefr === c ? styles.chipActive : styles.chipInactive]}
              accessibilityRole="button"
              accessibilityLabel={`Filter level ${c}`}
              accessibilityState={{ selected: cefr === c }}
            >
              <AppText
                weight="medium"
                size={14}
                color={cefr === c ? colors.onSurfaceInverse : colors.onSurfaceTertiary}
              >
                {c}
              </AppText>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      {filtering ? (
        <FlatList
          data={wordsQ.data?.words ?? []}
          keyExtractor={(w) => w.id}
          contentContainerStyle={styles.list}
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={wordsQ.isRefetching}
              onRefresh={() => wordsQ.refetch()}
              tintColor={colors.brand}
            />
          }
          ListHeaderComponent={
            topic ? (
              <Pressable
                onPress={() => setTopic(null)}
                style={styles.clearTopic}
                accessibilityRole="button"
                accessibilityLabel="Clear topic filter"
              >
                <Icon name="close" size={16} color={colors.brand} />
                <AppText size={13} weight="medium" color={colors.brand}>
                  {topicsQ.data?.topics.find((t) => t.slug === topic)?.name ?? 'Topic'}
                </AppText>
              </Pressable>
            ) : null
          }
          renderItem={({ item }) => (
            <WordRow
              item={item}
              onPress={() => router.push(`/word/${item.id}`)}
              onToggleSave={() => toggleSave(item)}
              trailing="save"
              testID={`word-row-${item.id}`}
            />
          )}
          ListEmptyComponent={
            wordsQ.isLoading ? (
              <View style={{ gap: 12 }}>
                {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={72} rounded={16} />)}
              </View>
            ) : wordsQ.isError ? (
              <EmptyState
                icon="alert-circle-outline"
                title="Couldn't load results"
                description="Check your connection and try again."
                action={{ label: 'Retry', onPress: () => wordsQ.refetch(), testID: 'discover-retry' }}
              />
            ) : (
              <EmptyState
                icon="magnify-close"
                title="No words found"
                description="Try another search term or clear the level filter."
                action={{ label: 'Clear filters', onPress: clearFilters, testID: 'discover-clear-filters' }}
              />
            )
          }
        />
      ) : (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          <AppText weight="medium" size={16} style={styles.section}>Browse by topic</AppText>
          {topicsQ.isLoading ? (
            <View style={styles.grid}>
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} width="47%" height={120} rounded={16} />)}
            </View>
          ) : topicsQ.isError ? (
            <EmptyState
              icon="alert-circle-outline"
              title="Couldn't load topics"
              description="Please try again."
              action={{ label: 'Retry', onPress: () => topicsQ.refetch(), testID: 'topics-retry' }}
              compact
            />
          ) : (topicsQ.data?.topics ?? []).length === 0 ? (
            <EmptyState
              icon="shape-outline"
              title="No topics yet"
              description="Topics will appear here once vocabulary is grouped."
              compact
            />
          ) : (
            <View style={styles.grid}>
              {topicsQ.data?.topics.map((t) => (
                <Pressable
                  key={t.slug}
                  testID={`topic-${t.slug}`}
                  onPress={() => setTopic(t.slug)}
                  style={styles.topicCard}
                  accessibilityRole="button"
                  accessibilityLabel={`Browse ${t.name}`}
                >
                  <View style={styles.topicIcon}>
                    <Icon name={t.icon as any} size={24} color={colors.brand} />
                  </View>
                  <AppText weight="medium" size={15} style={{ marginTop: 10 }}>{t.name}</AppText>
                  <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>
                    {t.word_count} words
                  </AppText>
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
  header: {
    paddingHorizontal: t.spacing.lg,
    paddingBottom: t.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: t.colors.divider,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: t.spacing.sm,
    backgroundColor: t.colors.surfaceTertiary,
    borderRadius: t.radius.md,
    paddingHorizontal: t.spacing.md,
    height: 48,
  },
  searchInput: {
    flex: 1,
    fontFamily: t.fontFamily.regular,
    fontSize: 15,
    color: t.colors.onSurface,
    height: '100%',
  },
  chipRow: { gap: t.spacing.sm, paddingTop: t.spacing.md, paddingRight: t.spacing.lg },
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
  list: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.lg, paddingBottom: 32, gap: 12 },
  section: { marginBottom: 4 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.md },
  topicCard: {
    width: '47%',
    flexGrow: 1,
    backgroundColor: t.colors.surfaceSecondary,
    borderRadius: t.radius.lg,
    borderWidth: 1,
    borderColor: t.colors.border,
    padding: t.spacing.lg,
    ...t.shadow.sm,
  },
  topicIcon: {
    width: 48,
    height: 48,
    borderRadius: t.radius.md,
    backgroundColor: t.colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  clearTopic: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    backgroundColor: t.colors.brandTertiary,
    paddingHorizontal: t.spacing.md,
    paddingVertical: 6,
    borderRadius: t.radius.pill,
    marginBottom: 4,
  },
}));
