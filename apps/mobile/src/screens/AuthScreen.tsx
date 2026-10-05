import {useState} from 'react';
import {Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';

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
    <ScrollView style={{backgroundColor: theme.bg}} contentContainerStyle={styles.content}>
      <View style={styles.brand}>
        <Mark size={42} />
        <View>
          <Text style={[styles.name, {color: theme.text}]}>Encefalus</Text>
          <Text style={[styles.tag, {color: theme.muted}]}>AI-Augmented Brain</Text>
        </View>
      </View>
      <Text style={[styles.pitch, {color: theme.muted}]}>
        Your memories. Sharper decisions.{'\n'}A more intentional you.
      </Text>
      <View style={[styles.segment, {backgroundColor: theme.sunken}]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Sign in"
          onPress={() => setMode('sign-in')}
          style={[styles.segmentItem, mode === 'sign-in' && {backgroundColor: theme.card}]}>
          <Text style={[styles.segmentText, {color: theme.text}]}>Sign in</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Sign up"
          onPress={() => setMode('sign-up')}
          style={[styles.segmentItem, mode === 'sign-up' && {backgroundColor: theme.card}]}>
          <Text style={[styles.segmentText, {color: mode === 'sign-up' ? theme.text : theme.muted}]}>Sign up</Text>
        </Pressable>
      </View>
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
          <Pressable accessibilityRole="button" accessibilityLabel="Show password" onPress={() => setShowPassword(value => !value)}>
            <Text style={{color: theme.muted}}>{showPassword ? 'Hide' : 'Show'}</Text>
          </Pressable>
        }
      />
      {snapshot.error ? <Text style={[styles.error, {color: theme.danger}]}>{snapshot.error}</Text> : null}
      <PrimaryButton label="Continue" onPress={() => void submit()} />
      <View style={[styles.privacy, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Text style={[styles.privacyTitle, {color: theme.text}]}>Runs private. Built for your personal AI.</Text>
        <Text style={[styles.privacyBody, {color: theme.muted}]}>
          Your data stays on your device. You control what to sync.
        </Text>
      </View>
      <Text style={[styles.footer, {color: theme.muted}]}>
        Free local AI on iPhone · Premium Digital Brain on web
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {paddingHorizontal: 22, paddingTop: 12, paddingBottom: 32, gap: 16},
  brand: {flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10},
  name: {fontSize: 28, fontWeight: '700'},
  tag: {fontSize: 13},
  pitch: {textAlign: 'center', fontSize: 16, lineHeight: 22},
  segment: {flexDirection: 'row', borderRadius: 16, padding: 4},
  segmentItem: {flex: 1, minHeight: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center'},
  segmentText: {fontSize: 15, fontWeight: '600'},
  error: {fontSize: 14},
  privacy: {borderRadius: 16, borderWidth: 1, padding: 14, gap: 4},
  privacyTitle: {fontSize: 14, fontWeight: '700'},
  privacyBody: {fontSize: 13, lineHeight: 18},
  footer: {textAlign: 'center', fontSize: 12},
});
