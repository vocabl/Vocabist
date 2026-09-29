import React from 'react';
import { View, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { Skeleton } from '@/src/components/Skeleton';
import { api } from '@/src/api/client';

type Exam = {
  slug: string; name: string; full_name: string; description: string;
  word_count: number; active: boolean;
};

export default function Exams() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const examsQ = useQuery({ queryKey: ['exams'], queryFn: () => api<{ exams: Exam[]; exam_date?: string }>('/exams') });

  const countdown = () => {
    if (!examsQ.data?.exam_date) return null;
    try {
      const days = Math.ceil((new Date(examsQ.data.exam_date).getTime() - Date.now()) / 86400000);
      return days > 0 ? `${days} days left` : 'Exam day!';
    } catch { return null; }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 12, paddingBottom: 32 }]}
      showsVerticalScrollIndicator={false}
    >
      <AppText weight="semibold" size={28} style={styles.h1}>Exams</AppText>
      <AppText size={15} color={colors.muted} style={styles.sub}>Target-focused vocabulary for every test.</AppText>

      {examsQ.isLoading ? (
        <View style={{ gap: 12 }}>
          {[0, 1, 2].map((i) => <Skeleton key={i} height={120} rounded={20} />)}
        </View>
      ) : examsQ.isError ? (
        <Card><AppText color={colors.muted}>Couldn't load exams.</AppText></Card>
      ) : (
        <View style={{ gap: 14 }}>
          {examsQ.data?.exams.map((e) => (
            <Card key={e.slug} style={styles.examCard} onPress={() => router.push(`/exam/${e.slug}`)} testID={`exam-card-${e.slug}`}>
              <View style={styles.examTop}>
                <View style={styles.examInitials}>
                  <AppText weight="semibold" size={16} color={colors.onBrandTertiary}>{e.name.slice(0, 3).toUpperCase()}</AppText>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.nameRow}>
                    <AppText weight="medium" size={18}>{e.name}</AppText>
                    {e.active ? (
                      <View style={styles.activePill}>
                        <AppText size={11} weight="medium" color={colors.onBrand}>ACTIVE</AppText>
                      </View>
                    ) : null}
                  </View>
                  <AppText size={13} color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>{e.description}</AppText>
                </View>
              </View>
              <View style={styles.examMeta}>
                <View style={styles.metaItem}>
                  <Icon name="book-outline" size={16} color={colors.onSurfaceTertiary} />
                  <AppText size={13} color={colors.onSurfaceTertiary}>{e.word_count} words</AppText>
                </View>
                {e.active && countdown() ? (
                  <View style={styles.metaItem}>
                    <Icon name="calendar-clock" size={16} color={colors.warning} />
                    <AppText size={13} color={colors.warning}>{countdown()}</AppText>
                  </View>
                ) : null}
                <View style={{ flex: 1 }} />
                <Icon name="chevron-right" size={20} color={colors.muted} />
              </View>
            </Card>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  content: { paddingHorizontal: t.spacing.lg },
  h1: { marginBottom: 4 },
  sub: { marginBottom: t.spacing.xl },
  examCard: { gap: t.spacing.md },
  examTop: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  examInitials: { width: 52, height: 52, borderRadius: t.radius.md, backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  activePill: { backgroundColor: t.colors.brand, paddingHorizontal: 8, paddingVertical: 3, borderRadius: t.radius.sm },
  examMeta: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.lg, borderTopWidth: 1, borderTopColor: t.colors.divider, paddingTop: t.spacing.md },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
}));
