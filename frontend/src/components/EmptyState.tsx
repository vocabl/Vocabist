import React from 'react';
import { View, ViewStyle } from 'react-native';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from './AppText';
import { Icon } from './Icon';
import { Button } from './Button';

type Props = {
  icon?: React.ComponentProps<typeof Icon>['name'];
  title: string;
  description?: string;
  action?: { label: string; onPress: () => void; testID?: string };
  secondaryAction?: { label: string; onPress: () => void; testID?: string };
  compact?: boolean;
  style?: ViewStyle;
  testID?: string;
};

/**
 * Shared empty/zero-data state. Every list / async view should prefer this
 * over blank space. Always offers at least one meaningful next action.
 */
export function EmptyState({
  icon = 'book-open-page-variant',
  title,
  description,
  action,
  secondaryAction,
  compact,
  style,
  testID,
}: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View
      style={[styles.wrap, compact && styles.compact, style]}
      testID={testID}
      accessibilityLiveRegion="polite"
    >
      <View style={[styles.iconBubble, compact && styles.iconBubbleCompact]}>
        <Icon name={icon} size={compact ? 24 : 30} color={colors.brand} />
      </View>
      <AppText weight="semibold" size={compact ? 15 : 17} style={{ marginTop: 12, textAlign: 'center' }}>
        {title}
      </AppText>
      {description ? (
        <AppText
          size={14}
          color={colors.muted}
          style={{ marginTop: 6, textAlign: 'center', lineHeight: 20, maxWidth: 320 }}
        >
          {description}
        </AppText>
      ) : null}
      {action || secondaryAction ? (
        <View style={styles.actions}>
          {action ? (
            <Button
              label={action.label}
              onPress={action.onPress}
              size="md"
              testID={action.testID}
              style={{ minWidth: 180 }}
            />
          ) : null}
          {secondaryAction ? (
            <Button
              label={secondaryAction.label}
              onPress={secondaryAction.onPress}
              variant="ghost"
              size="md"
              testID={secondaryAction.testID}
            />
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 40,
    paddingHorizontal: t.spacing.xl,
  },
  compact: { paddingVertical: 24 },
  iconBubble: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: t.colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconBubbleCompact: { width: 48, height: 48, borderRadius: 24 },
  actions: { marginTop: t.spacing.xl, alignItems: 'center', gap: t.spacing.sm },
}));
