import React, { useState } from 'react';
import { View, ScrollView, Pressable, TextInput, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import * as DocumentPicker from 'expo-document-picker';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { useToast } from '@/src/components/Toast';
import { api, API, loadToken } from '@/src/api/client';

type Item = { headword: string; in_bank: boolean; id: string | null; simple_definition?: string; cefr?: string };
type Result = { known: Item[]; learning: Item[]; new: Item[]; counts: { known: number; learning: number; new: number } };

export default function ImportScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();

  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const applyResult = (r: Result) => {
    setResult(r);
    setSelected(new Set(r.new.map((n) => n.headword)));
  };

  const extractText = async () => {
    if (text.trim().length < 10) { toast.show('Paste a bit more text first.', 'error'); return; }
    setLoading(true);
    try {
      applyResult(await api<Result>('/extract', { method: 'POST', body: { text } }));
    } catch { toast.show('Could not extract words', 'error'); }
    finally { setLoading(false); }
  };

  const pickPdf = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      setLoading(true);
      const form = new FormData();
      // @ts-ignore react-native FormData file
      form.append('file', { uri: asset.uri, name: asset.name || 'doc.pdf', type: 'application/pdf' });
      const token = await loadToken();
      const r = await fetch(`${API}/extract-pdf`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!r.ok) throw new Error();
      applyResult(await r.json());
    } catch { toast.show('Could not read that PDF', 'error'); }
    finally { setLoading(false); }
  };

  const toggle = (hw: string) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(hw)) n.delete(hw); else n.add(hw);
      return n;
    });
  };

  const learn = () => {
    const list = Array.from(selected).slice(0, 15);
    if (!list.length) { toast.show('Select some words to learn.', 'error'); return; }
    router.push(`/session?source=list&ref=${encodeURIComponent(list.join(','))}`);
  };

  const reset = () => { setResult(null); setText(''); setSelected(new Set()); };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <Pressable testID="import-back" onPress={() => router.back()} hitSlop={10}>
          <Icon name="chevron-left" size={28} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={20}>Learn From Anything</AppText>
        <View style={{ width: 28 }} />
      </View>

      {!result ? (
        <KeyboardAwareScrollView bottomOffset={20} contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          <AppText size={15} color={colors.muted} style={{ lineHeight: 21 }}>Paste an article, song, or notes — or upload a PDF. We'll find the vocabulary worth learning.</AppText>
          <TextInput
            testID="import-text-input"
            value={text}
            onChangeText={setText}
            placeholder="Paste your text here…"
            placeholderTextColor={colors.muted}
            multiline
            style={styles.textArea}
            textAlignVertical="top"
          />
          <Button label="Find words" icon="text-search" loading={loading} onPress={extractText} testID="extract-text-button" />
          <View style={styles.orRow}><View style={styles.line} /><AppText size={13} color={colors.muted}>or</AppText><View style={styles.line} /></View>
          <Button label="Upload a PDF" variant="ghost" icon="file-pdf-box" onPress={pickPdf} testID="upload-pdf-button" />
        </KeyboardAwareScrollView>
      ) : (
        <View style={{ flex: 1 }}>
          <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 96 }]} showsVerticalScrollIndicator={false}>
            <View style={styles.summary}>
              <Stat label="New" value={result.counts.new} color={colors.brand} styles={styles} />
              <Stat label="Learning" value={result.counts.learning} color={colors.warning} styles={styles} />
              <Stat label="Known" value={result.counts.known} color={colors.success} styles={styles} />
            </View>

            <AppText weight="medium" size={16} style={styles.section}>New words to learn</AppText>
            <AppText size={13} color={colors.muted} style={{ marginBottom: 12 }}>Tap to select the ones you want.</AppText>
            <View style={styles.chipWrap}>
              {result.new.map((it) => {
                const sel = selected.has(it.headword);
                return (
                  <Pressable key={it.headword} testID={`new-word-${it.headword}`} onPress={() => toggle(it.headword)} style={[styles.wordChip, sel ? styles.chipSel : styles.chipUnsel]}>
                    <Icon name={sel ? 'check-circle' : 'plus-circle-outline'} size={16} color={sel ? colors.onBrand : colors.muted} />
                    <AppText size={14} weight="medium" color={sel ? colors.onBrand : colors.onSurface}>{it.headword}</AppText>
                  </Pressable>
                );
              })}
              {result.new.length === 0 ? <AppText size={14} color={colors.muted}>No new words found — you know them all!</AppText> : null}
            </View>

            {result.learning.length ? (
              <>
                <AppText weight="medium" size={16} style={styles.section}>Still learning</AppText>
                <View style={styles.chipWrap}>
                  {result.learning.map((it) => (
                    <View key={it.headword} style={[styles.wordChip, styles.chipUnsel]}>
                      <AppText size={14} weight="medium" color={colors.onSurfaceTertiary}>{it.headword}</AppText>
                    </View>
                  ))}
                </View>
              </>
            ) : null}

            <Pressable onPress={reset} style={styles.resetRow} testID="import-reset">
              <Icon name="refresh" size={16} color={colors.brand} />
              <AppText size={14} weight="medium" color={colors.brand}>Try another text</AppText>
            </Pressable>
          </ScrollView>

          <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
            <Button label={`Learn ${selected.size} new word${selected.size === 1 ? '' : 's'}`} icon="school" onPress={learn} disabled={selected.size === 0} testID="learn-new-words-button" />
          </View>
        </View>
      )}

      {loading && result ? <View style={styles.loadingOverlay}><ActivityIndicator color={colors.brand} /></View> : null}
    </View>
  );
}

function Stat({ label, value, color, styles }: { label: string; value: number; color: string; styles: any }) {
  return (
    <View style={styles.stat}>
      <AppText weight="semibold" size={24} color={color}>{value}</AppText>
      <AppText size={12} color="#73736E">{label}</AppText>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: t.spacing.lg, paddingBottom: t.spacing.sm },
  scroll: { paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md, gap: t.spacing.lg },
  textArea: { minHeight: 200, backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border, padding: t.spacing.lg, fontFamily: t.fontFamily.regular, fontSize: 16, color: t.colors.onSurface },
  orRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  line: { flex: 1, height: 1, backgroundColor: t.colors.divider },
  summary: { flexDirection: 'row', gap: t.spacing.md },
  stat: { flex: 1, alignItems: 'center', backgroundColor: t.colors.surfaceSecondary, borderRadius: t.radius.md, borderWidth: 1, borderColor: t.colors.border, paddingVertical: t.spacing.lg },
  section: { marginTop: t.spacing.xl },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: t.spacing.sm },
  wordChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: t.spacing.md, paddingVertical: 9, borderRadius: t.radius.pill, borderWidth: 1 },
  chipSel: { backgroundColor: t.colors.brand, borderColor: t.colors.brand },
  chipUnsel: { backgroundColor: t.colors.surfaceSecondary, borderColor: t.colors.border },
  resetRow: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'center', marginTop: t.spacing.xxl, padding: t.spacing.sm },
  footer: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: t.spacing.lg, paddingTop: t.spacing.md, backgroundColor: t.colors.surface, borderTopWidth: 1, borderTopColor: t.colors.divider },
  loadingOverlay: { ...({ position: 'absolute' } as any), top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(253,253,251,0.6)', alignItems: 'center', justifyContent: 'center' },
}));
