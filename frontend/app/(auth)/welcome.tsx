import React, { useState } from 'react';
import { View, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { useAuth } from '@/src/auth/AuthContext';
import { useToast } from '@/src/components/Toast';

export default function Welcome() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { signInGoogle } = useAuth();
  const toast = useToast();
  const [googleLoading, setGoogleLoading] = useState(false);

  const onGoogle = async () => {
    setGoogleLoading(true);
    try {
      await signInGoogle();
    } catch {
      toast.show('Google sign-in failed. Try again.', 'error');
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.hero}>
        <View style={styles.logo}>
          <Icon name="book-open-page-variant" size={34} color={colors.onBrand} />
        </View>
        <AppText weight="semibold" size={40} style={styles.title}>Vocably</AppText>
        <AppText size={17} color={colors.muted} style={styles.tagline}>
          Learn the words that matter. A calm, personalized path to a powerful vocabulary.
        </AppText>

        <View style={styles.loopRow}>
          {['Discover', 'Recall', 'Master'].map((s, i) => (
            <View key={s} style={styles.loopItem}>
              <View style={styles.loopDot}>
                <Icon name={i === 0 ? 'compass-outline' : i === 1 ? 'brain' : 'trophy-outline'} size={18} color={colors.brand} />
              </View>
              <AppText size={12} weight="medium" color={colors.onSurfaceTertiary}>{s}</AppText>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.actions}>
        <Button testID="get-started-button" label="Get started" onPress={() => router.push('/(auth)/register')} />
        <Button testID="google-signin-button" label="Continue with Google" variant="ghost" icon="google" loading={googleLoading} onPress={onGoogle} />
        <Pressable testID="go-to-login-button" onPress={() => router.push('/(auth)/login')} style={styles.loginLink}>
          <AppText size={15} color={colors.muted}>Already have an account? </AppText>
          <AppText size={15} weight="medium" color={colors.brand}>Log in</AppText>
        </Pressable>
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface, paddingHorizontal: t.spacing.xl, justifyContent: 'space-between' },
  hero: { flex: 1, justifyContent: 'center' },
  logo: {
    width: 72, height: 72, borderRadius: 22, backgroundColor: t.colors.brand,
    alignItems: 'center', justifyContent: 'center', marginBottom: t.spacing.xl, ...t.shadow.md,
  },
  title: { marginBottom: t.spacing.sm },
  tagline: { lineHeight: 25, maxWidth: 340 },
  loopRow: { flexDirection: 'row', gap: t.spacing.xl, marginTop: t.spacing.xxxl },
  loopItem: { alignItems: 'center', gap: t.spacing.sm },
  loopDot: {
    width: 44, height: 44, borderRadius: t.radius.md, backgroundColor: t.colors.brandTertiary,
    alignItems: 'center', justifyContent: 'center',
  },
  actions: { gap: t.spacing.md },
  loginLink: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', paddingVertical: t.spacing.sm },
}));
