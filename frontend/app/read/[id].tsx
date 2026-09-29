import React, { useState } from 'react';
import { View, ScrollView, Pressable, Modal, ActivityIndicator, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { makeStyles, useTheme, fontFamily } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { CefrBadge } from '@/src/components/CefrBadge';
import { Skeleton } from '@/src/components/Skeleton';
import { useToast } from '@/src/components/Toast';
import { api, API } from '@/src/api/client';
import { playAudioUrl } from '@/src/utils/audio';

type Article = { id: string; title: string; level: string; minutes: number; body: string };
type Lookup = { in_bank: boolean; found?: boolean; id?: string; headword: string; phonetic?: string; simple_definition?: string | null; example?: string; cefr?: string; saved?: boolean };

export default function Reader() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();

  const q = useQuery({ queryKey: ['article', id], queryFn: () => api<{ article: Article }>(`/articles/${id}`) });
  const a = q.data?.article;

  const [active, setActive] = useState<string | null>(null);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [looking, setLooking] = useState(false);
  const [saving, setSaving] = useState(false);

  const onWord = async (raw: string) => {
    const word = raw.toLowerCase().replace(/[^a-z]/g, '');
    if (word.length < 3) return;
    setActive(word);
    setLookup(null);
    setLooking(true);
    try {
      const res = await api<Lookup>(`/lookup?word=${word}`);
      setLookup(res);
    } catch {
      setLookup({ in_bank: false, found: false, headword: word, simple_definition: null });
    } finally {
      setLooking(false);
    }
  };

  const listen = async () => {
    if (!lookup) return;
    try {
      let wid = lookup.id;
      if (!wid) wid = (await api<{ id: string }>('/words/import', { method: 'POST', body: { headword: lookup.headword } })).id;
      const audio = await api<{ us_url?: string; uk_url?: string; tts_url?: string }>(`/words/${wid}/audio`);
      const url = audio.us_url || audio.uk_url || audio.tts_url;
      if (url) await playAudioUrl(url.startsWith('http') ? url : `${API}${url}`);
    } catch { toast.show('Audio unavailable', 'error'); }
  };

  const save = async () => {
    if (!lookup) return;
    setSaving(true);
    try {
      let wid = lookup.id;
      if (!wid) wid = (await api<{ id: string }>('/words/import', { method: 'POST', body: { headword: lookup.headword } })).id;
      await api(`/words/${wid}/save`, { method: 'POST' });
      qc.invalidateQueries({ queryKey: ['saved'] });
      toast.show('Saved to your words', 'success');
      setActive(null);
    } catch { toast.show('Could not save', 'error'); }
    finally { setSaving(false); }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable testID="reader-back" onPress={() => router.back()} hitSlop={10}>
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText size={13} color={colors.muted}>Tap a word</AppText>
        <View style={{ width: 28 }} />
      </View>

      {q.isLoading || !a ? (
        <View style={{ padding: 24, gap: 12 }}>{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} height={18} />)}</View>
      ) : (
        <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 32 }]} showsVerticalScrollIndicator={false}>
          <View style={styles.titleRow}>
            <CefrBadge level={a.level} small />
            <AppText size={12} color={colors.muted}>{a.minutes} min read</AppText>
          </View>
          <AppText weight="semibold" size={26} style={{ marginTop: 10, lineHeight: 32 }}>{a.title}</AppText>
          <Text style={styles.article}>
            {a.body.split(/(\s+)/).map((tok, i) =>
              /\S/.test(tok) ? (
                <Text key={i} onPress={() => onWord(tok)} style={styles.word}>{tok}</Text>
              ) : (
                <Text key={i}>{tok}</Text>
              )
            )}
          </Text>
        </ScrollView>
      )}

      <Modal visible={!!active} transparent animationType="slide" onRequestClose={() => setActive(null)}>
        <Pressable style={styles.backdrop} onPress={() => setActive(null)} />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + 20 }]}>
          <View style={styles.handle} />
          {looking ? (
            <View style={{ paddingVertical: 30, alignItems: 'center' }}><ActivityIndicator color={colors.brand} /></View>
          ) : lookup && (lookup.simple_definition || lookup.found !== false) ? (
            <View>
              <View style={styles.sheetHead}>
                <AppText weight="semibold" size={26}>{lookup.headword}</AppText>
                {lookup.cefr ? <CefrBadge level={lookup.cefr} /> : null}
              </View>
              {lookup.phonetic ? <AppText size={15} color={colors.muted} style={{ marginTop: 2 }}>{lookup.phonetic}</AppText> : null}
              <AppText size={17} style={{ marginTop: 12, lineHeight: 24 }}>{lookup.simple_definition}</AppText>
              {lookup.example ? <AppText size={14} color={colors.onSurfaceTertiary} style={{ marginTop: 8, fontStyle: 'italic' }}>“{lookup.example}”</AppText> : null}
              <View style={styles.sheetActions}>
                <Button label="Listen" variant="secondary" icon="volume-high" style={{ flex: 1 }} onPress={listen} testID="reader-listen" />
                <Button label="Save word" icon="bookmark-outline" style={{ flex: 1 }} loading={saving} onPress={save} testID="reader-save" />
              </View>
            </View>
          ) : (
            <View style={{ paddingVertical: 24, alignItems: 'center' }}>
              <AppText size={16} color={colors.muted}>No definition found for “{active}”.</AppText>
            </View>
          )}
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: t.spacing.lg, paddingBottom: t.spacing.sm },
  body: { paddingHorizontal: t.spacing.xl, paddingTop: t.spacing.sm },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  article: { fontFamily: fontFamily.regular, fontSize: 18, lineHeight: 31, color: t.colors.onSurface, marginTop: t.spacing.xl },
  word: { color: t.colors.onSurface },
  backdrop: { flex: 1, backgroundColor: 'rgba(26,26,24,0.4)' },
  sheet: { backgroundColor: t.colors.surfaceSecondary, borderTopLeftRadius: t.radius.lg, borderTopRightRadius: t.radius.lg, paddingHorizontal: t.spacing.xl, paddingTop: t.spacing.md },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: t.colors.borderStrong, alignSelf: 'center', marginBottom: t.spacing.lg },
  sheetHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  sheetActions: { flexDirection: 'row', gap: t.spacing.md, marginTop: t.spacing.xl },
}));
