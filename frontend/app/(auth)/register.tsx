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

export default function Register() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { signUpEmail } = useAuth();
  const toast = useToast();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!name || !email || password.length < 6) {
      toast.show('Fill all fields (password 6+ chars).', 'error');
      return;
    }
    setLoading(true);
    try {
      await signUpEmail(email.trim(), password, name.trim());
    } catch (e) {
      toast.show(e instanceof ApiError ? e.message : 'Sign up failed', 'error');
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
        <AppText weight="semibold" size={30} style={styles.title}>Create your account</AppText>
        <AppText size={16} color={colors.muted} style={styles.subtitle}>Start learning in under a minute.</AppText>

        <View style={styles.form}>
          <Input testID="name-input" label="Name" icon="account-outline" placeholder="Your name" value={name} onChangeText={setName} />
          <Input testID="email-input" label="Email" icon="email-outline" placeholder="you@example.com" autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
          <Input testID="password-input" label="Password" icon="lock-outline" placeholder="At least 6 characters" isPassword value={password} onChangeText={setPassword} />
          <Button testID="register-submit-button" label="Create account" loading={loading} onPress={submit} style={{ marginTop: 8 }} />
        </View>

        <Pressable testID="go-to-login-button" onPress={() => router.replace('/(auth)/login')} style={styles.link}>
          <AppText size={15} color={colors.muted}>Already have an account? </AppText>
          <AppText size={15} weight="medium" color={colors.brand}>Log in</AppText>
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
