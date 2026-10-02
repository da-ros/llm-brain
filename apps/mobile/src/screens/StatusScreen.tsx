import {ScrollView, StyleSheet, Text, View} from 'react-native';

import {formatBytes, formatDuration} from '../bytes';
import {STORAGE_BUDGET_BYTES} from '../config';
import {MutedButton, ScreenHeader, useBrain, useSnapshot, useTheme} from '../ui';
import {useNavigation} from '@react-navigation/native';

export function StatusScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const navigation = useNavigation();
  const pack = brain.onDevice()
    ? snapshot.user?.plan === 'premium'
      ? snapshot.loraPack ?? snapshot.basePack
      : snapshot.basePack
    : snapshot.basePack;
  const modelBytes = pack?.bytes ?? 0;
  const used = modelBytes + snapshot.cacheBytes;
  const ratio = Math.min(1, used / STORAGE_BUDGET_BYTES);
  const average = brain.averageShortMs();
  const personalMissing = snapshot.user?.plan === 'premium' && !snapshot.loraPack;

  return (
    <ScrollView style={{backgroundColor: theme.bg}} contentContainerStyle={styles.content}>
      <ScreenHeader title="Model & Device Status" onBack={() => navigation.goBack()} />
      <View style={[styles.card, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.model, {color: theme.text}]}>Qwen 3.5 4B</Text>
        <Text style={[styles.meta, {color: theme.muted}]}>Open source LLM · 4.0B parameters</Text>
        <Text style={[styles.body, {color: theme.text}]}>
          A capable, efficient model for everyday questions, writing, and analysis.
        </Text>
        {personalMissing ? (
          <Text style={[styles.body, {color: theme.muted}]}>Your personal model is not built yet.</Text>
        ) : null}
      </View>
      <View style={[styles.card, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <View style={styles.rowBetween}>
          <Text style={[styles.rowTitle, {color: theme.text}]}>Model Storage</Text>
          <Text style={{color: theme.muted}}>
            {formatBytes(used)} / {formatBytes(STORAGE_BUDGET_BYTES)}
          </Text>
        </View>
        <View style={[styles.track, {backgroundColor: theme.sunken}]}>
          <View style={[styles.fill, {backgroundColor: theme.primary, width: `${ratio * 100}%`}]} />
        </View>
        <StorageRow label="Model file" value={pack ? `${pack.id} · ${formatBytes(modelBytes)}` : 'Not installed'} />
        <StorageRow label="Cache" value={formatBytes(snapshot.cacheBytes)} />
      </View>
      <View style={[styles.card, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>Status</Text>
        <StorageRow label="Model ready" value={pack ? 'On Device' : 'Not ready'} />
        <StorageRow label="Offline ready" value={pack ? 'Works without internet' : 'Download the model first'} />
        <StorageRow
          label="Average response time (short responses)"
          value={average == null ? '—' : formatDuration(average)}
        />
      </View>
      <MutedButton title="Reinstall Model" subtitle="Download or update model files" onPress={() => void brain.reinstall()} />
      <MutedButton
        title="Clear Cache"
        subtitle={snapshot.cacheBytes > 0 ? `Free up space (${formatBytes(snapshot.cacheBytes)})` : 'Free up space'}
        onPress={() => void brain.clearCache()}
      />
      {snapshot.error ? <Text style={{color: theme.danger}}>{snapshot.error}</Text> : null}
      {snapshot.notice ? <Text style={{color: theme.muted}}>{snapshot.notice}</Text> : null}
    </ScrollView>
  );
}

function StorageRow({label, value}: {label: string; value: string}) {
  const theme = useTheme();
  return (
    <View style={styles.rowBetween}>
      <Text style={{color: theme.text, flex: 1}}>{label}</Text>
      <Text style={{color: theme.muted, flex: 1, textAlign: 'right'}}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, gap: 12},
  card: {borderRadius: 16, borderWidth: 1, padding: 16, gap: 8},
  model: {fontSize: 20, fontWeight: '700'},
  meta: {fontSize: 13},
  body: {fontSize: 14, lineHeight: 20},
  rowBetween: {flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center'},
  rowTitle: {fontSize: 16, fontWeight: '700'},
  track: {height: 8, borderRadius: 4, overflow: 'hidden'},
  fill: {height: 8},
});
