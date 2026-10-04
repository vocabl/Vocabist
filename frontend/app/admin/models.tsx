import React, { useState } from 'react';
import { View, ScrollView, Switch, Pressable, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Card } from '@/src/components/Card';
import { Icon } from '@/src/components/Icon';
import { adminApi, ModelInfo } from '@/src/api/admin';
import { AdminHeader, Loading, StatusBadge, Tag, adminStyles } from '@/src/components/admin/AdminUI';

export default function AdminModels() {
  const styles = adminStyles();
  const { colors: c } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey: ['admin-models'], queryFn: adminApi.models });
  const [busy, setBusy] = useState<string | null>(null);
  const [pingResult, setPingResult] = useState<Record<string, string>>({});

  const toggle = async (m: ModelInfo) => {
    setBusy(m.key);
    try { await adminApi.toggleModel(m.key, !m.enabled); await q.refetch(); } finally { setBusy(null); }
  };
  const ping = async (m: ModelInfo) => {
    setBusy(m.key + ':ping');
    try {
      const r = await adminApi.pingModel(m.key);
      setPingResult((p) => ({ ...p, [m.key]: r.status === 'AVAILABLE' ? `OK ${r.latency_ms}ms` : (r.error || 'failed') }));
      await q.refetch();
    } finally { setBusy(null); }
  };

  const models = q.data?.models ?? [];

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 }]}>
      <AdminHeader title="Providers & Models" subtitle="NVIDIA + Emergent" />
      {q.isLoading ? <Loading /> : models.map((m) => (
        <Card key={m.key} padded style={{ gap: 8 }} testID={`model-${m.key}`}>
          <View style={rowStyles.head}>
            <View style={{ flex: 1 }}>
              <AppText weight="semibold" size={15}>{m.display_name}</AppText>
              <AppText size={11} color={c.muted}>{m.model_id}</AppText>
            </View>
            <StatusBadge status={m.status} />
          </View>

          <View style={rowStyles.tags}>
            <Tag label={m.provider} tone="brand" />
            <Tag label={m.modality} />
            {m.capabilities.map((cap) => <Tag key={cap} label={cap} />)}
          </View>

          {m.notes ? <AppText size={12} color={c.onSurfaceTertiary}>{m.notes}</AppText> : null}

          <View style={rowStyles.footer}>
            <View style={rowStyles.toggle}>
              <AppText size={13} color={c.muted}>Enabled</AppText>
              <Switch
                testID={`toggle-${m.key}`}
                value={m.enabled}
                onValueChange={() => toggle(m)}
                disabled={busy === m.key}
                trackColor={{ true: c.brand, false: c.borderStrong }}
                thumbColor="#fff"
              />
            </View>
            <Pressable onPress={() => ping(m)} disabled={!!busy} style={rowStyles.pingBtn} testID={`ping-${m.key}`}>
              <Icon name="access-point" size={16} color={c.brand} />
              <AppText size={12} weight="medium" color={c.brand}>
                {busy === m.key + ':ping' ? 'Pinging…' : 'Ping'}
              </AppText>
            </Pressable>
          </View>
          {pingResult[m.key] ? <AppText size={11} color={c.muted}>Last ping: {pingResult[m.key]}</AppText> : null}
          {(m.failure_count ?? 0) > 0 ? <AppText size={11} color={c.error}>Failures: {m.failure_count}</AppText> : null}
        </Card>
      ))}
    </ScrollView>
  );
}

const rowStyles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pingBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: '#4A7C5955' },
});
