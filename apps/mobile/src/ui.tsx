import {Image, Pressable, StyleSheet, Text, TextInput, View} from 'react-native';

import {Glass} from './glass';
import {Icon} from './icons';
import {typeScale as scale, type Palette} from './theme';
import {BrainContext, ThemeContext, useBrain, useSnapshot, useTheme} from './context';
import type {ComponentType, ReactNode} from 'react';
import type {IconProps} from './icons';

const mark = require('./assets/encefalus-mark.png');

export {BrainContext, ThemeContext, useBrain, useSnapshot, useTheme};
export type {Palette};

export function Mark({size = 36}: {size?: number}) {
  return <Image source={mark} style={{width: size, height: size}} accessibilityIgnoresInvertColors />;
}

/** The Encefalus badge that sits beside an answer from the model. */
export function MarkBadge({size = 36}: {size?: number}) {
  return (
    <Glass radius={size / 2} style={{width: size, height: size}} contentStyle={styles.badge} strong fill>
      <Mark size={size * 0.62} />
    </Glass>
  );
}

export function PrimaryButton({label, onPress}: {label: string; onPress: () => void}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({pressed}) => [styles.primary, {backgroundColor: theme.primary, opacity: pressed ? 0.88 : 1}]}>
      <View style={styles.primarySlot} />
      <Text style={[styles.primaryText, {color: theme.primaryText}]}>{label}</Text>
      <View style={styles.primarySlot}>
        <Icon.forward size={22} color={theme.primaryText} strokeWidth={2.6} />
      </View>
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
      <Glass radius={18} contentStyle={styles.inputRow}>
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
      </Glass>
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
          <Icon.back size={26} color={theme.text} strokeWidth={2.4} />
        </Pressable>
      ) : (
        left ?? <View style={styles.iconButton} />
      )}
      <Text style={[styles.headerTitle, {color: theme.text}]}>{title}</Text>
      {right ?? <View style={styles.iconButton} />}
    </View>
  );
}

/** A glass tile with a leading icon, a title, and a quiet second line. */
export function MutedButton({
  title,
  subtitle,
  onPress,
  label,
  icon: Glyph,
}: {
  title: string;
  subtitle: string;
  onPress: () => void;
  label?: string;
  icon?: ComponentType<IconProps>;
}) {
  const theme = useTheme();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label ?? title} onPress={onPress}>
      <Glass radius={20} contentStyle={styles.tile}>
        {Glyph ? <Glyph size={22} color={theme.text} strokeWidth={2} /> : null}
        <View style={styles.tileText}>
          <Text style={[styles.rowTitle, {color: theme.text}]}>{title}</Text>
          <Text style={[styles.rowSub, {color: theme.muted}]}>{subtitle}</Text>
        </View>
        <Icon.next size={20} color={theme.muted} strokeWidth={2.2} />
      </Glass>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  badge: {alignItems: 'center', justifyContent: 'center'},
  primary: {
    minHeight: 58,
    borderRadius: 20,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  primarySlot: {width: 24, alignItems: 'center'},
  primaryText: {fontSize: scale.body, fontWeight: '700'},
  field: {gap: 8},
  label: {fontSize: scale.label, fontWeight: '600'},
  inputRow: {minHeight: 58, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 8},
  input: {flex: 1, fontSize: scale.body, paddingVertical: 14},
  header: {minHeight: 52, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  headerTitle: {fontSize: scale.headline, fontWeight: '700'},
  iconButton: {width: 44, height: 44, alignItems: 'center', justifyContent: 'center'},
  tile: {minHeight: 72, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 14},
  tileText: {flex: 1, gap: 2},
  rowTitle: {fontSize: scale.body, fontWeight: '600'},
  rowSub: {fontSize: scale.micro},
});
