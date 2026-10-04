import React from 'react';
import { View, ScrollView, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { adminApi } from '@/src/api/admin';
import { AdminHeader, Loading, Tag, adminStyles } from '@/src/components/admin/AdminUI';

export default function AdminRouting() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey: ['admin-routing'], queryFn: adminApi.routing });
  const routes = q.data?.routing ?? [];

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}>
      <AdminHeader title="Task Routing" subtitle="Primary → fallback chain per task" />
      <AppText size={12} color={c.muted} style={{ marginBottom: 4 }}>
        Each task routes to its primary model, then falls back on timeout / 429 / 5xx / malformed output. The gateway validates capability compatibility.
      </AppText>
      {q.isLoading ? <Loading /> : routes.map((r) => (
        <Card key={r.task} padded style={{ gap: 8 }} testID={`route-${r.task}`}>
          <View style={rowStyles.head}>
            <AppText weight="semibold" size={14}>{r.task.replace(/_/g, ' ')}</AppText>
            <Tag label={r.required_capability} tone="brand" />
          </View>
          <View style={rowStyles.chain}>
            {r.chain.map((m, i) => (
              <View key={m + i} style={rowStyles.chainItem}>
                <View style={[rowStyles.pill, i === 0 && rowStyles.primaryPill, r.invalid_models.includes(m) && rowStyles.invalidPill]}>
                  <AppText size={11} weight="medium" color={i === 0 ? '#fff' : c.onSurfaceTertiary}>
                    {i === 0 ? '★ ' : ''}{m}
                  </AppText>
                </View>
                {i < r.chain.length - 1 ? <Icon name="arrow-right" size={14} color={c.muted} /> : null}
              </View>
            ))}
          </View>
          {r.invalid_models.length > 0 ? (
            <AppText size={11} color={c.error}>Invalid for this task: {r.invalid_models.join(', ')}</AppText>
          ) : null}
          {r.is_override ? <AppText size={10} color={c.muted}>custom override</AppText> : null}
        </Card>
      ))}
    </ScrollView>
  );
}

const rowStyles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  chain: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 6 },
  chainItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  pill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: '#D6D6D2', backgroundColor: '#F4F4F2' },
  primaryPill: { backgroundColor: '#4A7C59', borderColor: '#4A7C59' },
  invalidPill: { borderColor: '#B54D4D', backgroundColor: '#B54D4D22' },
});
