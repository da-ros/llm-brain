import {Pressable, ScrollView, StyleSheet, Switch, Text, View} from 'react-native';

import {formatBytes} from '../bytes';
import {APP_VERSION} from '../config';
import {Glass} from '../glass';
import {Icon} from '../icons';
import {typeScale as scale} from '../theme';
import {PrimaryButton, ScreenHeader, useBrain, useSnapshot, useTheme} from '../ui';
import {useNavigation} from '@react-navigation/native';
import type {ComponentType, ReactNode} from 'react';
import type {IconProps} from '../icons';

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
      <Row label="Theme" title="Theme" icon={Icon.theme} onPress={() => brain.cycleTheme()}>
        <Text style={[styles.value, {color: theme.muted}]}>{labelFor(snapshot.theme)}</Text>
        <Icon.next size={20} color={theme.muted} strokeWidth={2.2} />
      </Row>
      <Text style={[styles.section, {color: theme.muted}]}>PRIVACY</Text>
      <Glass radius={20} contentStyle={styles.block}>
        <View style={styles.rowBetween}>
          <View style={styles.titleRow}>
            <Icon.privacy size={22} color={theme.text} strokeWidth={2} />
            <Text style={[styles.rowTitle, {color: theme.text}]}>Keep data on device</Text>
          </View>
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
      </Glass>
      <Text style={[styles.section, {color: theme.muted}]}>LOCAL DATA</Text>
      <Glass radius={20} contentStyle={styles.block}>
        <View style={styles.rowBetween}>
          <View style={styles.titleRow}>
            <Icon.storage size={22} color={theme.text} strokeWidth={2} />
            <Text style={[styles.rowTitle, {color: theme.text}]}>App Storage</Text>
          </View>
          <Text style={[styles.value, {color: theme.muted}]}>{formatBytes(brain.measuredStorage())}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Clear All Data"
          onPress={() => brain.askClear()}
          style={styles.clearBlock}>
          <View style={styles.titleRow}>
            <Icon.erase size={22} color={theme.text} strokeWidth={2} />
            <Text style={[styles.rowTitle, {color: theme.text}]}>Clear All Data</Text>
          </View>
          <Text style={[styles.sub, {color: theme.muted}]}>
            Remove conversations, cache, and model files from this device.
          </Text>
        </Pressable>
        {snapshot.confirmClear ? (
          <View style={styles.confirmRow}>
            <Pressable accessibilityRole="button" accessibilityLabel="Cancel clear" onPress={() => brain.cancelClear()}>
              <Text style={[styles.value, {color: theme.muted}]}>Cancel</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Confirm clear" onPress={() => void brain.clearAll()}>
              <Text style={[styles.value, {color: theme.danger}]}>Remove</Text>
            </Pressable>
          </View>
        ) : null}
      </Glass>
      <Text style={[styles.section, {color: theme.muted}]}>SUPPORT</Text>
      <Row label="Help & FAQ" title="Help & FAQ" icon={Icon.help} onPress={() => navigation.navigate('Help')}>
        <Icon.next size={20} color={theme.muted} strokeWidth={2.2} />
      </Row>
      <Row
        label="About Encefalus"
        title="About Encefalus"
        icon={Icon.about}
        onPress={() => navigation.navigate('About')}>
        <Text style={[styles.value, {color: theme.muted}]}>{APP_VERSION}</Text>
      </Row>
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
      {snapshot.notice ? <Text style={[styles.sub, {color: theme.muted}]}>{snapshot.notice}</Text> : null}
      <Pressable accessibilityRole="button" accessibilityLabel="Sign out" onPress={() => void brain.signOut()}>
        <Text style={[styles.signOut, {color: theme.danger}]}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

function Row({
  label,
  title,
  icon: Glyph,
  onPress,
  children,
}: {
  label: string;
  title: string;
  icon: ComponentType<IconProps>;
  onPress: () => void;
  children?: ReactNode;
}) {
  const theme = useTheme();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress}>
      <Glass radius={20} contentStyle={styles.row}>
        <View style={styles.titleRow}>
          <Glyph size={22} color={theme.text} strokeWidth={2} />
          <Text style={[styles.rowTitle, {color: theme.text}]}>{title}</Text>
        </View>
        <View style={styles.trailing}>{children}</View>
      </Glass>
    </Pressable>
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
      <Glass radius={20} contentStyle={styles.block}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>Where do free answers run?</Text>
        <Text style={[styles.sub, {color: theme.muted}]}>
          On this iPhone, with the base Qwen 3.5 4B model. Nothing from that chat is sent to the cloud.
        </Text>
      </Glass>
      <Glass radius={20} contentStyle={styles.block}>
        <Text style={[styles.rowTitle, {color: theme.text}]}>What is Premium?</Text>
        <Text style={[styles.sub, {color: theme.muted}]}>
          Keep data on device uses your personal model. Turning it off uses the Digital Brain, which is the web app with memory, RAG, analytics, the simulator, and shield.
        </Text>
      </Glass>
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
  content: {paddingHorizontal: 18, paddingTop: 4, paddingBottom: 36, gap: 10},
  section: {fontSize: scale.micro, fontWeight: '700', letterSpacing: 0.6, marginTop: 10},
  row: {
    minHeight: 60,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  trailing: {flexDirection: 'row', alignItems: 'center', gap: 6},
  block: {padding: 16, gap: 18},
  clearBlock: {gap: 10},
  rowBetween: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12},
  titleRow: {flexDirection: 'row', alignItems: 'center', gap: 12, flexShrink: 1},
  rowTitle: {fontSize: scale.body, fontWeight: '600'},
  value: {fontSize: scale.caption},
  sub: {fontSize: scale.caption, lineHeight: 21},
  confirmRow: {flexDirection: 'row', justifyContent: 'flex-end', gap: 18},
  note: {fontSize: scale.body, fontWeight: '600', marginTop: 8},
  footer: {textAlign: 'center', fontSize: scale.micro, lineHeight: 19},
  signOut: {textAlign: 'center', fontSize: scale.body, fontWeight: '600', marginTop: 8},
  hero: {fontSize: scale.display, fontWeight: '700'},
});
