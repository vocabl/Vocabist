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

type Topic = { slug: string; name: string; icon: string; description: string; word_count: number };

export default function Learn() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const missionQ = useQuery({ queryKey: ['mission'], queryFn: () => api<any>('/mission') });
  const topicsQ = useQuery({ queryKey: ['topics'], queryFn: () => api<{ topics: Topic[] }>('/topics') });
  const savedQ = useQuery({ queryKey: ['saved'], queryFn: () => api<{ words: any[] }>('/saved') });

  const m = missionQ.data;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, { paddingTop: insets.top + 12, paddingBottom: 32 }]}
      showsVerticalScrollIndicator={false}
    >
      <AppText weight="semibold" size={28} style={styles.h1}>Learn</AppText>

      <Card style={styles.missionCard} onPress={() => router.push('/session?source=mission')} testID="learn-mission-card">
        <View style={styles.missionIcon}>
          <Icon name="lightning-bolt" size={24} color={colors.onBrand} />
        </View>
        <View style={{ flex: 1 }}>
          <AppText weight="medium" size={17} color={colors.onSurface}>Today's mission</AppText>
          <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>
            {m ? `${m.total_words} words · ${m.review_count} review · ${m.new_count} new` : 'Loading…'}
          </AppText>
        </View>
        <Icon name="chevron-right" size={22} color={colors.muted} />
      </Card>

      <View style={styles.featureRow}>
        <Card style={styles.featureCard} onPress={() => router.push('/read')} testID="read-learn-card">
          <View style={[styles.topicIcon, { backgroundColor: colors.brandTertiary }]}>
            <Icon name="book-open-page-variant" size={22} color={colors.brand} />
          </View>
          <AppText weight="medium" size={15} style={{ marginTop: 10 }}>Read & Learn</AppText>
          <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>Tap words in short articles</AppText>
        </Card>
        <Card style={styles.featureCard} onPress={() => router.push('/import')} testID="learn-anything-card">
          <View style={[styles.topicIcon, { backgroundColor: '#FBEEDD' }]}>
            <Icon name="file-import-outline" size={22} color={colors.warning} />
          </View>
          <AppText weight="medium" size={15} style={{ marginTop: 10 }}>Learn Anything</AppText>
          <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>Paste text or a PDF</AppText>
        </Card>
      </View>

      <View style={styles.featureRow}>
        <Card style={[styles.featureCard, { width: '100%' }]} onPress={() => router.push('/visual-capture')} testID="visual-capture-card">
          <View style={[styles.topicIcon, { backgroundColor: '#EDE7F6' }]}>
            <Icon name="camera-outline" size={22} color="#7E57C2" />
          </View>
          <AppText weight="medium" size={15} style={{ marginTop: 10 }}>Capture Words</AppText>
          <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>Scan textbook pages or notes</AppText>
        </Card>
      </View>

      <AppText weight="medium" size={16} style={styles.section}>Practice by topic</AppText>
      {topicsQ.isLoading ? (
        <View style={{ gap: 12 }}>
          <Skeleton height={72} rounded={16} /><Skeleton height={72} rounded={16} />
        </View>
      ) : (
        <View style={{ gap: 12 }}>
          {topicsQ.data?.topics.map((t) => (
            <Card key={t.slug} style={styles.topicRow} onPress={() => router.push(`/session?source=topic&ref=${t.slug}`)} testID={`topic-practice-${t.slug}`}>
              <View style={styles.topicIcon}>
                <Icon name={t.icon as any} size={22} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <AppText weight="medium" size={16}>{t.name}</AppText>
                <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>{t.word_count} words</AppText>
              </View>
              <Icon name="play-circle" size={26} color={colors.brand} />
            </Card>
          ))}
        </View>
      )}

      <AppText weight="medium" size={16} style={styles.section}>Saved words</AppText>
      <Card style={styles.topicRow} onPress={() => router.push('/saved')} testID="saved-words-card">
        <View style={[styles.topicIcon, { backgroundColor: '#FBEEDD' }]}>
          <Icon name="bookmark-multiple-outline" size={22} color={colors.warning} />
        </View>
        <View style={{ flex: 1 }}>
          <AppText weight="medium" size={16}>Your saved words</AppText>
          <AppText size={13} color={colors.muted} style={{ marginTop: 2 }}>
            {savedQ.isLoading ? 'Loading…' : `${savedQ.data?.words.length ?? 0} saved · tap to open`}
          </AppText>
        </View>
        <Icon name="chevron-right" size={22} color={colors.muted} />
      </Card>
    </ScrollView>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  content: { paddingHorizontal: t.spacing.lg },
  h1: { marginBottom: t.spacing.lg },
  missionCard: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  missionIcon: { width: 48, height: 48, borderRadius: t.radius.md, backgroundColor: t.colors.brand, alignItems: 'center', justifyContent: 'center' },
  section: { marginTop: t.spacing.xl, marginBottom: t.spacing.md },
  topicRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  topicIcon: { width: 44, height: 44, borderRadius: t.radius.md, backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center' },
  featureRow: { flexDirection: 'row', gap: t.spacing.md, marginTop: t.spacing.lg },
  featureCard: { flex: 1 },
}));
