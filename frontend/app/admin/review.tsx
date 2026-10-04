import React, { useState } from 'react';
import { View, ScrollView, Pressable, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Input } from '@/src/components/Input';
import { Icon } from '@/src/components/Icon';
import { adminApi, ReviewWord } from '@/src/api/admin';
import { AdminHeader, Loading, Tag, StatusBadge, adminStyles } from '@/src/components/admin/AdminUI';

const FIELD_BUTTONS: { field: string; label: string }[] = [
  { field: 'definition', label: 'Definition' },
  { field: 'examples', label: 'Example' },
  { field: 'synonyms', label: 'Synonyms' },
  { field: 'antonyms', label: 'Antonyms' },
  { field: 'cefr', label: 'CEFR' },
  { field: 'word_family', label: 'Word family' },
  { field: 'memory_hook', label: 'Memory hook' },
  { field: 'common_mistake', label: 'Mistake' },
];

export default function AdminReview() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<Record<string, string>>({});

  const q = useQuery({ queryKey: ['admin-review', search], queryFn: () => adminApi.reviewQueue(search) });
  const words = q.data?.words ?? [];

  const act = async (id: string, fn: () => Promise<any>, okMsg: string) => {
    setBusy(id);
    try { await fn(); setMsg((m) => ({ ...m, [id]: okMsg })); await q.refetch(); }
    catch (e: any) { setMsg((m) => ({ ...m, [id]: e?.message || 'Failed' })); }
    finally { setBusy(null); }
  };

  const regen = async (id: string, field: string) => {
    setBusy(id + ':' + field);
    try { await adminApi.regenerate(id, field); setMsg((m) => ({ ...m, [id]: `Regenerated ${field}` })); await q.refetch(); }
    catch (e: any) { setMsg((m) => ({ ...m, [id]: e?.message || 'Regen failed' })); }
    finally { setBusy(null); }
  };

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}>
      <AdminHeader title="Review Queue" subtitle={`${q.data?.total ?? 0} words awaiting review`} />
      <Input icon="magnify" placeholder="Search headword" value={search} onChangeText={setSearch} testID="review-search" />

      {q.isLoading ? <Loading /> : words.length === 0 ? (
        <View style={rStyles.empty}>
          <Icon name="check-circle-outline" size={28} color={c.success} />
          <AppText size={13} color={c.muted} style={{ marginTop: 8, textAlign: 'center' }}>
            Nothing in the review queue. AI-generated words land here before publishing.
          </AppText>
        </View>
      ) : words.map((w: ReviewWord) => (
        <Card key={w.id} padded style={{ gap: 8 }} testID={`review-${w.id}`}>
          <Pressable onPress={() => setOpen(open === w.id ? null : w.id)} style={rStyles.head}>
            <View style={{ flex: 1 }}>
              <AppText weight="semibold" size={16}>{w.headword}</AppText>
              <AppText size={12} color={c.muted}>{w.part_of_speech || '—'} · {w.cefr || 'no CEFR'}</AppText>
            </View>
            <StatusBadge status={w.status || 'REVIEW'} />
            <Icon name={open === w.id ? 'chevron-up' : 'chevron-down'} size={20} color={c.muted} />
          </Pressable>

          {w.simple_definition ? <AppText size={13} color={c.onSurfaceTertiary}>{w.simple_definition}</AppText> : null}

          {open === w.id && (
            <View style={{ gap: 10 }}>
              {w.example ? <AppText size={12} color={c.muted} style={{ fontStyle: 'italic' }}>“{w.example}”</AppText> : null}
              {(w.synonyms?.length || w.antonyms?.length) ? (
                <View style={rStyles.tags}>
                  {w.synonyms?.map((s) => <Tag key={'s' + s} label={s} tone="brand" />)}
                  {w.antonyms?.map((a) => <Tag key={'a' + a} label={a} tone="warn" />)}
                </View>
              ) : null}
              {w.mnemonic ? <AppText size={12} color={c.muted}>Hook: {w.mnemonic}</AppText> : null}
              {w.common_mistakes ? <AppText size={12} color={c.muted}>Mistake: {w.common_mistakes}</AppText> : null}

              <AppText size={12} weight="medium" color={c.onSurfaceTertiary}>Regenerate field</AppText>
              <View style={rStyles.tags}>
                {FIELD_BUTTONS.map((f) => (
                  <Pressable key={f.field} onPress={() => regen(w.id, f.field)} disabled={!!busy} style={rStyles.fieldBtn} testID={`regen-${w.id}-${f.field}`}>
                    <AppText size={11} color={c.brand}>{busy === w.id + ':' + f.field ? '…' : f.label}</AppText>
                  </Pressable>
                ))}
              </View>

              <View style={rStyles.actions}>
                <Pressable onPress={() => act(w.id, () => adminApi.publish(w.id), 'Published')} disabled={!!busy} style={[rStyles.actionBtn, { backgroundColor: c.brand }]} testID={`publish-${w.id}`}>
                  <Icon name="check" size={16} color="#fff" />
                  <AppText size={13} weight="medium" color="#fff">Publish</AppText>
                </Pressable>
                <Pressable onPress={() => act(w.id, () => adminApi.reject(w.id), 'Rejected')} disabled={!!busy} style={[rStyles.actionBtn, rStyles.reject]} testID={`reject-${w.id}`}>
                  <Icon name="close" size={16} color={c.error} />
                  <AppText size={13} weight="medium" color={c.error}>Reject</AppText>
                </Pressable>
              </View>
            </View>
          )}
          {msg[w.id] ? <AppText size={11} color={c.muted}>{msg[w.id]}</AppText> : null}
        </Card>
      ))}
    </ScrollView>
  );
}

const rStyles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  fieldBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: '#4A7C5955', backgroundColor: '#E7F0E9' },
  actions: { flexDirection: 'row', gap: 8, marginTop: 4 },
  actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 10 },
  reject: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#B54D4D55' },
  empty: { alignItems: 'center', paddingVertical: 40 },
});
