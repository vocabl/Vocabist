import React, { useState } from 'react';
import { View, ScrollView, Pressable, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Animated, { FadeInDown, LinearTransition } from 'react-native-reanimated';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { CefrBadge } from '@/src/components/CefrBadge';
import { Skeleton } from '@/src/components/Skeleton';
import { useToast } from '@/src/components/Toast';
import { api, ApiError, API } from '@/src/api/client';
import { playAudioUrl } from '@/src/utils/audio';

type WordRef = { id: string | null; headword: string; cefr?: string; simple_definition?: string };
type Detail = {
  word: any;
  graph: { synonyms: WordRef[]; antonyms: WordRef[]; related: WordRef[] };
  exams: { slug: string; name: string }[];
  saved: boolean;
  progress: { status: string; mastery_score: number } | null;
};

export default function WordDetail() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();

  const q = useQuery({ queryKey: ['word', id], queryFn: () => api<Detail>(`/words/${id}`) });
  const d = q.data;
  const w = d?.word;

  const [audio, setAudio] = useState<{ us_url?: string | null; uk_url?: string | null; tts_url?: string | null } | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [coach, setCoach] = useState<{ explanation: string; example: string; mnemonic: string } | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);

  const playPron = async (variant?: 'us' | 'uk') => {
    let a = audio;
    if (!a) {
      setAudioLoading(true);
      try {
        a = await api<typeof audio>(`/words/${id}/audio`);
        setAudio(a);
      } catch {
        toast.show('Audio unavailable', 'error');
        setAudioLoading(false);
        return;
      }
      setAudioLoading(false);
    }
    const url = variant === 'uk' ? a?.uk_url : variant === 'us' ? a?.us_url : (a?.us_url || a?.uk_url || a?.tts_url);
    if (url) await playAudioUrl(url.startsWith('http') ? url : `${API}${url}`);
    else toast.show('Audio unavailable', 'error');
  };

  const runCoach = async () => {
    setCoachLoading(true);
    try {
      const res = await api<{ content: typeof coach }>(`/words/${id}/ai-coach`, { method: 'POST' });
      setCoach(res.content);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        toast.show(e.message, 'info');
        router.push('/paywall');
      } else {
        toast.show(e instanceof ApiError ? e.message : 'AI Coach failed', 'error');
      }
    } finally {
      setCoachLoading(false);
    }
  };

  const toggleSave = async () => {
    if (!d) return;
    try {
      if (d.saved) await api(`/words/${id}/save`, { method: 'DELETE' });
      else { await api(`/words/${id}/save`, { method: 'POST' }); toast.show('Saved to your words', 'success'); }
      qc.invalidateQueries({ queryKey: ['word', id] });
      qc.invalidateQueries({ queryKey: ['saved'] });
      qc.invalidateQueries({ queryKey: ['words'] });
    } catch { toast.show('Could not update', 'error'); }
  };

  const WordChips = ({ items }: { items: WordRef[] }) => (
    <View style={styles.chipWrap}>
      {items.map((it, i) => (
        <Pressable
          key={`${it.headword}-${i}`}
          onPress={() => it.id ? router.push(`/word/${it.id}`) : router.push(`/(tabs)/discover?q=${encodeURIComponent(it.headword)}`)}
          style={styles.wordChip}
          testID={`related-chip-${it.headword}`}
        >
          <AppText size={14} weight="medium" color={colors.onBrandTertiary}>{it.headword}</AppText>
          <Icon name={it.id ? 'arrow-top-right' : 'magnify'} size={13} color={colors.brandSecondary} />
        </Pressable>
      ))}
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="word-back-button" onPress={() => router.back()} hitSlop={10}>
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <Pressable testID="word-save-button" onPress={toggleSave} hitSlop={10}>
          <Icon name={d?.saved ? 'bookmark' : 'bookmark-outline'} size={24} color={d?.saved ? colors.brand : colors.onSurface} />
        </Pressable>
      </View>

      {q.isLoading ? (
        <View style={styles.loading}>
          <Skeleton width={180} height={40} /><Skeleton width={120} height={20} /><Skeleton height={80} rounded={12} />
        </View>
      ) : q.isError || !w ? (
        <View style={styles.loading}>
          <AppText color={colors.muted} style={{ marginBottom: 12 }}>Couldn't load this word.</AppText>
          <Button label="Retry" variant="secondary" size="md" onPress={() => q.refetch()} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 110 }]} showsVerticalScrollIndicator={false}>
          <Animated.View entering={FadeInDown.duration(240)}>
            <View style={styles.headRow}>
              <AppText weight="semibold" size={40} style={{ flexShrink: 1 }}>{w.headword}</AppText>
              <CefrBadge level={w.cefr} />
            </View>
            {w.phonetic ? <AppText size={17} color={colors.muted} style={{ marginTop: 4 }}>{w.phonetic}</AppText> : null}
            <AppText size={14} color={colors.brandSecondary} weight="medium" style={{ marginTop: 4 }}>{w.part_of_speech}</AppText>

            <View style={styles.pronRow}>
              <Pressable testID="pron-listen" onPress={() => playPron()} style={styles.pronBtn}>
                {audioLoading ? <ActivityIndicator size="small" color={colors.brand} /> : <Icon name="volume-high" size={18} color={colors.brand} />}
                <AppText size={14} weight="medium" color={colors.brand}>Listen</AppText>
              </Pressable>
              {audio?.us_url ? (
                <Pressable testID="pron-us" onPress={() => playPron('us')} style={styles.pronMini}><AppText size={13} weight="medium" color={colors.onSurfaceTertiary}>US</AppText></Pressable>
              ) : null}
              {audio?.uk_url ? (
                <Pressable testID="pron-uk" onPress={() => playPron('uk')} style={styles.pronMini}><AppText size={13} weight="medium" color={colors.onSurfaceTertiary}>UK</AppText></Pressable>
              ) : null}
            </View>
            {d?.progress ? (
              <View style={styles.masteryWrap}>
                <View style={styles.statusPill}>
                  <Icon name="progress-check" size={14} color={colors.brand} />
                  <AppText size={12} weight="medium" color={colors.brand}>
                    {d.progress.status} · {Math.round(d.progress.mastery_score)}% mastery
                  </AppText>
                </View>
                <View
                  style={styles.masteryTrack}
                  accessibilityRole="progressbar"
                  accessibilityValue={{
                    min: 0,
                    max: 100,
                    now: Math.round(d.progress.mastery_score),
                  }}
                >
                  <View
                    style={[
                      styles.masteryFill,
                      {
                        width: `${Math.min(100, Math.max(2, Math.round(d.progress.mastery_score)))}%`,
                      },
                    ]}
                  />
                </View>
              </View>
            ) : null}
          </Animated.View>

          <Section title="Meaning">
            <AppText size={18} style={{ lineHeight: 27 }}>{w.simple_definition}</AppText>
            {w.easy_meaning ? <AppText size={15} color={colors.muted} style={{ marginTop: 6 }}>Simply: {w.easy_meaning}</AppText> : null}
            {w.detailed_definition ? <AppText size={15} color={colors.onSurfaceTertiary} style={{ marginTop: 10, lineHeight: 22 }}>{w.detailed_definition}</AppText> : null}
          </Section>

          {w.example ? (
            <Section title="Example">
              <View style={styles.quote}>
                <Icon name="format-quote-open" size={20} color={colors.brandSecondary} />
                <AppText size={16} style={{ flex: 1, fontStyle: 'italic', lineHeight: 24 }}>{w.example}</AppText>
              </View>
            </Section>
          ) : null}

          <Section title="AI Coach">
            {coach ? (
              <Animated.View entering={FadeInDown.duration(240)} style={styles.coachBox}>
                <View style={styles.coachRow}><Icon name="robot-happy-outline" size={18} color={colors.brand} /><AppText size={13} weight="medium" color={colors.brand}>Explanation</AppText></View>
                <AppText size={15} style={{ lineHeight: 22, marginTop: 4 }}>{coach.explanation}</AppText>
                <View style={[styles.coachRow, { marginTop: 14 }]}><Icon name="text-box-outline" size={18} color={colors.brand} /><AppText size={13} weight="medium" color={colors.brand}>Fresh example</AppText></View>
                <AppText size={15} style={{ lineHeight: 22, marginTop: 4, fontStyle: 'italic' }}>{coach.example}</AppText>
                <View style={[styles.coachRow, { marginTop: 14 }]}><Icon name="lightbulb-on-outline" size={18} color={colors.warning} /><AppText size={13} weight="medium" color={colors.brand}>Memory hook</AppText></View>
                <AppText size={15} style={{ lineHeight: 22, marginTop: 4 }}>{coach.mnemonic}</AppText>
              </Animated.View>
            ) : (
              <Pressable testID="ai-coach-button" onPress={runCoach} disabled={coachLoading} style={styles.coachCta}>
                {coachLoading ? <ActivityIndicator size="small" color={colors.brand} /> : <Icon name="robot-happy-outline" size={20} color={colors.brand} />}
                <View style={{ flex: 1 }}>
                  <AppText size={15} weight="medium">{coachLoading ? 'Thinking…' : 'Explain this with AI'}</AppText>
                  <AppText size={13} color={colors.muted} style={{ marginTop: 1 }}>Get a plain explanation, example & memory hook</AppText>
                </View>
                {!coachLoading ? <Icon name="chevron-right" size={20} color={colors.muted} /> : null}
              </Pressable>
            )}
          </Section>

          {d?.graph.synonyms.length ? <Section title="Synonyms"><WordChips items={d.graph.synonyms} /></Section> : null}
          {d?.graph.antonyms.length ? <Section title="Antonyms"><WordChips items={d.graph.antonyms} /></Section> : null}
          {d?.graph.related.length ? <Section title="Related words"><WordChips items={d.graph.related} /></Section> : null}

          {(w.word_family?.length || w.roots?.length || w.mnemonic || w.common_mistakes) ? (
            <ExpandableGroup title="More about this word" testID="more-about-word">
              {(w.word_family?.length || w.roots?.length) ? (
                <SubSection title="Word building">
                  {w.word_family?.length ? <MetaLine label="Family" value={w.word_family.join(', ')} /> : null}
                  {w.roots?.length ? <MetaLine label="Roots" value={w.roots.join(', ')} /> : null}
                  {w.prefixes?.length ? <MetaLine label="Prefixes" value={w.prefixes.join(', ')} /> : null}
                  {w.suffixes?.length ? <MetaLine label="Suffixes" value={w.suffixes.join(', ')} /> : null}
                </SubSection>
              ) : null}

              {w.mnemonic ? (
                <SubSection title="Memory hook">
                  <View style={styles.mnemonic}>
                    <Icon name="lightbulb-on-outline" size={20} color={colors.warning} />
                    <AppText size={15} style={{ flex: 1, lineHeight: 22 }}>{w.mnemonic}</AppText>
                  </View>
                </SubSection>
              ) : null}

              {w.common_mistakes ? (
                <SubSection title="Common mistake">
                  <View style={styles.mistake}>
                    <Icon name="alert-outline" size={20} color={colors.error} />
                    <AppText size={15} color={colors.onSurfaceTertiary} style={{ flex: 1, lineHeight: 22 }}>{w.common_mistakes}</AppText>
                  </View>
                </SubSection>
              ) : null}
            </ExpandableGroup>
          ) : null}

          {d?.exams.length ? (
            <Section title="Appears in exams">
              <View style={styles.chipWrap}>
                {d.exams.map((e) => (
                  <Pressable key={e.slug} onPress={() => router.push(`/exam/${e.slug}`)} style={styles.examChip} testID={`exam-chip-${e.slug}`}>
                    <Icon name="trophy-outline" size={14} color={colors.onSurfaceTertiary} />
                    <AppText size={13} weight="medium" color={colors.onSurfaceTertiary}>{e.name}</AppText>
                  </Pressable>
                ))}
              </View>
            </Section>
          ) : null}
        </ScrollView>
      )}

      {/* sticky CTA */}
      {w ? (
        <View style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
          <Button label="Practice" icon="play" style={{ flex: 1 }} onPress={() => router.push(`/session?source=word&ref=${w.id}`)} testID="word-practice-button" />
          <Button label={d?.saved ? 'Saved' : 'Save'} variant="secondary" icon={d?.saved ? 'bookmark' : 'bookmark-outline'} style={{ flex: 1 }} onPress={toggleSave} testID="word-save-cta" />
        </View>
      ) : null}
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.section}>
      <AppText size={13} weight="medium" color={colors.muted} style={styles.sectionTitle}>{title.toUpperCase()}</AppText>
      {children}
    </View>
  );
}

function ExpandableGroup({
  title,
  children,
  testID,
}: {
  title: string;
  children: React.ReactNode;
  testID?: string;
}) {
  const styles = useStyles();
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <Animated.View layout={LinearTransition.duration(220)} style={styles.expandable}>
      <Pressable
        onPress={() => setOpen((o) => !o)}
        testID={testID}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={title}
        style={styles.expandableHead}
        hitSlop={6}
      >
        <AppText size={13} weight="medium" color={colors.muted} style={styles.expandableTitle}>
          {title.toUpperCase()}
        </AppText>
        <Icon name={open ? 'chevron-up' : 'chevron-down'} size={20} color={colors.muted} />
      </Pressable>
      {open ? <View style={{ marginTop: 10 }}>{children}</View> : null}
    </Animated.View>
  );
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={{ marginBottom: 14 }}>
      <AppText size={12} weight="medium" color={colors.onSurfaceTertiary} style={{ marginBottom: 6 }}>
        {title}
      </AppText>
      {children}
    </View>
  );
}

function MetaLine({ label, value }: { label: string; value: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: 'row', marginBottom: 6 }}>
      <AppText size={14} color={colors.muted} style={{ width: 76 }}>{label}</AppText>
      <AppText size={14} style={{ flex: 1 }}>{value}</AppText>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: t.spacing.lg, paddingBottom: t.spacing.sm },
  loading: { padding: t.spacing.xl, gap: t.spacing.md },
  body: { paddingHorizontal: t.spacing.xl, paddingTop: t.spacing.sm },
  headRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: t.colors.brandTertiary, alignSelf: 'flex-start', paddingHorizontal: t.spacing.md, paddingVertical: 6, borderRadius: t.radius.pill },
  masteryWrap: { marginTop: t.spacing.md, gap: t.spacing.sm },
  masteryTrack: { height: 6, borderRadius: 3, backgroundColor: t.colors.surfaceTertiary, overflow: 'hidden' },
  masteryFill: { height: '100%', backgroundColor: t.colors.brand, borderRadius: 3 },
  section: { marginTop: t.spacing.xl },
  expandable: {
    marginTop: t.spacing.xl,
    borderWidth: 1,
    borderColor: t.colors.border,
    backgroundColor: t.colors.surfaceSecondary,
    borderRadius: t.radius.md,
    padding: t.spacing.lg,
  },
  expandableHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 32,
  },
  expandableTitle: { letterSpacing: 0.5 },
  sectionTitle: { marginBottom: t.spacing.sm, letterSpacing: 0.5 },
  quote: { flexDirection: 'row', gap: t.spacing.sm, backgroundColor: t.colors.surfaceTertiary, borderRadius: t.radius.md, padding: t.spacing.lg },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.sm },
  wordChip: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: t.colors.brandTertiary, paddingHorizontal: t.spacing.lg, paddingVertical: 10, borderRadius: t.radius.pill },
  pronRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm, marginTop: t.spacing.md },
  pronBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: t.colors.brandTertiary, paddingHorizontal: t.spacing.lg, height: 40, borderRadius: t.radius.pill },
  pronMini: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: t.colors.border, alignItems: 'center', justifyContent: 'center' },
  coachBox: { backgroundColor: t.colors.surfaceTertiary, borderRadius: t.radius.md, padding: t.spacing.lg },
  coachRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  coachCta: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, backgroundColor: t.colors.surfaceSecondary, borderWidth: 1, borderColor: t.colors.border, borderRadius: t.radius.md, padding: t.spacing.lg },
  examChip: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: t.colors.surfaceTertiary, paddingHorizontal: t.spacing.md, paddingVertical: 8, borderRadius: t.radius.pill },
  mnemonic: { flexDirection: 'row', gap: t.spacing.sm, backgroundColor: '#FBF6EC', borderRadius: t.radius.md, padding: t.spacing.lg },
  mistake: { flexDirection: 'row', gap: t.spacing.sm, backgroundColor: '#FBF0F0', borderRadius: t.radius.md, padding: t.spacing.lg },
  cta: { position: 'absolute', left: 0, right: 0, bottom: 0, flexDirection: 'row', gap: t.spacing.md, paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md, backgroundColor: t.colors.surface, borderTopWidth: 1, borderTopColor: t.colors.divider },
}));
