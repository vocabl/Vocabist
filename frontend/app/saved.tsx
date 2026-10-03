import React from 'react';
import { View, FlatList, Pressable, RefreshControl } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { WordRow, WordRowItem } from '@/src/components/WordRow';
import { EmptyState } from '@/src/components/EmptyState';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

type SavedResponse = { words: WordRowItem[] };

export default function Saved() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

  const q = useQuery({
    queryKey: ['saved'],
    queryFn: () => api<SavedResponse>('/saved'),
  });

  const items = (q.data?.words ?? []).map((w) => ({ ...w, saved: true }));

  const unsave = async (w: WordRowItem) => {
    try {
      await api(`/words/${w.id}/save`, { method: 'DELETE' });
      qc.invalidateQueries({ queryKey: ['saved'] });
      qc.invalidateQueries({ queryKey: ['words'] });
      toast.show('Removed from saved', 'info');
    } catch {
      toast.show('Could not update', 'error');
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.topBar}>
        <Pressable
          testID="saved-back"
          onPress={() => router.back()}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Back"
          style={styles.backBtn}
        >
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={20}>Saved words</AppText>
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
          items.length > 0 ? (
            <View style={styles.intro}>
              <AppText size={14} color={colors.muted}>
                {items.length} word{items.length === 1 ? '' : 's'} saved · tap a word to open its detail
              </AppText>
            </View>
          ) : null
        }
        renderItem={({ item }) => (
          <WordRow
            item={item}
            onPress={() => router.push(`/word/${item.id}`)}
            onToggleSave={() => unsave(item)}
            trailing="save"
            testID={`saved-word-${item.id}`}
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
              title="Couldn't load saved words"
              description="Please check your connection and try again."
              action={{ label: 'Retry', onPress: () => q.refetch(), testID: 'saved-retry' }}
            />
          ) : (
            <EmptyState
              icon="bookmark-outline"
              title="No saved words yet"
              description="Save words you want to remember and revisit. Everything you save shows up here, ready to practise."
              action={{
                label: 'Discover words',
                onPress: () => router.push('/(tabs)/discover'),
                testID: 'saved-empty-discover',
              }}
            />
          )
        }
      />

      {/* Sticky practice CTA */}
      {!q.isLoading && items.length > 0 ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          <Button
            testID="saved-practice-button"
            label={`Practise saved · ${items.length}`}
            icon="play"
            onPress={() => router.push('/session?source=saved')}
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
  intro: { paddingBottom: t.spacing.lg },
  cta: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md,
    backgroundColor: t.colors.surface,
    borderTopWidth: 1, borderTopColor: t.colors.divider,
  },
}));
