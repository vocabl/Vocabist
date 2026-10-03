import React from 'react';
import { View, Pressable } from 'react-native';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from './AppText';
import { Icon } from './Icon';
import { CefrBadge } from './CefrBadge';

export type WordRowStatus = 'NEW' | 'SEEN' | 'LEARNING' | 'RECALLING' | 'MASTERED' | string;

export type WordRowItem = {
  id: string;
  headword: string;
  simple_definition?: string | null;
  cefr?: string | null;
  part_of_speech?: string | null;
  saved?: boolean;
  // optional, backend-provided; never fabricated client-side
  status?: WordRowStatus | null;
  mastery_score?: number | null;
  overdue_days?: number | null;
};

type Props = {
  item: WordRowItem;
  onPress: () => void;
  onToggleSave?: () => void;
  trailing?: 'chevron' | 'save' | 'none';
  testID?: string;
};

/**
 * Shared vocabulary row used across Discover, Saved and Review screens.
 * Shows a compact header (headword + CEFR + optional mastery/status), a
 * truncated simple definition and either a save toggle or a chevron.
 *
 * No status or mastery value is invented here — the row only renders those
 * if the backend returned them for this item.
 */
export function WordRow({ item, onPress, onToggleSave, trailing, testID }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const effectiveTrailing = trailing ?? (onToggleSave ? 'save' : 'chevron');

  const statusTint = statusColor(item.status, colors);

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={item.headword}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
    >
      <View style={{ flex: 1 }}>
        <View style={styles.head}>
          <AppText weight="medium" size={17} numberOfLines={1} style={{ flexShrink: 1 }}>
            {item.headword}
          </AppText>
          {item.cefr ? <CefrBadge level={item.cefr} small /> : null}
          {item.status && statusTint ? (
            <View style={[styles.statusDot, { backgroundColor: statusTint }]} accessible={false} />
          ) : null}
        </View>
        {item.simple_definition ? (
          <AppText size={14} color={colors.muted} numberOfLines={1} style={{ marginTop: 3 }}>
            {item.simple_definition}
          </AppText>
        ) : null}
        {typeof item.mastery_score === 'number' && item.status ? (
          <AppText size={12} color={colors.onSurfaceTertiary} style={{ marginTop: 4 }}>
            {friendlyStatus(item.status)} · {Math.round(item.mastery_score)}% mastery
            {typeof item.overdue_days === 'number' && item.overdue_days > 0
              ? ` · ${item.overdue_days}d overdue`
              : ''}
          </AppText>
        ) : null}
      </View>

      {effectiveTrailing === 'save' && onToggleSave ? (
        <Pressable
          testID={`save-word-${item.id}`}
          onPress={onToggleSave}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel={item.saved ? 'Unsave word' : 'Save word'}
          style={styles.saveBtn}
        >
          <Icon
            name={item.saved ? 'bookmark' : 'bookmark-outline'}
            size={22}
            color={item.saved ? colors.brand : colors.muted}
          />
        </Pressable>
      ) : effectiveTrailing === 'chevron' ? (
        <Icon name="chevron-right" size={20} color={colors.muted} />
      ) : null}
    </Pressable>
  );
}

function friendlyStatus(status: string): string {
  switch (status.toUpperCase()) {
    case 'NEW': return 'New';
    case 'SEEN': return 'Just met';
    case 'LEARNING': return 'Learning';
    case 'RECALLING': return 'Recalling';
    case 'MASTERED': return 'Mastered';
    default: return status;
  }
}

function statusColor(status: string | null | undefined, colors: ReturnType<typeof useTheme>['colors']): string | null {
  if (!status) return null;
  switch (status.toUpperCase()) {
    case 'MASTERED': return colors.success;
    case 'RECALLING': return colors.warning;
    case 'LEARNING': return colors.brand;
    case 'SEEN': return colors.onSurfaceTertiary;
    case 'NEW': return colors.muted;
    default: return null;
  }
}

const useStyles = makeStyles((t) => ({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: t.spacing.md,
    backgroundColor: t.colors.surfaceSecondary,
    borderRadius: t.radius.lg,
    borderWidth: 1,
    borderColor: t.colors.border,
    paddingVertical: t.spacing.lg,
    paddingHorizontal: t.spacing.lg,
    minHeight: 64,
    ...t.shadow.sm,
  },
  pressed: { opacity: 0.9, transform: [{ scale: 0.995 }] },
  head: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm, flexWrap: 'wrap' },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  saveBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', marginRight: -8 },
}));
