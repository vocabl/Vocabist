import React from 'react';
import { View, FlatList, Pressable, RefreshControl } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { WordRow, WordRowItem } from '@/src/components/WordRow';
import { EmptyState } from '@/src/components/EmptyState';
import { api } from '@/src/api/client';

type SlippingResponse = { count: number; words: WordRowItem[] };

export default function Review() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const q = useQuery({
    queryKey: ['slipping'],
    queryFn: () => api<SlippingResponse>('/review/slipping'),
  });

  const items = q.data?.words ?? [];
  const count = q.data?.count ?? 0;

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
        <AppText weight="semibold" size={20}>Review</AppText>
        <View style={styles.backBtn} />
      </View>

      <FlatList
        data={items}
        keyExtractor={(w) => w.id}
        contentContainerStyle={[
          styles.list,
          { paddingBottom: insets.bottom + (items.length > 0 ? 110 : 24) },
        ]}
        ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brand} />
        }
        ListHeaderComponent={
          <View style={styles.intro}>
            <AppText weight="semibold" size={28}>
              {q.isLoading ? '…' : count > 0 ? `${count} word${count === 1 ? '' : 's'} to review` : 'All caught up'}
            </AppText>
            <AppText size={15} color={colors.muted} style={{ marginTop: 6, lineHeight: 22 }}>
              {count > 0
                ? 'A short review now will keep these words in your long-term memory.'
                : 'Nothing is slipping right now. Keep practising to build mastery.'}
            </AppText>
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
          q.isLoading ? (
            <View style={{ gap: 12, paddingTop: 8 }}>
              {[0, 1, 2].map((i) => <Skeleton key={i} height={76} rounded={16} />)}
            </View>
          ) : q.isError ? (
            <EmptyState
              icon="alert-circle-outline"
              title="Couldn't load review"
              description="Please check your connection and try again."
              action={{ label: 'Retry', onPress: () => q.refetch(), testID: 'review-retry' }}
            />
          ) : (
            <EmptyState
              icon="check-all"
              title="All caught up"
              description="You're on top of your reviews. Discover new words or practise what you're learning."
              action={{ label: 'Discover words', onPress: () => router.push('/(tabs)/discover'), testID: 'review-empty-discover' }}
              secondaryAction={{ label: 'Open Learn', onPress: () => router.push('/(tabs)/learn'), testID: 'review-empty-learn' }}
            />
          )
        }
      />

      {/* Sticky start-review CTA when there are items */}
      {!q.isLoading && items.length > 0 ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          <Button
            testID="review-start-button"
            label={`Start review · ${count}`}
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
  list: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.sm },
  intro: { paddingBottom: t.spacing.xl },
  cta: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md,
    backgroundColor: t.colors.surface,
    borderTopWidth: 1, borderTopColor: t.colors.divider,
  },
}));
