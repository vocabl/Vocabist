import React, { useState, useCallback } from 'react';
import { View, ScrollView, Pressable, Alert, ActivityIndicator, Image } from 'react-native';
import { useRouter, Stack } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import * as Linking from 'expo-linking';
import { makeStyles, useTheme } from '@/src/theme';
import { AppText } from '@/src/components/AppText';
import { Button } from '@/src/components/Button';
import { Icon } from '@/src/components/Icon';
import { useToast } from '@/src/components/Toast';
import { api } from '@/src/api/client';

type Candidate = {
  headword: string;
  simple_definition?: string;
  cefr?: string;
  part_of_speech?: string;
  detected_context?: string;
  confidence?: string;
  reason?: string;
  already_exists?: boolean;
  existing_id?: string;
  selected?: boolean;
};

export default function VisualCapture() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();

  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [extracted, setExtracted] = useState(false);

  const pickImage = useCallback(async (fromCamera: boolean) => {
    try {
      const perm = fromCamera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();

      if (!perm.granted) {
        Alert.alert(
          'Permission needed',
          fromCamera ? 'Camera access is needed to capture study materials.' : 'Photo library access is needed to select study materials.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Open Settings', onPress: () => {
              Linking.openSettings();
            }},
          ]
        );
        return;
      }

      const result = fromCamera
        ? await ImagePicker.launchCameraAsync({ base64: true, quality: 0.7 })
        : await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.7, mediaTypes: ['images'] });

      if (!result.canceled && result.assets[0]) {
        const asset = result.assets[0];
        setImageUri(asset.uri);
        setImageBase64(asset.base64 || null);
        setCandidates([]);
        setExtracted(false);
      }
    } catch {
      toast.show('Could not open image picker', 'error');
    }
  }, [toast]);

  const extractWords = useCallback(async () => {
    if (!imageBase64) return;
    setExtracting(true);
    try {
      const mimeType = 'image/jpeg';
      const dataUrl = `data:${mimeType};base64,${imageBase64}`;
      const res = await api<{ candidates: Candidate[]; total_extracted: number }>('/visual-capture/extract', {
        method: 'POST',
        body: { image: dataUrl, max_words: 20 },
      });
      const withSelection = (res.candidates || []).map((c) => ({
        ...c,
        selected: !c.already_exists,
      }));
      setCandidates(withSelection);
      setExtracted(true);
      if (withSelection.length === 0) {
        toast.show('No vocabulary found in this image', 'info');
      }
    } catch (err: any) {
      toast.show(err?.message || 'Extraction failed', 'error');
    } finally {
      setExtracting(false);
    }
  }, [imageBase64, toast]);

  const toggleCandidate = useCallback((idx: number) => {
    setCandidates((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, selected: !c.selected } : c))
    );
  }, []);

  const importSelected = useCallback(async () => {
    const selected = candidates.filter((c) => c.selected && !c.already_exists);
    if (selected.length === 0) {
      toast.show('No new words selected', 'info');
      return;
    }
    setImporting(true);
    try {
      const words = selected.map((c) => ({
        headword: c.headword,
        simple_definition: c.simple_definition,
        cefr: c.cefr,
        part_of_speech: c.part_of_speech,
        example: c.detected_context,
      }));
      const res = await api('/visual-capture/import', { method: 'POST', body: { words } });
      toast.show(`${res.created || 0} words sent to review`, 'success');
      setCandidates([]);
      setImageUri(null);
      setImageBase64(null);
      setExtracted(false);
    } catch (err: any) {
      toast.show(err?.message || 'Import failed', 'error');
    } finally {
      setImporting(false);
    }
  }, [candidates, toast]);

  const selectedCount = candidates.filter((c) => c.selected && !c.already_exists).length;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Stack.Screen options={{ headerShown: false }} />
      {/* Header */}
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Icon name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <AppText weight="semibold" size={18}>Capture Words</AppText>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* Image selection */}
        {!imageUri ? (
          <View style={styles.pickSection}>
            <View style={styles.pickIcon}>
              <Icon name="camera-outline" size={40} color={colors.brand} />
            </View>
            <AppText weight="medium" size={16} style={{ marginTop: 16, textAlign: 'center' }}>
              Scan study material
            </AppText>
            <AppText size={14} color={colors.muted} style={{ marginTop: 6, textAlign: 'center' }}>
              Take a photo or upload an image of a textbook page, notes, or any study material.
            </AppText>
            <View style={styles.btnRow}>
              <Button
                testID="visual-camera"
                label="Camera"
                onPress={() => pickImage(true)}
                variant="primary"
                icon="camera"
                style={{ flex: 1 }}
              />
              <Button
                testID="visual-gallery"
                label="Gallery"
                onPress={() => pickImage(false)}
                variant="secondary"
                icon="image"
                style={{ flex: 1 }}
              />
            </View>
          </View>
        ) : (
          <>
            {/* Preview */}
            <View style={styles.previewContainer}>
              <Image source={{ uri: imageUri }} style={styles.previewImage} resizeMode="cover" />
              <Pressable style={styles.changeBtn} onPress={() => {
                setImageUri(null);
                setImageBase64(null);
                setCandidates([]);
                setExtracted(false);
              }}>
                <Icon name="close" size={18} color={colors.onSurface} />
              </Pressable>
            </View>

            {!extracted && (
              <Button
                testID="visual-extract"
                label={extracting ? "Extracting vocabulary..." : "Extract vocabulary"}
                onPress={extractWords}
                disabled={extracting}
                variant="primary"
                icon={extracting ? undefined : "text-search"}
              />
            )}

            {extracting && (
              <View style={styles.loadingBox}>
                <ActivityIndicator color={colors.brand} size="small" />
                <AppText size={13} color={colors.muted} style={{ marginTop: 8, textAlign: 'center' }}>
                  Analyzing image for vocabulary...
                </AppText>
              </View>
            )}

            {/* Results */}
            {extracted && candidates.length > 0 && (
              <>
                <View style={styles.resultsHeader}>
                  <AppText weight="semibold" size={16}>
                    {candidates.length} words found
                  </AppText>
                  <AppText size={13} color={colors.muted}>
                    {selectedCount} selected for review
                  </AppText>
                </View>

                {candidates.map((c, idx) => (
                  <Pressable
                    key={`${c.headword}-${idx}`}
                    onPress={() => c.already_exists && c.existing_id
                      ? router.push(`/word/${c.existing_id}`)
                      : toggleCandidate(idx)
                    }
                    style={[
                      styles.candidateCard,
                      c.already_exists && styles.candidateExisting,
                      c.selected && !c.already_exists && styles.candidateSelected,
                    ]}
                  >
                    <View style={styles.candidateRow}>
                      {!c.already_exists && (
                        <View style={[styles.checkbox, c.selected && styles.checkboxActive]}>
                          {c.selected && <Icon name="check" size={14} color="#FFF" />}
                        </View>
                      )}
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <AppText weight="semibold" size={15}>{c.headword}</AppText>
                          {c.cefr && (
                            <View style={styles.cefrBadge}>
                              <AppText size={10} weight="medium" color={colors.brand}>{c.cefr}</AppText>
                            </View>
                          )}
                          {c.part_of_speech && (
                            <AppText size={11} color={colors.muted}>{c.part_of_speech}</AppText>
                          )}
                        </View>
                        {c.simple_definition && (
                          <AppText size={13} color={colors.muted} numberOfLines={2} style={{ marginTop: 3 }}>
                            {c.simple_definition}
                          </AppText>
                        )}
                        {c.detected_context && (
                          <AppText size={11} color={colors.muted} numberOfLines={1} style={{ marginTop: 2, fontStyle: 'italic' }}>
                            Context: {c.detected_context}
                          </AppText>
                        )}
                        {c.already_exists && (
                          <View style={styles.existsBadge}>
                            <Icon name="check-circle" size={12} color={colors.success} />
                            <AppText size={11} color={colors.success}>Already in Vocabist</AppText>
                          </View>
                        )}
                      </View>
                      {c.confidence && (
                        <View style={[styles.confBadge, c.confidence === 'high' ? styles.confHigh : c.confidence === 'medium' ? styles.confMed : styles.confLow]}>
                          <AppText size={9} weight="medium" color={c.confidence === 'high' ? colors.success : c.confidence === 'medium' ? colors.warning : colors.error}>
                            {c.confidence.toUpperCase()}
                          </AppText>
                        </View>
                      )}
                    </View>
                  </Pressable>
                ))}

                {selectedCount > 0 && (
                  <Button
                    testID="visual-import"
                    label={importing ? "Importing..." : `Send ${selectedCount} words to review`}
                    onPress={importSelected}
                    disabled={importing}
                    variant="primary"
                    icon="check-all"
                  />
                )}
              </>
            )}

            {extracted && candidates.length === 0 && (
              <View style={styles.emptyResults}>
                <Icon name="text-search" size={32} color={colors.muted} />
                <AppText size={14} color={colors.muted} style={{ marginTop: 8, textAlign: 'center' }}>
                  No useful vocabulary found. Try a different image with more text content.
                </AppText>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  container: { flex: 1, backgroundColor: t.colors.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: t.spacing.lg,
    paddingVertical: t.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: t.colors.divider,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: t.spacing.lg, paddingBottom: 40, gap: 16 },
  pickSection: { alignItems: 'center', paddingVertical: 40 },
  pickIcon: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: t.colors.brandTertiary,
    alignItems: 'center', justifyContent: 'center',
  },
  btnRow: { flexDirection: 'row', gap: 12, marginTop: 24, width: '100%' },
  previewContainer: {
    borderRadius: t.radius.lg,
    overflow: 'hidden',
    backgroundColor: t.colors.surfaceTertiary,
  },
  previewImage: { width: '100%', height: 200, borderRadius: t.radius.lg },
  changeBtn: {
    position: 'absolute', top: 8, right: 8,
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.9)',
    alignItems: 'center', justifyContent: 'center',
  },
  loadingBox: { alignItems: 'center', paddingVertical: 24 },
  resultsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  candidateCard: {
    backgroundColor: t.colors.surfaceSecondary,
    borderRadius: t.radius.md,
    borderWidth: 1,
    borderColor: t.colors.border,
    padding: t.spacing.md,
  },
  candidateExisting: { opacity: 0.7, borderColor: t.colors.borderStrong },
  candidateSelected: { borderColor: t.colors.brand, backgroundColor: t.colors.brandTertiary + '30' },
  candidateRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  checkbox: {
    width: 22, height: 22, borderRadius: 6,
    borderWidth: 2, borderColor: t.colors.border,
    alignItems: 'center', justifyContent: 'center', marginTop: 2,
  },
  checkboxActive: { backgroundColor: t.colors.brand, borderColor: t.colors.brand },
  cefrBadge: {
    paddingHorizontal: 6, paddingVertical: 2,
    backgroundColor: t.colors.brandTertiary,
    borderRadius: t.radius.sm,
  },
  existsBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4,
  },
  confBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: t.radius.sm },
  confHigh: { backgroundColor: '#E7F5EC' },
  confMed: { backgroundColor: '#FFF4E0' },
  confLow: { backgroundColor: '#FFE8E8' },
  emptyResults: { alignItems: 'center', paddingVertical: 32 },
}));
