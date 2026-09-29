import React, { createContext, useCallback, useContext, useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInUp, FadeOutUp } from 'react-native-reanimated';
import { colors, radius, spacing, shadow, fontFamily } from '@/src/theme';
import { Icon } from './Icon';
import { AppText } from './AppText';

type ToastType = 'success' | 'error' | 'info';
type ToastItem = { id: number; message: string; type: ToastType };

const ToastContext = createContext<{ show: (message: string, type?: ToastType) => void }>({
  show: () => {},
});

export const useToast = () => useContext(ToastContext);

let counter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const insets = useSafeAreaInsets();

  const show = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++counter;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 2600);
  }, []);

  const iconFor: Record<ToastType, any> = {
    success: 'check-circle',
    error: 'alert-circle',
    info: 'information',
  };
  const colorFor: Record<ToastType, string> = {
    success: colors.success,
    error: colors.error,
    info: colors.brand,
  };

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <View style={[styles.wrap, { top: insets.top + spacing.sm, pointerEvents: 'box-none' }]}>
        {toasts.map((t) => (
          <Animated.View key={t.id} entering={FadeInUp} exiting={FadeOutUp} style={styles.toast}>
            <Icon name={iconFor[t.type]} size={20} color={colorFor[t.type]} />
            <AppText size={14} weight="medium" style={{ flex: 1 }} color={colors.onSurface}>
              {t.message}
            </AppText>
          </Animated.View>
        ))}
      </View>
    </ToastContext.Provider>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    alignItems: 'center',
    gap: spacing.sm,
    zIndex: 1000,
  },
  toast: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    ...shadow.md,
    maxWidth: 460,
    width: '100%',
    fontFamily: fontFamily.regular,
  },
});
