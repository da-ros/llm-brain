import {useState} from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {Glass} from '../glass';
import {Icon} from '../icons';
import {typeScale as scale} from '../theme';
import {Mark, MarkBadge, ScreenHeader, useBrain, useSnapshot, useTheme} from '../ui';
import {useNavigation} from '@react-navigation/native';
import type {ComponentType} from 'react';
import type {IconProps} from '../icons';

export function ChatScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const [menu, setMenu] = useState(false);
  const [draft, setDraft] = useState('');
  const thread = brain.activeThread();
  const onDevice = brain.onDevice();
  const premium = snapshot.user?.plan === 'premium';

  async function send() {
    const ok = await brain.send(draft);
    if (ok) {
      setDraft('');
    }
  }

  return (
    <View style={[styles.screen, {backgroundColor: theme.bg}]}>
      {/* The gap left for the home indicator is already padding, so the
          keyboard only has to make up the difference. */}
      <KeyboardAvoidingView
        style={styles.fill}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={insets.bottom}>
        <View style={[styles.body, {paddingBottom: Math.max(insets.bottom, 12)}]}>
          <ScreenHeader
            title="Local AI Chat"
            left={
              <Pressable accessibilityRole="button" accessibilityLabel="Menu" onPress={() => setMenu(true)} style={styles.iconButton}>
                <Icon.menu size={24} color={theme.text} strokeWidth={2.4} />
              </Pressable>
            }
            right={
              <Pressable accessibilityRole="button" accessibilityLabel="New chat" onPress={() => brain.newThread()} style={styles.iconButton}>
                <Icon.newChat size={24} color={theme.text} strokeWidth={2.4} />
              </Pressable>
            }
          />
          <View style={styles.pillRow}>
            {premium ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={onDevice ? 'On Device' : 'Digital Brain'}
                onPress={() => brain.setKeepOnDevice(!snapshot.keepOnDevice)}>
                <Pill label={onDevice ? 'On Device' : 'Digital Brain'} />
              </Pressable>
            ) : (
              <View accessibilityLabel="On Device">
                <Pill label="On Device" />
              </View>
            )}
          </View>
          <ScrollView style={styles.fill} contentContainerStyle={styles.transcript} keyboardDismissMode="interactive">
            {(thread?.turns ?? []).map((turn, index) =>
              turn.role === 'user' ? (
                <Glass
                  key={`${index}-user`}
                  radius={22}
                  strong
                  style={styles.userBubble}
                  contentStyle={styles.bubblePad}>
                  <Text style={[styles.bubbleText, {color: theme.text}]}>{turn.text}</Text>
                </Glass>
              ) : (
                <View key={`${index}-${turn.role}`} style={styles.assistantRow}>
                  {turn.role === 'assistant' ? <MarkBadge size={34} /> : <View style={styles.badgeGap} />}
                  <Glass radius={22} style={styles.assistantBubble} contentStyle={styles.bubblePad}>
                    <Text style={[styles.bubbleText, {color: turn.role === 'note' ? theme.muted : theme.text}]}>
                      {turn.text}
                    </Text>
                  </Glass>
                </View>
              ),
            )}
            {(thread?.files ?? []).map(file => (
              <View key={file.filename} style={styles.fileRow}>
                <Icon.attach size={14} color={theme.muted} strokeWidth={2} />
                <Text style={[styles.fileChip, {color: theme.muted}]}>{file.filename}</Text>
              </View>
            ))}
          </ScrollView>
          {snapshot.error ? <Text style={[styles.error, {color: theme.danger}]}>{snapshot.error}</Text> : null}
          <Glass radius={28} floating strong contentStyle={styles.composer}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Attach file"
              onPress={() => void brain.attach('file')}
              style={styles.composerButton}>
              <Icon.attach size={22} color={theme.muted} strokeWidth={2} />
            </Pressable>
            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder="Ask anything..."
              placeholderTextColor={theme.muted}
              style={[styles.input, {color: theme.text}]}
              multiline
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Send"
              onPress={() => void send()}
              style={({pressed}) => [styles.send, {backgroundColor: theme.primary, opacity: pressed ? 0.85 : 1}]}>
              <Icon.send size={24} color={theme.primaryText} strokeWidth={3} />
            </Pressable>
          </Glass>
          <Text style={[styles.footer, {color: theme.muted}]}>
            {onDevice
              ? 'Runs completely on your iPhone. No cloud required.'
              : 'Digital Brain uses RAG and memory in the web app.'}
          </Text>
        </View>
      </KeyboardAvoidingView>
      {menu ? (
        <View style={styles.overlay}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close menu"
            onPress={() => setMenu(false)}
            style={[styles.scrim, {backgroundColor: theme.scrim}]}
          />
          <Glass
            radius={0}
            strong
            floating
            fill
            style={styles.drawer}
            surfaceStyle={styles.drawerSurface}
            contentStyle={styles.drawerBody}>
            <View style={styles.drawerBrand}>
              <Mark size={30} />
              <Text style={[styles.drawerName, {color: theme.text}]}>Encefalus</Text>
            </View>
            <MenuRow
              label="Model & Device Status"
              icon={Icon.status}
              onPress={() => navigation.navigate('Status')}
              close={() => setMenu(false)}
            />
            <MenuRow
              label="Free vs Premium"
              icon={Icon.premium}
              onPress={() => navigation.navigate('Compare')}
              close={() => setMenu(false)}
            />
            <MenuRow
              label="Settings"
              icon={Icon.settings}
              onPress={() => navigation.navigate('Settings')}
              close={() => setMenu(false)}
            />
          </Glass>
        </View>
      ) : null}
    </View>
  );
}

function Pill({label}: {label: string}) {
  const theme = useTheme();
  return (
    <Glass radius={999} contentStyle={styles.pill}>
      <View style={[styles.dot, {backgroundColor: theme.green}]} />
      <Text style={[styles.pillText, {color: theme.green}]}>{label}</Text>
    </Glass>
  );
}

function MenuRow({
  label,
  icon: Glyph,
  onPress,
  close,
}: {
  label: string;
  icon: ComponentType<IconProps>;
  onPress: () => void;
  close: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => {
        close();
        onPress();
      }}
      style={({pressed}) => [styles.menuRow, pressed && {backgroundColor: theme.glass}]}>
      <Glyph size={20} color={theme.text} strokeWidth={2} />
      <Text style={[styles.menuText, {color: theme.text}]}>{label}</Text>
      <Icon.next size={18} color={theme.muted} strokeWidth={2.2} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {flex: 1},
  fill: {flex: 1},
  body: {flex: 1, paddingHorizontal: 18, paddingTop: 4},
  iconButton: {width: 44, height: 44, alignItems: 'center', justifyContent: 'center'},
  pillRow: {alignItems: 'center', marginBottom: 10},
  pill: {flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 14, paddingVertical: 8},
  dot: {width: 9, height: 9, borderRadius: 5},
  pillText: {fontWeight: '700', fontSize: scale.caption},
  transcript: {gap: 12, paddingVertical: 10},
  userBubble: {alignSelf: 'flex-end', maxWidth: '82%'},
  assistantRow: {flexDirection: 'row', gap: 10, alignItems: 'flex-start'},
  assistantBubble: {flex: 1},
  badgeGap: {width: 34},
  bubblePad: {paddingHorizontal: 16, paddingVertical: 13},
  bubbleText: {fontSize: scale.body, lineHeight: 24},
  fileRow: {flexDirection: 'row', alignItems: 'center', gap: 6},
  fileChip: {fontSize: scale.micro},
  error: {fontSize: scale.caption, marginBottom: 8},
  composer: {minHeight: 60, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, gap: 8},
  composerButton: {width: 38, height: 38, alignItems: 'center', justifyContent: 'center'},
  input: {flex: 1, fontSize: scale.body, paddingVertical: 12, maxHeight: 120},
  send: {width: 42, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center'},
  footer: {textAlign: 'center', fontSize: scale.micro, marginTop: 10},
  overlay: {...StyleSheet.absoluteFillObject, flexDirection: 'row'},
  scrim: {...StyleSheet.absoluteFillObject},
  drawer: {width: '78%'},
  drawerSurface: {borderLeftWidth: 0, borderTopRightRadius: 28, borderBottomRightRadius: 28},
  drawerBody: {paddingHorizontal: 18, paddingTop: 18, gap: 6},
  drawerBrand: {flexDirection: 'row', alignItems: 'center', gap: 10, paddingBottom: 14},
  drawerName: {fontSize: scale.headline, fontWeight: '700'},
  menuRow: {minHeight: 56, borderRadius: 16, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 14},
  menuText: {flex: 1, fontSize: scale.body, fontWeight: '600'},
});
