import {ScrollView, StyleSheet, Text, View} from 'react-native';

import {PrimaryButton, ScreenHeader, useBrain, useSnapshot, useTheme} from '../ui';
import {useNavigation} from '@react-navigation/native';

const ROWS: {feature: string; free: boolean; premium: boolean}[] = [
  {feature: 'General Chat', free: true, premium: true},
  {feature: 'On-device Privacy', free: true, premium: true},
  {feature: 'Lifelong Memory', free: false, premium: true},
  {feature: 'RAG over files', free: false, premium: true},
  {feature: 'Decision Simulator', free: false, premium: true},
  {feature: 'Analytics & Insights', free: false, premium: true},
  {feature: 'Shield (Safety layer)', free: false, premium: true},
];

export function CompareScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const navigation = useNavigation();
  const premium = snapshot.user?.plan === 'premium';

  return (
    <ScrollView style={{backgroundColor: theme.bg}} contentContainerStyle={styles.content}>
      <ScreenHeader title="Free vs Premium" onBack={() => navigation.goBack()} />
      <View style={[styles.hero, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.heroTitle, {color: theme.text}]}>Go further with Encefalus</Text>
        <Text style={[styles.heroBody, {color: theme.muted}]}>
          Keep using local AI, or upgrade to the full Digital Brain on the web.
        </Text>
      </View>
      <View style={[styles.table, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <View style={styles.headerRow}>
          <Text style={[styles.head, {color: theme.muted, flex: 1.4}]}>Feature</Text>
          <Text style={[styles.head, {color: theme.muted, flex: 1}]}>Free (Local AI)</Text>
          <Text style={[styles.head, {color: theme.muted, flex: 1}]}>Premium (Digital Brain)</Text>
        </View>
        {ROWS.map(row => (
          <View key={row.feature} style={[styles.headerRow, {borderTopColor: theme.border, borderTopWidth: 1}]}>
            <Text style={[styles.cell, {color: theme.text, flex: 1.4}]}>{row.feature}</Text>
            <Text style={[styles.cell, {color: row.free ? theme.green : theme.muted, flex: 1}]}>{row.free ? '✓' : '—'}</Text>
            <Text style={[styles.cell, {color: row.premium ? theme.green : theme.muted, flex: 1}]}>{row.premium ? '✓' : '—'}</Text>
          </View>
        ))}
      </View>
      {premium ? (
        <Text style={[styles.note, {color: theme.text}]}>The Digital Brain is the web app.</Text>
      ) : snapshot.confirmUpgrade ? (
        <PrimaryButton label="Confirm upgrade" onPress={() => void brain.upgrade()} />
      ) : (
        <PrimaryButton label="Upgrade to Premium" onPress={() => brain.askUpgrade()} />
      )}
      <Text style={[styles.footer, {color: theme.muted}]}>Use the web app for memory, RAG, analytics and more.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, gap: 14},
  hero: {borderRadius: 16, borderWidth: 1, padding: 16, gap: 6},
  heroTitle: {fontSize: 18, fontWeight: '700'},
  heroBody: {fontSize: 14, lineHeight: 20},
  table: {borderRadius: 16, borderWidth: 1, overflow: 'hidden'},
  headerRow: {flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 10, gap: 6},
  head: {fontSize: 11, fontWeight: '700'},
  cell: {fontSize: 13},
  note: {fontSize: 15, fontWeight: '600'},
  footer: {textAlign: 'center', fontSize: 12},
});
