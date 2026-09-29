import React, { useState } from 'react';
import { View, TextInput, TextInputProps, Pressable } from 'react-native';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from './AppText';
import { Icon } from './Icon';

type Props = TextInputProps & {
  label?: string;
  icon?: React.ComponentProps<typeof Icon>['name'];
  error?: string;
  isPassword?: boolean;
};

export function Input({ label, icon, error, isPassword, style, ...rest }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(!!isPassword);

  return (
    <View style={styles.wrap}>
      {label ? <AppText size={13} weight="medium" color={colors.onSurfaceTertiary} style={styles.label}>{label}</AppText> : null}
      <View style={[styles.field, focused && styles.focused, !!error && styles.errored]}>
        {icon ? <Icon name={icon} size={20} color={colors.muted} /> : null}
        <TextInput
          {...rest}
          secureTextEntry={hidden}
          onFocus={(e) => { setFocused(true); rest.onFocus?.(e); }}
          onBlur={(e) => { setFocused(false); rest.onBlur?.(e); }}
          placeholderTextColor={colors.muted}
          style={[styles.input, style]}
        />
        {isPassword ? (
          <Pressable onPress={() => setHidden((h) => !h)} hitSlop={10}>
            <Icon name={hidden ? 'eye-outline' : 'eye-off-outline'} size={20} color={colors.muted} />
          </Pressable>
        ) : null}
      </View>
      {error ? <AppText size={12} color={colors.error} style={styles.error}>{error}</AppText> : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: t.spacing.xs },
  label: { marginLeft: 2 },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: t.spacing.sm,
    backgroundColor: t.colors.surfaceSecondary,
    borderRadius: t.radius.md,
    borderWidth: 1,
    borderColor: t.colors.border,
    paddingHorizontal: t.spacing.lg,
    height: 54,
  },
  focused: { borderColor: t.colors.brand },
  errored: { borderColor: t.colors.error },
  input: {
    flex: 1,
    fontFamily: t.fontFamily.regular,
    fontSize: 16,
    color: t.colors.onSurface,
    height: '100%',
  },
  error: { marginLeft: 2 },
}));
