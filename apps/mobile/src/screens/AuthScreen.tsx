import {useState} from 'react';
import {Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';

import {Glass} from '../glass';
import {Icon} from '../icons';
import {typeScale as scale} from '../theme';
import {Field, Mark, PrimaryButton, useBrain, useSnapshot, useTheme} from '../ui';

export function AuthScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  async function submit() {
    if (mode === 'sign-up') {
      await brain.signUp(name, email, password);
      return;
    }
    await brain.signIn(email, password);
  }

  return (
    <ScrollView
      style={{backgroundColor: theme.bg}}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled">
      <View style={styles.brand}>
        <Mark size={46} />
        <View>
          <Text style={[styles.name, {color: theme.text}]}>Encefalus</Text>
          <Text style={[styles.tag, {color: theme.muted}]}>AI-Augmented Brain</Text>
        </View>
      </View>
      <Text style={[styles.pitch, {color: theme.muted}]}>
        Your memories. Sharper decisions.{'\n'}A more intentional you.
      </Text>
      <Glass radius={20} contentStyle={styles.segment}>
        <Segment label="Sign in" active={mode === 'sign-in'} onPress={() => setMode('sign-in')} />
        <Segment label="Sign up" active={mode === 'sign-up'} onPress={() => setMode('sign-up')} />
      </Glass>
      {mode === 'sign-up' ? (
        <Field label="Name" value={name} onChangeText={setName} placeholder="Your name" />
      ) : null}
      <Field label="Email" value={email} onChangeText={setEmail} placeholder="you@company.com" />
      <Field
        label="Password"
        value={password}
        onChangeText={setPassword}
        placeholder="Enter your password"
        secure={!showPassword}
        trailing={
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Show password"
            onPress={() => setShowPassword(value => !value)}
            style={styles.eye}>
            {showPassword ? (
              <Icon.show size={22} color={theme.muted} strokeWidth={2} />
            ) : (
              <Icon.hide size={22} color={theme.muted} strokeWidth={2} />
            )}
          </Pressable>
        }
      />
      {snapshot.error ? <Text style={[styles.error, {color: theme.danger}]}>{snapshot.error}</Text> : null}
      <PrimaryButton label="Continue" onPress={() => void submit()} />
      <Glass radius={20} contentStyle={styles.privacy}>
        <View style={[styles.privacyIcon, {backgroundColor: theme.greenSoft}]}>
          <Icon.privacy size={20} color={theme.green} strokeWidth={2.2} />
        </View>
        <View style={styles.privacyText}>
          <Text style={[styles.privacyTitle, {color: theme.text}]}>Runs private. Built for your personal AI.</Text>
          <Text style={[styles.privacyBody, {color: theme.muted}]}>
            Your data stays on your device. You control what to sync.
          </Text>
        </View>
      </Glass>
      <Text style={[styles.footer, {color: theme.muted}]}>
        Free local AI on iPhone · Premium Digital Brain on web
      </Text>
    </ScrollView>
  );
}

function Segment({label, active, onPress}: {label: string; active: boolean; onPress: () => void}) {
  const theme = useTheme();
  if (!active) {
    return (
      <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.segmentItem}>
        <Text style={[styles.segmentText, {color: theme.muted}]}>{label}</Text>
      </Pressable>
    );
  }
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.segmentSlot}>
      <Glass radius={16} strong floating contentStyle={styles.segmentItem}>
        <Text style={[styles.segmentText, {color: theme.text}]}>{label}</Text>
      </Glass>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: {paddingHorizontal: 22, paddingTop: 16, paddingBottom: 36, gap: 18},
  brand: {flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12},
  name: {fontSize: scale.display, fontWeight: '700'},
  tag: {fontSize: scale.caption},
  pitch: {textAlign: 'center', fontSize: scale.body, lineHeight: 24},
  segment: {flexDirection: 'row', padding: 5, gap: 5},
  segmentSlot: {flex: 1},
  segmentItem: {flex: 1, minHeight: 46, alignItems: 'center', justifyContent: 'center'},
  segmentText: {fontSize: scale.body, fontWeight: '700'},
  eye: {width: 32, height: 32, alignItems: 'center', justifyContent: 'center'},
  error: {fontSize: scale.caption},
  privacy: {flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16},
  privacyIcon: {width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center'},
  privacyText: {flex: 1, gap: 3},
  privacyTitle: {fontSize: scale.caption, fontWeight: '700'},
  privacyBody: {fontSize: scale.micro, lineHeight: 19},
  footer: {textAlign: 'center', fontSize: scale.micro},
});
