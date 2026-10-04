import React from 'react';
import { View, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { makeStyles, useTheme, colors } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Icon } from '@/src/components/Icon';

// Status → color for model/provider health + job + lifecycle badges.
const STATUS_COLOR: Record<string, string> = {
  AVAILABLE: '#3E7B51',
  UNAVAILABLE: '#B54D4D',
  UNKNOWN: '#73736E',
  DISABLED: '#B8B8B3',
  RUNNING: '#D19036',
  QUEUED: '#73736E',
  COMPLETED: '#3E7B51',
  PARTIAL: '#D19036',
  FAILED: '#B54D4D',
  CANCELLED: '#B8B8B3',
  PUBLISHED: '#3E7B51',
  REVIEW: '#D19036',
  ARCHIVED: '#B8B8B3',
  DRAFT: '#73736E',
};

export function StatusBadge({ status }: { status: string }) {
  const bg = STATUS_COLOR[status] ?? '#73736E';
  return (
    <View style={[badgeStyles.badge, { backgroundColor: bg + '22', borderColor: bg + '55' }]}>
      <View style={[badgeStyles.dot, { backgroundColor: bg }]} />
      <AppText size={11} weight="medium" color={bg}>{status}</AppText>
    </View>
  );
}

export function Tag({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'brand' | 'warn' }) {
  const map = { neutral: '#73736E', brand: '#4A7C59', warn: '#D19036' };
  const col = map[tone];
  return (
    <View style={[badgeStyles.tag, { borderColor: col + '55', backgroundColor: col + '14' }]}>
      <AppText size={10} weight="medium" color={col}>{label}</AppText>
    </View>
  );
}

export function AdminHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const router = useRouter();
  const { colors: c } = useTheme();
  return (
    <View style={headerStyles.wrap}>
      <Pressable onPress={() => router.back()} hitSlop={12} style={headerStyles.back} testID="admin-back">
        <Icon name="arrow-left" size={22} color={c.onSurface} />
      </Pressable>
      <View style={{ flex: 1 }}>
        <AppText weight="semibold" size={20}>{title}</AppText>
        {subtitle ? <AppText size={12} color={c.muted}>{subtitle}</AppText> : null}
      </View>
    </View>
  );
}

export function Loading() {
  const { colors: c } = useTheme();
  return (
    <View style={{ paddingVertical: 48, alignItems: 'center' }}>
      <ActivityIndicator color={c.brand} />
    </View>
  );
}

export function KeyValue({ k, v, color }: { k: string; v: string | number; color?: string }) {
  const { colors: c } = useTheme();
  return (
    <View style={kvStyles.row}>
      <AppText size={13} color={c.muted}>{k}</AppText>
      <AppText size={13} weight="medium" color={color}>{String(v)}</AppText>
    </View>
  );
}

const badgeStyles = StyleSheet.create({
  badge: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, borderWidth: 1 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  tag: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 1 },
});

const headerStyles = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 },
  back: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceTertiary },
});

const kvStyles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.divider },
});

export const adminStyles = makeStyles((t) => ({
  scroll: { flex: 1, backgroundColor: t.colors.surface },
  content: { paddingHorizontal: t.spacing.lg, gap: t.spacing.md },
  sectionTitle: { marginTop: t.spacing.sm, marginBottom: 4 },
}));
