import React from 'react';
import { View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { useTheme } from '@/src/theme';
import { AppText } from './AppText';

type Props = {
  size?: number;
  strokeWidth?: number;
  progress: number; // 0..1
  centerLabel?: string;
  centerSub?: string;
  color?: string;
  track?: string;
};

export function ProgressRing({
  size = 120, strokeWidth = 12, progress, centerLabel, centerSub, color, track,
}: Props) {
  const { colors } = useTheme();
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, progress));
  const offset = c * (1 - clamped);
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle
          cx={size / 2} cy={size / 2} r={r}
          stroke={track ?? colors.surfaceTertiary} strokeWidth={strokeWidth} fill="none"
        />
        <Circle
          cx={size / 2} cy={size / 2} r={r}
          stroke={color ?? colors.brand} strokeWidth={strokeWidth} fill="none"
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      {(centerLabel || centerSub) && (
        <View style={{ position: 'absolute', alignItems: 'center' }}>
          {centerLabel ? <AppText weight="semibold" size={24}>{centerLabel}</AppText> : null}
          {centerSub ? <AppText size={12} color={colors.muted}>{centerSub}</AppText> : null}
        </View>
      )}
    </View>
  );
}
