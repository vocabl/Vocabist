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
import { Skeleton } from '@/src/components/Skeleton';
import { useAuth } from '@/src/auth/AuthContext';
import { useToast } from '@/src/components/Toast';
import { useEntitlement } from '@/src/hooks/useEntitlement';
import { api } from '@/src/api/client';

const BENEFITS = [
  { icon: 'infinity', title: 'Unlimited learning', desc: 'No daily word caps — learn as much as you want' },
  { icon: 'trophy-outline', title: 'All exam libraries', desc: 'GRE, GMAT and every exam deck unlocked' },
  { icon: 'robot-happy-outline', title: 'Unlimited AI Coach', desc: 'Explanations, examples & memory hooks on tap' },
  { icon: 'chart-line', title: 'Deeper insights', desc: 'Advanced progress analytics and weak-area tracking' },
  { icon: 'book-open-page-variant-outline', title: 'Premium tools', desc: 'Learn From Anything with higher limits' },
];

const PLAN_OPTIONS = [
  { key: 'annual', label: 'Yearly', badge: 'BEST VALUE' },
  { key: 'monthly', label: 'Monthly', badge: null },
];

export default function Paywall() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { refresh: refreshAuth } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const ent = useEntitlement();
  const [selectedPlan, setSelectedPlan] = useState('annual');
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    api('/analytics', { method: 'POST', body: { event: 'paywall_viewed', props: {} } }).catch(() => {});
  }, []);

  const handleUpgrade = async () => {
    if (!ent.providerConnected) {
      toast.show('Billing is not configured yet. Purchases will be available soon.', 'info');
      return;
    }
    setLoading(true);
    try {
      await api('/subscription/activate', { method: 'POST', body: { plan: selectedPlan } });
      await refreshAuth();
      ent.refresh();
      qc.invalidateQueries();
      toast.show('Welcome to Vocabist Pro!', 'success');
    } catch {
      toast.show('Could not complete purchase. Try again.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    setLoading(true);
    try {
      await api('/subscription/cancel', { method: 'POST' });
      await refreshAuth();
      ent.refresh();
      qc.invalidateQueries();
      toast.show('Pro subscription cancelled.', 'info');
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async () => {
    setRestoring(true);
    try {
      const result = await api<{ restored: boolean; message: string }>('/subscription/restore', { method: 'POST' });
      if (result.restored) {
        await refreshAuth();
        ent.refresh();
        qc.invalidateQueries();
        toast.show('Subscription restored!', 'success');
      } else {
        toast.show(result.message, 'info');
      }
    } catch {
      toast.show('Could not restore purchases.', 'error');
    } finally {
      setRestoring(false);
    }
  };

  const pricing = ent.pricing;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      <Pressable testID="paywall-close" onPress={() => router.back()} hitSlop={10} style={styles.close}
        accessibilityRole="button" accessibilityLabel="Close paywall">
        <Icon name="close" size={26} color={colors.onSurface} />
      </Pressable>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.crown}>
          <Icon name="crown" size={34} color={colors.warning} />
        </View>
        <AppText weight="semibold" size={30} style={styles.title} testID="paywall-title">
          Vocabist Pro
        </AppText>
        <AppText size={16} color={colors.muted} style={styles.subtitle}>
          Unlock the full learning experience.
        </AppText>

        {/* Benefits */}
        <View style={styles.benefits}>
          {BENEFITS.map((b, i) => (
            <Animated.View key={b.title} entering={FadeInDown.delay(i * 50).duration(240)} style={styles.benefitRow}>
              <View style={styles.benefitIcon}>
                <Icon name={b.icon as any} size={20} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <AppText weight="medium" size={15}>{b.title}</AppText>
                <AppText size={13} color={colors.muted} style={{ marginTop: 1 }}>{b.desc}</AppText>
              </View>
            </Animated.View>
          ))}
        </View>

        {ent.loading ? (
          <View style={{ marginTop: 32, gap: 12 }}>
            <Skeleton width="100%" height={72} rounded={14} />
            <Skeleton width="100%" height={72} rounded={14} />
          </View>
        ) : ent.isPro ? (
          /* Active Pro state */
          <View style={styles.activeBox} testID="pro-active-badge">
            <Icon name="check-decagram" size={22} color={colors.success} />
            <View style={{ flex: 1 }}>
              <AppText weight="medium" size={16}>You&apos;re a Pro member</AppText>
              {ent.data?.subscription_plan && (
                <AppText size={12} color={colors.muted} style={{ marginTop: 2 }}>
                  {ent.data.subscription_plan} plan · {ent.data.source === 'mock' ? 'Preview mode' : 'Active'}
                </AppText>
              )}
            </View>
          </View>
        ) : (
          /* Plan selection */
          <View style={styles.plans}>
            {PLAN_OPTIONS.map((pl) => {
              const p = pricing[pl.key];
              return (
                <Pressable
                  key={pl.key}
                  testID={`plan-${pl.key}`}
                  onPress={() => setSelectedPlan(pl.key)}
                  style={[styles.plan, selectedPlan === pl.key && styles.planActive]}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selectedPlan === pl.key }}
                  accessibilityLabel={`${pl.label} plan ${p?.price_display ?? ''}`}
                >
                  <View style={styles.radio}>
                    {selectedPlan === pl.key ? <View style={styles.radioDot} /> : null}
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={styles.planHead}>
                      <AppText weight="medium" size={16}>{pl.label}</AppText>
                      {pl.badge && (
                        <View style={styles.badge}>
                          <AppText size={10} weight="semibold" color={colors.onBrand}>{pl.badge}</AppText>
                        </View>
                      )}
                    </View>
                    <AppText size={13} color={colors.muted}>
                      {pl.key === 'annual' ? `${p?.price_display ?? '$49.99'}/yr` : `${p?.price_display ?? '$7.99'}/mo`}
                    </AppText>
                  </View>
                  <AppText weight="semibold" size={18}>{p?.price_display ?? ''}</AppText>
                </Pressable>
              );
            })}
          </View>
        )}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
        {ent.isPro ? (
          <Button testID="cancel-pro-button" label="Cancel Pro" variant="ghost"
            loading={loading} onPress={handleCancel} />
        ) : (
          <>
            <Button testID="subscribe-button" label="Subscribe to Pro" icon="crown-outline"
              loading={loading} onPress={handleUpgrade} />
            <View style={styles.footerLinks}>
              <Pressable testID="restore-purchases-btn" onPress={handleRestore} hitSlop={8}
                accessibilityRole="button" accessibilityLabel="Restore purchases">
                <AppText size={13} color={colors.muted}>
                  {restoring ? 'Restoring...' : 'Restore purchases'}
                </AppText>
              </Pressable>
              <AppText size={13} color={colors.border}>·</AppText>
              <Pressable onPress={() => router.back()} hitSlop={8}
                accessibilityRole="button" accessibilityLabel="Continue with free plan">
                <AppText size={13} color={colors.muted}>Continue free</AppText>
              </Pressable>
            </View>
            {!ent.providerConnected && (
              <AppText size={11} color={colors.muted} style={styles.legal}>
                Billing is being configured. Purchases will be available soon.
              </AppText>
            )}
          </>
        )}
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  close: { marginLeft: t.spacing.lg, width: 40, height: 40, justifyContent: 'center' },
  scroll: { paddingHorizontal: t.spacing.xl, paddingBottom: t.spacing.xl },
  crown: {
    width: 68, height: 68, borderRadius: 34, backgroundColor: '#FBF3E2',
    alignItems: 'center', justifyContent: 'center', marginTop: t.spacing.sm,
  },
  title: { marginTop: t.spacing.lg },
  subtitle: { marginTop: 4, marginBottom: t.spacing.xl },
  benefits: { gap: t.spacing.lg },
  benefitRow: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.md },
  benefitIcon: {
    width: 40, height: 40, borderRadius: t.radius.md,
    backgroundColor: t.colors.brandTertiary, alignItems: 'center', justifyContent: 'center',
  },
  plans: { gap: t.spacing.md, marginTop: t.spacing.xxl },
  plan: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    borderWidth: 1.5, borderColor: t.colors.border, borderRadius: t.radius.md,
    padding: t.spacing.lg, backgroundColor: t.colors.surfaceSecondary,
  },
  planActive: { borderColor: t.colors.brand, backgroundColor: t.colors.brandTertiary },
  radio: {
    width: 22, height: 22, borderRadius: 11, borderWidth: 2,
    borderColor: t.colors.brand, alignItems: 'center', justifyContent: 'center',
  },
  radioDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: t.colors.brand },
  planHead: { flexDirection: 'row', alignItems: 'center', gap: t.spacing.sm },
  badge: { backgroundColor: t.colors.brand, paddingHorizontal: 7, paddingVertical: 2, borderRadius: t.radius.sm },
  activeBox: {
    flexDirection: 'row', alignItems: 'center', gap: t.spacing.md,
    marginTop: t.spacing.xxl, backgroundColor: t.colors.brandTertiary,
    padding: t.spacing.lg, borderRadius: t.radius.md,
  },
  footer: {
    paddingHorizontal: t.spacing.xl, paddingTop: t.spacing.md,
    borderTopWidth: 1, borderTopColor: t.colors.divider,
  },
  footerLinks: {
    flexDirection: 'row', justifyContent: 'center', alignItems: 'center',
    gap: t.spacing.sm, marginTop: t.spacing.md,
  },
  legal: { textAlign: 'center', marginTop: t.spacing.sm },
}));
