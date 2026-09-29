import React from 'react';
import { Pressable, ActivityIndicator, View, ViewStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from './AppText';
import { Icon } from './Icon';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

type Props = {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  icon?: React.ComponentProps<typeof Icon>['name'];
  style?: ViewStyle;
  testID?: string;
  size?: 'md' | 'lg';
};

export function Button({
  label, onPress, variant = 'primary', loading, disabled, icon, style, testID, size = 'lg',
}: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const isDisabled = disabled || loading;

  const bg: Record<Variant, string> = {
    primary: colors.brand,
    secondary: colors.brandTertiary,
    ghost: 'transparent',
    danger: colors.error,
  };
  const fg: Record<Variant, string> = {
    primary: colors.onBrand,
    secondary: colors.onBrandTertiary,
    ghost: colors.brand,
    danger: colors.onError,
  };

  const handlePress = () => {
    if (isDisabled) return;
    if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    onPress?.();
  };

  return (
    <Pressable
      testID={testID}
      onPress={handlePress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        size === 'md' && styles.md,
        { backgroundColor: bg[variant] },
        variant === 'ghost' && styles.ghostBorder,
        pressed && !isDisabled && styles.pressed,
        isDisabled && styles.disabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg[variant]} />
      ) : (
        <View style={styles.row}>
          {icon ? <Icon name={icon} size={20} color={fg[variant]} /> : null}
          <AppText weight="medium" size={16} color={fg[variant]}>
            {label}
          </AppText>
        </View>
      )}
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  base: {
    height: 56,
    borderRadius: t.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: t.spacing.xl,
    flexDirection: 'row',
  },
  md: { height: 46, borderRadius: t.radius.sm, paddingHorizontal: t.spacing.lg },
  ghostBorder: { borderWidth: 1, borderColor: t.colors.borderStrong },
  row: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  pressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  disabled: { opacity: 0.45 },
}));
