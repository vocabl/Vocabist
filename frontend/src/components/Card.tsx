import React from 'react';
import { View, ViewStyle, Pressable } from 'react-native';
import { makeStyles } from '@/src/theme';

type Props = {
  children: React.ReactNode;
  style?: ViewStyle;
  onPress?: () => void;
  testID?: string;
  padded?: boolean;
};

export function Card({ children, style, onPress, testID, padded = true }: Props) {
  const styles = useStyles();
  if (onPress) {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        style={({ pressed }) => [styles.card, padded && styles.padded, style, pressed && styles.pressed]}
      >
        {children}
      </Pressable>
    );
  }
  return (
    <View testID={testID} style={[styles.card, padded && styles.padded, style]}>
      {children}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  card: {
    backgroundColor: t.colors.surfaceSecondary,
    borderRadius: t.radius.lg,
    borderWidth: 1,
    borderColor: t.colors.border,
    ...t.shadow.sm,
  },
  padded: { padding: t.spacing.lg },
  pressed: { opacity: 0.9, transform: [{ scale: 0.995 }] },
}));
