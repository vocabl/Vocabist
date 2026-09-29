import React, { useEffect } from 'react';
import { View, ViewStyle } from 'react-native';
import Animated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming, withSequence } from 'react-native-reanimated';
import { colors, radius } from '@/src/theme';

export function Skeleton({ width, height, style, rounded }: { width?: number | string; height?: number; style?: ViewStyle; rounded?: number }) {
  const opacity = useSharedValue(0.5);
  useEffect(() => {
    opacity.value = withRepeat(withSequence(withTiming(1, { duration: 700 }), withTiming(0.5, { duration: 700 })), -1, false);
  }, [opacity]);
  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return (
    <Animated.View
      style={[
        { width: (width as any) ?? '100%', height: height ?? 16, backgroundColor: colors.surfaceTertiary, borderRadius: rounded ?? radius.sm },
        animStyle,
        style,
      ]}
    />
  );
}

export function SkeletonBlock({ children }: { children: React.ReactNode }) {
  return <View style={{ gap: 12 }}>{children}</View>;
}
