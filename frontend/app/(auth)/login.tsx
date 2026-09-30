import React, { useState } from 'react';
import { View, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Input } from '@/src/components/Input';
import { Icon } from '@/src/components/Icon';
import { useAuth } from '@/src/auth/AuthContext';
import { useToast } from '@/src/components/Toast';
import { ApiError } from '@/src/api/client';

export default function Login() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { signInEmail } = useAuth();
  const toast = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!email || !password) {
      toast.show('Enter your email and password.', 'error');
      return;
    }
    setLoading(true);
    try {
      await signInEmail(email.trim(), password);
    } catch (e) {
      toast.show(e instanceof ApiError ? e.message : 'Login failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <Pressable testID="back-button" onPress={() => router.back()} style={styles.back} hitSlop={10}>
        <Icon name="chevron-left" size={28} color={colors.onSurface} />
      </Pressable>
      <KeyboardAwareScrollView
        bottomOffset={24}
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <AppText weight="semibold" size={30} style={styles.title}>Welcome back</AppText>
        <AppText size={16} color={colors.muted} style={styles.subtitle}>Log in to continue your journey.</AppText>

        <View style={styles.form}>
          <Input testID="email-input" label="Email" icon="email-outline" placeholder="you@example.com" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
          <Input testID="password-input" label="Password" icon="lock-outline" placeholder="Your password" isPassword value={password} onChangeText={setPassword} />
          <Button testID="login-submit-button" label="Log in" loading={loading} onPress={submit} style={{ marginTop: 8 }} />
        </View>

        <Pressable testID="go-to-register-button" onPress={() => router.replace('/(auth)/register')} style={styles.link}>
          <AppText size={15} color={colors.muted}>New to Vocabist? </AppText>
          <AppText size={15} weight="medium" color={colors.brand}>Create account</AppText>
        </Pressable>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  back: { marginLeft: t.spacing.md, marginBottom: t.spacing.sm, width: 40, height: 40, justifyContent: 'center' },
  scroll: { paddingHorizontal: t.spacing.xl, flexGrow: 1 },
  title: { marginTop: t.spacing.lg },
  subtitle: { marginTop: t.spacing.xs, marginBottom: t.spacing.xl },
  form: { gap: t.spacing.lg },
  link: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', marginTop: t.spacing.xl },
}));
