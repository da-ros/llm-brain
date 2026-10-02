import {Pressable, ScrollView, StyleSheet, Switch, Text, View} from 'react-native';

import {formatBytes} from '../bytes';
import {APP_VERSION} from '../config';
import {PrimaryButton, ScreenHeader, useBrain, useSnapshot, useTheme} from '../ui';
import {useNavigation} from '@react-navigation/native';

export function SettingsScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const navigation = useNavigation();
  const premium = snapshot.user?.plan === 'premium';
  const onDevice = brain.onDevice();

  return (
    <ScrollView style={{backgroundColor: theme.bg}} contentContainerStyle={styles.content}>
      <ScreenHeader title="Settings" onBack={() => navigation.goBack()} />
      <Text style={[styles.section, {color: theme.muted}]}>APPEARANCE</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Theme"
        onPress={() => brain.cycleTheme()}
        style={[styles.row, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>Theme</Text>
        <Text style={{color: theme.muted}}>{labelFor(snapshot.theme)} ›</Text>
      </Pressable>
      <Text style={[styles.section, {color: theme.muted}]}>PRIVACY</Text>
      <View style={[styles.block, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <View style={styles.rowBetween}>
          <Text style={[styles.rowTitle, {color: theme.text}]}>Keep data on device</Text>
          <Switch
            accessibilityLabel="Keep data on device"
            value={onDevice}
            disabled={!premium}
            onValueChange={value => brain.setKeepOnDevice(value)}
            trackColor={{true: theme.primary, false: theme.sunken}}
          />
        </View>
        <Text style={[styles.sub, {color: theme.muted}]}>
          {onDevice
            ? 'Conversations and files stay on this iPhone. Nothing is sent to the cloud.'
            : 'Turns use the Digital Brain with RAG and memory.'}
        </Text>
      </View>
      <Text style={[styles.section, {color: theme.muted}]}>LOCAL DATA</Text>
      <View style={[styles.block, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <View style={styles.rowBetween}>
          <Text style={[styles.rowTitle, {color: theme.text}]}>App Storage</Text>
          <Text style={{color: theme.muted}}>{formatBytes(brain.measuredStorage())}</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="Clear All Data" onPress={() => brain.askClear()}>
          <Text style={[styles.rowTitle, {color: theme.text}]}>Clear All Data</Text>
          <Text style={[styles.sub, {color: theme.muted}]}>
            Remove conversations, cache, and model files from this device.
          </Text>
        </Pressable>
        {snapshot.confirmClear ? (
          <View style={styles.confirmRow}>
            <Pressable accessibilityRole="button" accessibilityLabel="Cancel clear" onPress={() => brain.cancelClear()}>
              <Text style={{color: theme.muted}}>Cancel</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Confirm clear" onPress={() => void brain.clearAll()}>
              <Text style={{color: theme.danger}}>Remove</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
      <Text style={[styles.section, {color: theme.muted}]}>SUPPORT</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Help & FAQ"
        onPress={() => navigation.navigate('Help')}
        style={[styles.row, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>Help & FAQ</Text>
        <Text style={{color: theme.muted}}>›</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="About Encefalus"
        onPress={() => navigation.navigate('About')}
        style={[styles.row, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>About Encefalus</Text>
        <Text style={{color: theme.muted}}>{APP_VERSION}</Text>
      </Pressable>
      {premium ? (
        <Text style={[styles.note, {color: theme.text}]}>The Digital Brain is the web app.</Text>
      ) : snapshot.confirmUpgrade ? (
        <PrimaryButton label="Confirm upgrade" onPress={() => void brain.upgrade()} />
      ) : (
        <PrimaryButton label="Upgrade to Premium" onPress={() => brain.askUpgrade()} />
      )}
      <Text style={[styles.footer, {color: theme.muted}]}>
        Premium runs in your secure web app with memory, RAG, analytics, simulator and shield.
      </Text>
      {snapshot.notice ? <Text style={{color: theme.muted}}>{snapshot.notice}</Text> : null}
      <Pressable accessibilityRole="button" accessibilityLabel="Sign out" onPress={() => void brain.signOut()}>
        <Text style={[styles.signOut, {color: theme.danger}]}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

function labelFor(theme: 'system' | 'light' | 'dark'): string {
  if (theme === 'light') {
    return 'Light';
  }
  if (theme === 'dark') {
    return 'Dark';
  }
  return 'System';
}

export function HelpScreen() {
  const theme = useTheme();
  const navigation = useNavigation();
  return (
    <ScrollView style={{backgroundColor: theme.bg}} contentContainerStyle={styles.content}>
      <ScreenHeader title="Help & FAQ" onBack={() => navigation.goBack()} />
      <Text style={[styles.rowTitle, {color: theme.text}]}>Where do free answers run?</Text>
      <Text style={[styles.sub, {color: theme.muted}]}>
        On this iPhone, with the base Qwen 3.5 4B model. Nothing from that chat is sent to the cloud.
      </Text>
      <Text style={[styles.rowTitle, {color: theme.text}]}>What is Premium?</Text>
      <Text style={[styles.sub, {color: theme.muted}]}>
        Keep data on device uses your personal model. Turning it off uses the Digital Brain, which is the web app with memory, RAG, analytics, the simulator, and shield.
      </Text>
    </ScrollView>
  );
}

export function AboutScreen() {
  const theme = useTheme();
  const navigation = useNavigation();
  return (
    <ScrollView style={{backgroundColor: theme.bg}} contentContainerStyle={styles.content}>
      <ScreenHeader title="About Encefalus" onBack={() => navigation.goBack()} />
      <Text style={[styles.hero, {color: theme.text}]}>Encefalus</Text>
      <Text style={[styles.sub, {color: theme.muted}]}>AI-Augmented Brain</Text>
      <Text style={[styles.sub, {color: theme.muted}]}>{APP_VERSION}</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, gap: 10, paddingBottom: 32},
  section: {fontSize: 12, fontWeight: '700', marginTop: 8},
  row: {
    minHeight: 52,
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  block: {borderRadius: 16, borderWidth: 1, padding: 14, gap: 8},
  rowBetween: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  rowTitle: {fontSize: 16, fontWeight: '600'},
  sub: {fontSize: 13, lineHeight: 18},
  confirmRow: {flexDirection: 'row', justifyContent: 'flex-end', gap: 16},
  note: {fontSize: 15, fontWeight: '600', marginTop: 8},
  footer: {textAlign: 'center', fontSize: 12, lineHeight: 18},
  signOut: {textAlign: 'center', fontSize: 16, fontWeight: '600', marginTop: 8},
  hero: {fontSize: 28, fontWeight: '700'},
});
