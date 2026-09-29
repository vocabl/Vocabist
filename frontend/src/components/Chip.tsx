import React from 'react';
import { Pressable } from 'react-native';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from './AppText';

type Props = {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  testID?: string;
};

export function Chip({ label, selected, onPress, testID }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[styles.chip, selected ? styles.selected : styles.unselected]}
    >
      <AppText
        weight="medium"
        size={14}
        color={selected ? colors.onSurfaceInverse : colors.onSurfaceTertiary}
      >
        {label}
      </AppText>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  chip: {
    height: 36,
    paddingHorizontal: t.spacing.lg,
    borderRadius: t.radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    flexShrink: 0,
  },
  selected: { backgroundColor: t.colors.surfaceInverse, borderColor: t.colors.surfaceInverse },
  unselected: { backgroundColor: t.colors.surface, borderColor: t.colors.border },
}));
