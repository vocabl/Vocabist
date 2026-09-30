import { useMemo } from 'react';
import { StyleSheet } from 'react-native';

// ============================================================================
// Vocabist theme — light mode only. Tokens mirror design_guidelines.json.
// ============================================================================

export const colors = {
  surface: '#FDFDFB',
  onSurface: '#1A1A18',
  surfaceSecondary: '#FFFFFF',
  onSurfaceSecondary: '#1A1A18',
  surfaceTertiary: '#F4F4F2',
  onSurfaceTertiary: '#3D3D3A',
  surfaceInverse: '#2B2B29',
  onSurfaceInverse: '#FFFFFF',

  brand: '#4A7C59',
  onBrand: '#FFFFFF',
  brandPrimary: '#4A7C59',
  onBrandPrimary: '#FFFFFF',
  brandSecondary: '#779C81',
  onBrandSecondary: '#132B1A',
  brandTertiary: '#E7F0E9',
  onBrandTertiary: '#294A34',

  success: '#3E7B51',
  onSuccess: '#FFFFFF',
  warning: '#D19036',
  onWarning: '#FFFFFF',
  error: '#B54D4D',
  onError: '#FFFFFF',
  info: '#4A7C59',
  onInfo: '#FFFFFF',

  border: '#EBEBE8',
  borderStrong: '#D6D6D2',
  divider: '#F0F0EE',
  muted: '#73736E',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const radius = {
  sm: 6,
  md: 12,
  lg: 20,
  pill: 999,
} as const;

export const fontFamily = {
  regular: 'PlusJakartaSans-Regular',
  medium: 'PlusJakartaSans-Medium',
  semibold: 'PlusJakartaSans-SemiBold',
} as const;

export const fontSize = {
  sm: 12,
  base: 14,
  lg: 16,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
  '4xl': 40,
} as const;

export const shadow = {
  sm: {
    shadowColor: '#1A1A18',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  md: {
    shadowColor: '#1A1A18',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.07,
    shadowRadius: 12,
    elevation: 3,
  },
  lg: {
    shadowColor: '#1A1A18',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.1,
    shadowRadius: 24,
    elevation: 6,
  },
} as const;

export type Theme = {
  colors: typeof colors;
  spacing: typeof spacing;
  radius: typeof radius;
  fontFamily: typeof fontFamily;
  fontSize: typeof fontSize;
  shadow: typeof shadow;
};

const theme: Theme = { colors, spacing, radius, fontFamily, fontSize, shadow };

export function useTheme(): Theme {
  return theme;
}

// makeStyles: build a StyleSheet from a factory that receives the theme.
export function makeStyles<T extends StyleSheet.NamedStyles<T>>(
  factory: (t: Theme) => T | StyleSheet.NamedStyles<T>
): () => T {
  return function useStyles(): T {
    return useMemo(() => StyleSheet.create(factory(theme) as T), []);
  };
}
