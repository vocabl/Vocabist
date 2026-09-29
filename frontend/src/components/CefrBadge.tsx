import React from 'react';
import { View } from 'react-native';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from './AppText';

const CEFR_COLORS: Record<string, string> = {
  A1: '#5B8A72', A2: '#5B8A72',
  B1: '#4A7C59', B2: '#4A7C59',
  C1: '#2E5C3E', C2: '#2E5C3E',
};

export function CefrBadge({ level, small }: { level?: string | null; small?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  if (!level) return null;
  return (
    <View style={[styles.badge, small && styles.small, { backgroundColor: colors.brandTertiary }]}>
      <AppText weight="semibold" size={small ? 11 : 12} color={CEFR_COLORS[level] ?? colors.onBrandTertiary}>
        {level}
      </AppText>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  badge: {
    paddingHorizontal: t.spacing.sm,
    paddingVertical: 3,
    borderRadius: t.radius.sm,
    alignSelf: 'flex-start',
  },
  small: { paddingHorizontal: 6, paddingVertical: 2 },
}));
