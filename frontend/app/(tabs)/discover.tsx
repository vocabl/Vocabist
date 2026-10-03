import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, ScrollView, FlatList, Pressable, TextInput, RefreshControl } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { WordRow, WordRowItem } from '@/src/components/WordRow';
import { EmptyState } from '@/src/components/EmptyState';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

const CEFR = ['All', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

type Topic = { slug: string; name: string; icon: string; word_count: number; description?: string };
type Exam = { slug: string; name: string; description?: string; active?: boolean; word_count?: number };
type WordsResponse = { words: WordRowItem[]; total: number; offset: number; limit: number };
type Mission = { continue_word: { id: string; headword: string; simple_definition: string; cefr?: string } | null };

export default function Discover() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

  const params = useLocalSearchParams<{ q?: string }>();
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [cefr, setCefr] = useState('All');
  const [offset, setOffset] = useState(0);
  const [accumulated, setAccumulated] = useState<WordRowItem[]>([]);

  // Keep debounced in sync without firing a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [search]);

  // External param-based search (e.g. from Home)
  useEffect(() => {
    if (params.q !== undefined) {
      setSearch(String(params.q));
      setDebouncedSearch(String(params.q));
    }
  }, [params.q]);

  // Reset pagination whenever filters change.
  const filtersKey = `${debouncedSearch}|${cefr}`;
  const lastKey = useRef(filtersKey);
  useEffect(() => {
    if (lastKey.current !== filtersKey) {
      lastKey.current = filtersKey;
      setOffset(0);
      setAccumulated([]);
    }
  }, [filtersKey]);

  const filtering = debouncedSearch.trim().length > 0 || cefr !== 'All';

  const topicsQ = useQuery({ queryKey: ['topics'], queryFn: () => api<{ topics: Topic[] }>('/topics'), staleTime: 10 * 60_000 });
  const examsQ = useQuery({ queryKey: ['exams'], queryFn: () => api<{ exams: Exam[] }>('/exams'), staleTime: 10 * 60_000 });
  const missionQ = useQuery({ queryKey: ['mission'], queryFn: () => api<Mission>('/mission'), staleTime: 2 * 60_000 });

  const wordsQ = useQuery({
    queryKey: ['words', debouncedSearch, cefr, offset],
    queryFn: () => {
      const sp = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (debouncedSearch) sp.set('search', debouncedSearch);
      if (cefr !== 'All') sp.set('cefr', cefr);
      return api<WordsResponse>(`/words?${sp.toString()}`);
    },
    placeholderData: keepPreviousData,
    enabled: filtering,
    staleTime: 60_000,
  });

  // Accumulate pages (dedupe by canonical id) so "Load more" grows the list.
  useEffect(() => {
    if (!wordsQ.data) return;
    setAccumulated((prev) => {
      if (wordsQ.data!.offset === 0) return wordsQ.data!.words;
      const seen = new Set(prev.map((w) => w.id));
      const next = wordsQ.data!.words.filter((w) => !seen.has(w.id));
      return [...prev, ...next];
    });
  }, [wordsQ.data]);

  const total = wordsQ.data?.total ?? 0;
  const canLoadMore = filtering && accumulated.length < total && !wordsQ.isFetching;

  const toggleSave = async (w: WordRowItem) => {
    // Optimistic
    setAccumulated((prev) => prev.map((x) => (x.id === w.id ? { ...x, saved: !x.saved } : x)));
    try {
      if (w.saved) await api(`/words/${w.id}/save`, { method: 'DELETE' });
      else {
        await api(`/words/${w.id}/save`, { method: 'POST' });
        toast.show('Saved to your words', 'success');
      }
      qc.invalidateQueries({ queryKey: ['saved'] });
      // Keep this page's cache but don't disturb accumulation.
    } catch {
      // Revert
      setAccumulated((prev) => prev.map((x) => (x.id === w.id ? { ...x, saved: w.saved } : x)));
      toast.show('Could not update', 'error');
    }
  };

  const clearFilters = () => {
    setSearch('');
    setDebouncedSearch('');
    setCefr('All');
  };

  const results = filtering ? accumulated : [];
  const examsSorted = useMemo(
    () => (examsQ.data?.exams ?? []).slice().sort((a, b) => Number(!!b.active) - Number(!!a.active)),
    [examsQ.data],
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top + 12 }]}>
      {/* Sticky header */}
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
            returnKeyType="search"
          />
          {search ? (
            <Pressable
              onPress={clearFilters}
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
          data={results}
          keyExtractor={(w) => w.id}
          contentContainerStyle={styles.list}
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={wordsQ.isRefetching && offset === 0}
              onRefresh={() => {
                setOffset(0);
                setAccumulated([]);
                wordsQ.refetch();
              }}
              tintColor={colors.brand}
            />
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
          ListFooterComponent={
            !filtering ? null : wordsQ.isFetching && offset > 0 ? (
              <View style={{ paddingTop: 12, gap: 12 }}>
                <Skeleton height={72} rounded={16} />
                <Skeleton height={72} rounded={16} />
              </View>
            ) : canLoadMore ? (
              <View style={{ paddingTop: 12 }}>
                <Button
                  testID="discover-load-more"
                  label={`Load more · ${total - accumulated.length} remaining`}
                  variant="secondary"
                  onPress={() => setOffset(accumulated.length)}
                />
              </View>
            ) : accumulated.length > 0 && accumulated.length >= total ? (
              <AppText size={12} color={colors.onSurfaceTertiary} style={styles.endOfList}>
                That&apos;s everything matching this search.
              </AppText>
            ) : null
          }
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
                description="Try another spelling or clear the level filter."
                action={{ label: 'Clear filters', onPress: clearFilters, testID: 'discover-clear-filters' }}
              />
            )
          }
        />
      ) : (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          {/* Continue exploring — only the real continue_word, never fabricated */}
          {missionQ.data?.continue_word ? (
            <>
              <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionLabel}>
                PICK UP WHERE YOU LEFT OFF
              </AppText>
              <Pressable
                testID="discover-continue"
                onPress={() => router.push(`/word/${missionQ.data!.continue_word!.id}`)}
                accessibilityRole="button"
                accessibilityLabel={`Open ${missionQ.data!.continue_word.headword}`}
              >
                <Card style={styles.continueCard}>
                  <View style={styles.continueIcon}>
                    <Icon name="book-open-variant" size={20} color={colors.brand} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <AppText weight="medium" size={16}>{missionQ.data!.continue_word.headword}</AppText>
                    <AppText size={13} color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>
                      {missionQ.data!.continue_word.simple_definition}
                    </AppText>
                  </View>
                  <Icon name="chevron-right" size={22} color={colors.muted} />
                </Card>
              </Pressable>
            </>
          ) : null}

          <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionLabel}>
            EXPLORE TOPICS
          </AppText>
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
                  onPress={() => router.push(`/topic/${t.slug}`)}
                  style={styles.topicCard}
                  accessibilityRole="button"
                  accessibilityLabel={`Browse ${t.name}`}
                >
                  <View style={styles.topicIcon}>
                    <Icon name={t.icon as any} size={24} color={colors.brand} />
                  </View>
                  <AppText weight="medium" size={15} style={{ marginTop: 10 }}>{t.name}</AppText>
                  <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>
                    {t.word_count} word{t.word_count === 1 ? '' : 's'}
                  </AppText>
                </Pressable>
              ))}
            </View>
          )}

          {/* Exam vocabulary — real list from /exams, only rendered when non-empty */}
          {!examsQ.isLoading && examsSorted.length > 0 ? (
            <>
              <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionLabel}>
                EXAM VOCABULARY
              </AppText>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
                {examsSorted.map((e) => (
                  <Pressable
                    key={e.slug}
                    testID={`discover-exam-${e.slug}`}
                    onPress={() => router.push(`/exam/${e.slug}`)}
                    style={styles.examPill}
                    accessibilityRole="button"
                    accessibilityLabel={`Open ${e.name}`}
                  >
                    <Icon name="trophy-outline" size={18} color={colors.brand} />
                    <View style={{ marginLeft: 8 }}>
                      <AppText weight="medium" size={14}>{e.name}</AppText>
                      {typeof e.word_count === 'number' ? (
                        <AppText size={12} color={colors.muted} style={{ marginTop: 1 }}>
                          {e.word_count} words
                        </AppText>
                      ) : null}
                    </View>
                  </Pressable>
                ))}
              </ScrollView>
            </>
          ) : null}
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

  sectionLabel: { letterSpacing: 0.5, marginTop: t.spacing.sm, marginBottom: 2 },

  continueCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  continueIcon: {
    width: 44, height: 44, borderRadius: t.radius.md,
    backgroundColor: t.colors.brandTertiary,
    alignItems: 'center', justifyContent: 'center',
  },

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

  examPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: t.colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: t.colors.border,
    borderRadius: t.radius.md,
    paddingHorizontal: t.spacing.md,
    paddingVertical: 10,
    minHeight: 48,
  },

  endOfList: { textAlign: 'center', paddingVertical: t.spacing.md },
}));
