import React from 'react';
import { Platform } from 'react-native';
import { Tabs } from 'expo-router';
import { NativeTabs } from 'expo-router/unstable-native-tabs';
import { Icon } from '@/src/components/Icon';
import { colors, fontFamily } from '@/src/theme';
import { usesNativeTabs } from '@/src/navigation';

const TABS = [
  { name: 'home', label: 'Home', icon: 'home-variant', iconOutline: 'home-variant-outline', sf: 'house.fill' },
  { name: 'learn', label: 'Learn', icon: 'cards', iconOutline: 'cards-outline', sf: 'square.stack.fill' },
  { name: 'exams', label: 'Exams', icon: 'trophy', iconOutline: 'trophy-outline', sf: 'trophy.fill' },
  { name: 'discover', label: 'Discover', icon: 'compass', iconOutline: 'compass-outline', sf: 'safari.fill' },
  { name: 'profile', label: 'Profile', icon: 'account-circle', iconOutline: 'account-circle-outline', sf: 'person.crop.circle.fill' },
] as const;

export default function TabsLayout() {
  if (usesNativeTabs) {
    return (
      <NativeTabs>
        {TABS.map((t) => (
          <NativeTabs.Trigger key={t.name} name={t.name}>
            <NativeTabs.Trigger.Icon sf={t.sf as any} />
            <NativeTabs.Trigger.Label>{t.label}</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
        ))}
      </NativeTabs>
    );
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          ...(Platform.OS === 'web' ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: 'center' },
        tabBarLabelStyle: { fontFamily: fontFamily.medium, fontSize: 11 },
      }}
    >
      {TABS.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.label,
            tabBarButtonTestID: `tab-${t.name}`,
            tabBarIcon: ({ focused, color }) => (
              <Icon name={(focused ? t.icon : t.iconOutline) as any} size={26} color={color} />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
