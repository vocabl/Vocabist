import React, { useEffect, useState } from 'react';
import { View, FlatList, Pressable, RefreshControl } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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

const PAGE_SIZE = 25;

type Topic = { slug: string; name: string; icon: string; word_count: number; description?: string };
type WordsResponse = { words: WordRowItem[]; total: number; offset: number; limit: number };

/**
 * Topic detail — browse real vocabulary within a canonical backend topic.
 *
 * Uses `/words?topic=<slug>&limit=&offset=` (real server-side pagination) and
 * `/topics` for the title. No frontend topic metadata is invented.
 */
export default function TopicDetail() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

  const { slug: rawSlug } = useLocalSearchParams<{ slug: string }>();
  const slug = String(rawSlug ?? '');

  const topicsQ = useQuery({
    queryKey: ['topics'],
    queryFn: () => api<{ topics: Topic[] }>('/topics'),
    staleTime: 10 * 60_000,
  });
  const topic = topicsQ.data?.topics.find((t) => t.slug === slug);

  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<WordRowItem[]>([]);

  useEffect(() => {
    // Reset when slug changes
    setOffset(0);
    setItems([]);
  }, [slug]);

  const wordsQ = useQuery({
    queryKey: ['words', 'topic', slug, offset],
    queryFn: () => {
      const sp = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset), topic: slug });
      return api<WordsResponse>(`/words?${sp.toString()}`);
    },
    enabled: !!slug,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!wordsQ.data) return;
    setItems((prev) => {
      if (wordsQ.data!.offset === 0) return wordsQ.data!.words;
      const seen = new Set(prev.map((w) => w.id));
      const next = wordsQ.data!.words.filter((w) => !seen.has(w.id));
      return [...prev, ...next];
    });
  }, [wordsQ.data]);

  const total = wordsQ.data?.total ?? 0;
  const canLoadMore = items.length < total && !wordsQ.isFetching;
  const loading = wordsQ.isLoading && items.length === 0;

  const toggleSave = async (w: WordRowItem) => {
    setItems((prev) => prev.map((x) => (x.id === w.id ? { ...x, saved: !x.saved } : x)));
    try {
      if (w.saved) await api(`/words/${w.id}/save`, { method: 'DELETE' });
      else {
        await api(`/words/${w.id}/save`, { method: 'POST' });
        toast.show('Saved to your words', 'success');
      }
      qc.invalidateQueries({ queryKey: ['saved'] });
    } catch {
      setItems((prev) => prev.map((x) => (x.id === w.id ? { ...x, saved: w.saved } : x)));
      toast.show('Could not update', 'error');
    }
  };

  const hasItems = items.length > 0;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.topBar}>
        <Pressable
          testID="topic-back"
          onPress={() => router.back()}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Back"
          style={styles.backBtn}
        >
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={20} numberOfLines={1} style={{ flex: 1, textAlign: 'center' }}>
          {topic?.name ?? 'Topic'}
        </AppText>
        <View style={styles.backBtn} />
      </View>

      <FlatList
        data={items}
        keyExtractor={(w) => w.id}
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + (hasItems ? 110 : 24) },
        ]}
        ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={wordsQ.isRefetching && offset === 0}
            onRefresh={() => {
              setOffset(0);
              setItems([]);
              wordsQ.refetch();
            }}
            tintColor={colors.brand}
          />
        }
        ListHeaderComponent={
          <View style={{ gap: 12 }}>
            {topic ? (
              <Card style={styles.hero}>
                <View style={styles.heroHead}>
                  <View style={styles.heroIcon}>
                    <Icon name={(topic.icon as any) ?? 'shape-outline'} size={22} color={colors.onBrand} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <AppText size={13} weight="medium" color={colors.brand}>Topic</AppText>
                    <AppText weight="semibold" size={22} style={{ marginTop: 2 }}>{topic.name}</AppText>
                  </View>
                </View>
                {topic.description ? (
                  <AppText size={14} color={colors.muted} style={{ marginTop: 10, lineHeight: 20 }}>
                    {topic.description}
                  </AppText>
                ) : null}
                <AppText size={13} color={colors.onSurfaceTertiary} style={{ marginTop: 10 }}>
                  {total > 0
                    ? `${total} word${total === 1 ? '' : 's'} · tap any word to open its detail`
                    : loading
                    ? 'Loading vocabulary…'
                    : 'No words in this topic yet'}
                </AppText>
              </Card>
            ) : topicsQ.isLoading ? (
              <Skeleton height={120} rounded={16} />
            ) : null}
          </View>
        }
        renderItem={({ item }) => (
          <WordRow
            item={item}
            onPress={() => router.push(`/word/${item.id}`)}
            onToggleSave={() => toggleSave(item)}
            trailing="save"
            testID={`topic-word-${item.id}`}
          />
        )}
        ListFooterComponent={
          loading ? null : wordsQ.isFetching && offset > 0 ? (
            <View style={{ paddingTop: 12, gap: 12 }}>
              <Skeleton height={72} rounded={16} />
              <Skeleton height={72} rounded={16} />
            </View>
          ) : canLoadMore ? (
            <View style={{ paddingTop: 12 }}>
              <Button
                testID="topic-load-more"
                label={`Load more · ${total - items.length} remaining`}
                variant="secondary"
                onPress={() => setOffset(items.length)}
              />
            </View>
          ) : hasItems ? (
            <AppText size={12} color={colors.onSurfaceTertiary} style={styles.endOfList}>
              That&apos;s every word in this topic.
            </AppText>
          ) : null
        }
        ListEmptyComponent={
          loading ? (
            <View style={{ gap: 12, paddingTop: 8 }}>
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} height={76} rounded={16} />)}
            </View>
          ) : wordsQ.isError ? (
            <EmptyState
              icon="alert-circle-outline"
              title="Couldn't load this topic"
              description="Please try again."
              action={{ label: 'Retry', onPress: () => wordsQ.refetch(), testID: 'topic-retry' }}
            />
          ) : (
            <EmptyState
              icon="shape-outline"
              title="No words in this topic"
              description="Explore another topic from Discover."
              action={{
                label: 'Back to Discover',
                onPress: () => router.replace('/(tabs)/discover'),
                testID: 'topic-empty-back',
              }}
            />
          )
        }
      />

      {hasItems ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          <Button
            testID="topic-practice-button"
            label={`Practise this topic`}
            icon="play"
            onPress={() => router.push(`/session?source=topic&ref=${slug}`)}
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
  content: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.sm, gap: 0 },

  hero: {},
  heroHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  heroIcon: {
    width: 48, height: 48, borderRadius: t.radius.md,
    backgroundColor: t.colors.brand,
    alignItems: 'center', justifyContent: 'center',
  },

  endOfList: { textAlign: 'center', paddingVertical: t.spacing.md },

  cta: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md,
    backgroundColor: t.colors.surface,
    borderTopWidth: 1, borderTopColor: t.colors.divider,
  },
}));
