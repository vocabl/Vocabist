import React, { useEffect, useState } from 'react';
import { View, ScrollView, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { useAuth } from '@/src/auth/AuthContext';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

const BENEFITS = [
  { icon: 'infinity', title: 'Unlimited learning', desc: 'No daily word caps — learn as much as you want' },
  { icon: 'trophy-outline', title: 'All exam libraries', desc: 'GRE, GMAT and every exam deck unlocked' },
  { icon: 'robot-happy-outline', title: 'Unlimited AI Coach', desc: 'Explanations, examples & memory hooks on tap' },
  { icon: 'chart-line', title: 'Advanced analytics', desc: 'Deeper insights into your weak areas' },
  { icon: 'volume-high', title: 'Pronunciation & audio', desc: 'US/UK audio for every word' },
];

const PLANS = [
  { key: 'monthly', title: 'Monthly', price: '$7.99', sub: 'per month', badge: null },
  { key: 'yearly', title: 'Yearly', price: '$49.99', sub: '$4.16/mo · save 48%', badge: 'BEST VALUE' },
  { key: 'lifetime', title: 'Lifetime', price: '$99.99', sub: 'one-time payment', badge: null },
];

export default function Paywall() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, refresh } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [plan, setPlan] = useState('yearly');
  const [loading, setLoading] = useState(false);

  useEffect(() => { api('/analytics', { method: 'POST', body: { event: 'paywall_viewed', props: {} } }).catch(() => {}); }, []);

  const isPro = user?.tier === 'pro';

  const activate = async () => {
    setLoading(true);
    try {
      await api('/subscription/activate', { method: 'POST', body: { plan } });
      await refresh();
      qc.invalidateQueries();
      toast.show('Welcome to Vocably Pro! 🎉', 'success');
    } catch {
      toast.show('Could not activate. Try again.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const cancel = async () => {
    setLoading(true);
    try {
      await api('/subscription/cancel', { method: 'POST' });
      await refresh();
      qc.invalidateQueries();
      toast.show('Pro cancelled', 'info');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <Pressable testID="paywall-close" onPress={() => router.back()} hitSlop={10} style={styles.close}>
        <Icon name="close" size={26} color={colors.onSurface} />
      </Pressable>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.crown}><Icon name="crown" size={34} color={colors.warning} /></View>
        <AppText weight="semibold" size={30} style={styles.title}>Vocably Pro</AppText>
        <AppText size={16} color={colors.muted} style={styles.subtitle}>Unlock the full learning experience.</AppText>

        <View style={styles.benefits}>
          {BENEFITS.map((b, i) => (
            <Animated.View key={b.title} entering={FadeInDown.delay(i * 50).duration(240)} style={styles.benefitRow}>
              <View style={styles.benefitIcon}><Icon name={b.icon as any} size={20} color={colors.brand} /></View>
              <View style={{ flex: 1 }}>
                <AppText weight="medium" size={15}>{b.title}</AppText>
                <AppText size={13} color={colors.muted} style={{ marginTop: 1 }}>{b.desc}</AppText>
              </View>
            </Animated.View>
          ))}
        </View>

        {!isPro ? (
          <View style={styles.plans}>
            {PLANS.map((pl) => (
              <Pressable key={pl.key} testID={`plan-${pl.key}`} onPress={() => setPlan(pl.key)} style={[styles.plan, plan === pl.key && styles.planActive]}>
                <View style={styles.radio}>{plan === pl.key ? <View style={styles.radioDot} /> : null}</View>
                <View style={{ flex: 1 }}>
                  <View style={styles.planHead}>
                    <AppText weight="medium" size={16}>{pl.title}</AppText>
                    {pl.badge ? <View style={styles.badge}><AppText size={10} weight="semibold" color={colors.onBrand}>{pl.badge}</AppText></View> : null}
                  </View>
                  <AppText size={13} color={colors.muted}>{pl.sub}</AppText>
                </View>
                <AppText weight="semibold" size={18}>{pl.price}</AppText>
              </Pressable>
            ))}
          </View>
        ) : (
          <View style={styles.activeBox}>
            <Icon name="check-decagram" size={22} color={colors.success} />
            <AppText weight="medium" size={16} color={colors.onSurface}>You're a Pro member</AppText>
          </View>
        )}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
        {!isPro ? (
          <>
            <Button testID="subscribe-button" label="Start Pro" icon="crown-outline" loading={loading} onPress={activate} />
            <AppText size={12} color={colors.muted} style={styles.legal}>Simulated purchase in preview. Real billing added at launch.</AppText>
          </>
        ) : (
          <Button testID="cancel-pro-button" label="Cancel Pro" variant="ghost" loading={loading} onPress={cancel} />
        )}
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  close: { marginLeft: t.spacing.lg, width: 40, height: 40, justifyContent: 'center' },
  scroll: { paddingHorizontal: t.spacing.xl, paddingBottom: t.spacing.xl },
  crown: { width: 68, height: 68, borderRadius: 34, backgroundColor: '#FBF3E2', alignItems: 'center', justifyContent: 'center', marginTop: t.spacing.sm },
  title: { marginTop: t.spacing.lg },
  subtitle: { marginTop: 4, marginBottom: t.spacing.xl },
  benefits: { gap: t.spacing.lg },
  benefitRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  benefitIcon: { width: 40, height: 40, borderRadius: t.radius.md, backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center' },
  plans: { gap: t.spacing.md, marginTop: t.spacing.xxl },
  plan: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md, borderWidth: 1.5, borderColor: t.colors.border, borderRadius: t.radius.md, padding: t.spacing.lg, backgroundColor: t.colors.surfaceSecondary },
  planActive: { borderColor: t.colors.brand, backgroundColor: t.colors.brandTertiary },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: t.colors.brand, alignItems: 'center', justifyContent: 'center' },
  radioDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: t.colors.brand },
  planHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  badge: { backgroundColor: t.colors.brand, paddingHorizontal: 7, paddingVertical: 2, borderRadius: t.radius.sm },
  activeBox: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm, marginTop: t.spacing.xxl, backgroundColor: t.colors.brandTertiary, padding: t.spacing.lg, borderRadius: t.radius.md },
  footer: { paddingHorizontal: t.spacing.xl, paddingTop: t.spacing.md, borderTopWidth: 1, borderTopColor: t.colors.divider },
  legal: { textAlign: 'center', marginTop: t.spacing.sm },
}));
