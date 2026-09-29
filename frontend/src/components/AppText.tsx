import React from 'react';
import { Text, TextProps, StyleSheet } from 'react-native';
import { colors, fontFamily, fontSize } from '@/src/theme';

type Weight = 'regular' | 'medium' | 'semibold';

type Props = TextProps & {
  size?: number;
  weight?: Weight;
  color?: string;
  children?: React.ReactNode;
};

const familyFor: Record<Weight, string> = {
  regular: fontFamily.regular,
  medium: fontFamily.medium,
  semibold: fontFamily.semibold,
};

export function AppText({ size = fontSize.base, weight = 'regular', color, style, children, ...rest }: Props) {
  return (
    <Text
      {...rest}
      style={[
        { fontFamily: familyFor[weight], fontSize: size, color: color ?? colors.onSurface },
        style,
      ]}
    >
      {children}
    </Text>
  );
}

export const textStyles = StyleSheet.create({});
