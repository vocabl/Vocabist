import React from 'react';
import { View, ActivityIndicator } from 'react-native';
import { colors } from '@/src/theme';

// The root layout gate handles all redirects; this is only the initial splash.
export default function Index() {
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface }}>
      <ActivityIndicator color={colors.brand} />
    </View>
  );
}
