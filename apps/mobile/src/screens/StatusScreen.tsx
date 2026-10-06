import {ScrollView, StyleSheet, Text, View} from 'react-native';

import {formatBytes, formatDuration} from '../bytes';
import {STORAGE_BUDGET_BYTES} from '../config';
import {Glass} from '../glass';
import {Icon} from '../icons';
import {typeScale as scale} from '../theme';
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
      <Glass radius={22} contentStyle={styles.card}>
        <Text style={[styles.model, {color: theme.text}]}>Qwen 3.5 4B</Text>
        <Text style={[styles.meta, {color: theme.muted}]}>Open source LLM · 4.0B parameters</Text>
        <Text style={[styles.body, {color: theme.text}]}>
          A capable, efficient model for everyday questions, writing, and analysis.
        </Text>
        {personalMissing ? (
          <Text style={[styles.body, {color: theme.muted}]}>Your personal model is not built yet.</Text>
        ) : null}
      </Glass>
      <Glass radius={22} contentStyle={styles.card}>
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
      </Glass>
      <Glass radius={22} contentStyle={styles.card}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>Status</Text>
        <StorageRow label="Model ready" value={pack ? 'On Device' : 'Not ready'} />
        <StorageRow label="Offline ready" value={pack ? 'Works without internet' : 'Download the model first'} />
        <StorageRow
          label="Average response time (short responses)"
          value={average == null ? '—' : formatDuration(average)}
        />
      </Glass>
      <MutedButton
        title="Reinstall Model"
        subtitle="Download or update model files"
        icon={Icon.reinstall}
        onPress={() => void brain.reinstall()}
      />
      <MutedButton
        title="Clear Cache"
        subtitle={snapshot.cacheBytes > 0 ? `Free up space (${formatBytes(snapshot.cacheBytes)})` : 'Free up space'}
        icon={Icon.erase}
        onPress={() => void brain.clearCache()}
      />
      {snapshot.error ? <Text style={[styles.body, {color: theme.danger}]}>{snapshot.error}</Text> : null}
      {snapshot.notice ? <Text style={[styles.body, {color: theme.muted}]}>{snapshot.notice}</Text> : null}
    </ScrollView>
  );
}

function StorageRow({label, value}: {label: string; value: string}) {
  const theme = useTheme();
  return (
    <View style={styles.rowBetween}>
      <Text style={[styles.rowLabel, {color: theme.text}]}>{label}</Text>
      <Text style={[styles.rowValue, {color: theme.muted}]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: {paddingHorizontal: 18, paddingTop: 4, paddingBottom: 28, gap: 12},
  card: {padding: 18, gap: 8},
  model: {fontSize: scale.title, fontWeight: '700'},
  meta: {fontSize: scale.caption},
  body: {fontSize: scale.caption, lineHeight: 22},
  rowBetween: {flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center'},
  rowTitle: {fontSize: scale.body, fontWeight: '700'},
  rowLabel: {flex: 1, fontSize: scale.caption},
  rowValue: {flex: 1, fontSize: scale.caption, textAlign: 'right'},
  track: {height: 8, borderRadius: 4, overflow: 'hidden'},
  fill: {height: 8},
});
