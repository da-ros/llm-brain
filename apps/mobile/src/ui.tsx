import {createContext, useContext, useEffect, useState, type ReactNode} from 'react';
import {Image, Pressable, StyleSheet, Text, TextInput, View} from 'react-native';

import {Brain, type Snapshot} from './brain';
import {light, type Palette} from './theme';

const mark = require('./assets/encefalus-mark.png');

export const BrainContext = createContext<Brain | null>(null);
export const ThemeContext = createContext<Palette>(light);

export function useBrain(): Brain {
  const brain = useContext(BrainContext);
  if (!brain) {
    throw new Error('Brain is missing');
  }
  return brain;
}

export function useTheme(): Palette {
  return useContext(ThemeContext);
}

export function useSnapshot(brain: Brain): Snapshot {
  const [snapshot, setSnapshot] = useState(brain.snapshot);
  useEffect(() => brain.subscribe(setSnapshot), [brain]);
  return snapshot;
}

export function Mark({size = 36}: {size?: number}) {
  return <Image source={mark} style={{width: size, height: size}} accessibilityIgnoresInvertColors />;
}

export function PrimaryButton({
  label,
  onPress,
  icon,
}: {
  label: string;
  onPress: () => void;
  icon?: string;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.primary, {backgroundColor: theme.primary}]}>
      {icon ? <Text style={[styles.primaryText, {color: theme.primaryText}]}>{icon}</Text> : null}
      <Text style={[styles.primaryText, {color: theme.primaryText, flex: 1, textAlign: 'center'}]}>{label}</Text>
      <Text style={[styles.primaryText, {color: theme.primaryText}]}>→</Text>
    </Pressable>
  );
}

export function Field({
  label,
  value,
  onChangeText,
  placeholder,
  secure,
  trailing,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  secure?: boolean;
  trailing?: ReactNode;
}) {
  const theme = useTheme();
  return (
    <View style={styles.field}>
      <Text style={[styles.label, {color: theme.text}]}>{label}</Text>
      <View style={[styles.inputRow, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={theme.muted}
          secureTextEntry={secure}
          autoCapitalize="none"
          style={[styles.input, {color: theme.text}]}
        />
        {trailing}
      </View>
    </View>
  );
}

export function ScreenHeader({
  title,
  onBack,
  left,
  right,
}: {
  title: string;
  onBack?: () => void;
  left?: ReactNode;
  right?: ReactNode;
}) {
  const theme = useTheme();
  return (
    <View style={styles.header}>
      {onBack ? (
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={onBack} style={styles.iconButton}>
          <Text style={[styles.icon, {color: theme.text}]}>‹</Text>
        </Pressable>
      ) : (
        left
      )}
      <Text style={[styles.headerTitle, {color: theme.text}]}>{title}</Text>
      {right ?? <View style={styles.iconButton} />}
    </View>
  );
}

export function MutedButton({
  title,
  subtitle,
  onPress,
  label,
}: {
  title: string;
  subtitle: string;
  onPress: () => void;
  label?: string;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label ?? title}
      onPress={onPress}
      style={[styles.mutedButton, {backgroundColor: theme.sunken}]}>
      <Text style={[styles.rowTitle, {color: theme.text}]}>{title}</Text>
      <Text style={[styles.rowSub, {color: theme.muted}]}>{subtitle}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  primary: {
    minHeight: 52,
    borderRadius: 16,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
  },
  primaryText: {fontSize: 16, fontWeight: '600'},
  field: {gap: 8},
  label: {fontSize: 14, fontWeight: '600'},
  inputRow: {
    minHeight: 52,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
  },
  input: {flex: 1, fontSize: 16, paddingVertical: 12},
  header: {minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  headerTitle: {fontSize: 17, fontWeight: '700'},
  iconButton: {width: 40, height: 40, alignItems: 'center', justifyContent: 'center'},
  icon: {fontSize: 28, lineHeight: 30},
  mutedButton: {borderRadius: 16, padding: 16, gap: 4},
  rowTitle: {fontSize: 16, fontWeight: '600'},
  rowSub: {fontSize: 13},
});
