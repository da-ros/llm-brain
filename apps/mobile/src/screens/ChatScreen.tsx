import {useEffect, useRef, useState} from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
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
import type {Thread} from '../storage';

export function ChatScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const [menu, setMenu] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const transcriptRef = useRef<ScrollView>(null);
  const thread = brain.activeThread();
  const onDevice = brain.onDevice();
  const premium = snapshot.user?.plan === 'premium';

  async function send() {
    const question = draft;
    if (brain.snapshot.sending || !question.trim()) {
      return;
    }
    setDraft('');
    const ok = await brain.send(question);
    if (!ok && !brain.snapshot.sending) {
      setDraft(current => (current.trim() ? current : question));
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
              <Glass radius={999} contentStyle={styles.pill}>
                <Text style={[styles.modeLabel, {color: onDevice ? theme.green : theme.muted}]}>On Device</Text>
                <Switch
                  accessibilityLabel={onDevice ? 'On Device' : 'Digital Brain'}
                  value={!onDevice}
                  onValueChange={digital => brain.setKeepOnDevice(!digital)}
                  trackColor={{true: theme.green, false: theme.sunken}}
                />
                <Text style={[styles.modeLabel, {color: onDevice ? theme.muted : theme.green}]}>Digital Brain</Text>
              </Glass>
            ) : (
              <View accessibilityLabel="On Device">
                <Pill label="On Device" />
              </View>
            )}
          </View>
          <ScrollView
            ref={transcriptRef}
            style={styles.fill}
            contentContainerStyle={styles.transcript}
            keyboardDismissMode="interactive"
            onContentSizeChange={() => transcriptRef.current?.scrollToEnd({animated: true})}>
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
                    {turn.thinking ? <Thinking text={turn.thinking} openByDefault={!turn.text.trim()} /> : null}
                    {turn.text.trim() ? (
                      <Text style={[styles.bubbleText, {color: turn.role === 'note' ? theme.muted : theme.text}]}>
                        {turn.text}
                      </Text>
                    ) : null}
                    {(turn.cards ?? []).length ? (
                      <View style={styles.sourceRow}>
                        {(turn.cards ?? []).map(card => (
                          <Text key={`${card.n}-${card.label}`} style={[styles.source, {color: theme.muted}]}>
                            {card.n}. {card.label}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {shownAssumptions(turn.assumptions).map(item => (
                      <Text key={item} style={[styles.evidence, {color: theme.muted}]}>
                        {item}
                      </Text>
                    ))}
                  </Glass>
                </View>
              ),
            )}
            {snapshot.pending ? (
              <>
                <Glass radius={22} strong style={styles.userBubble} contentStyle={styles.bubblePad}>
                  <Text style={[styles.bubbleText, {color: theme.text}]}>{snapshot.pending}</Text>
                </Glass>
                <View style={styles.typingRow}>
                  <MarkBadge size={34} />
                  <TypingDots />
                </View>
              </>
            ) : null}
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
              accessibilityState={{disabled: snapshot.sending, busy: snapshot.sending}}
              disabled={snapshot.sending}
              onPress={() => void send()}
              style={({pressed}) => [
                styles.send,
                {backgroundColor: theme.primary, opacity: snapshot.sending || pressed ? 0.55 : 1},
              ]}>
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
            onPress={() => {
              setPendingDelete(null);
              setMenu(false);
            }}
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
              close={() => {
                setPendingDelete(null);
                setMenu(false);
              }}
            />
            <MenuRow
              label="Free vs Premium"
              icon={Icon.premium}
              onPress={() => navigation.navigate('Compare')}
              close={() => {
                setPendingDelete(null);
                setMenu(false);
              }}
            />
            <MenuRow
              label="Settings"
              icon={Icon.settings}
              onPress={() => navigation.navigate('Settings')}
              close={() => {
                setPendingDelete(null);
                setMenu(false);
              }}
            />
            <Text style={[styles.chatHeading, {color: theme.muted}]}>Chats</Text>
            <ScrollView style={styles.fill} contentContainerStyle={styles.chatList}>
              {snapshot.threads.map(item => {
                const title = threadTitle(item);
                const active = item.id === snapshot.activeId;
                return (
                  <View key={item.id}>
                    <View style={[styles.chatRow, active && {backgroundColor: theme.glass}]}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Open ${title}`}
                        onPress={() => {
                          brain.openThread(item.id);
                          setPendingDelete(null);
                          setMenu(false);
                        }}
                        style={styles.chatOpen}>
                        <Text style={[styles.chatTitle, {color: theme.text}]} numberOfLines={2}>
                          {title}
                        </Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Delete ${title}`}
                        onPress={() => setPendingDelete(item.id)}
                        style={styles.chatDelete}>
                        <Icon.erase size={18} color={theme.danger} strokeWidth={2.2} />
                      </Pressable>
                    </View>
                    {pendingDelete === item.id ? (
                      <View style={styles.confirmDelete}>
                        <Text style={[styles.confirmCopy, {color: theme.muted}]}>Remove this chat?</Text>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel="Cancel delete"
                          onPress={() => setPendingDelete(null)}>
                          <Text style={[styles.confirmAction, {color: theme.muted}]}>Cancel</Text>
                        </Pressable>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel="Confirm delete"
                          onPress={() => {
                            setPendingDelete(null);
                            void brain.deleteThread(item.id);
                          }}>
                          <Text style={[styles.confirmAction, {color: theme.danger}]}>Delete</Text>
                        </Pressable>
                      </View>
                    ) : null}
                  </View>
                );
              })}
            </ScrollView>
            {snapshot.user ? (
              <View
                accessibilityLabel={`Signed in as ${snapshot.user.email}`}
                style={[styles.account, {borderTopColor: theme.border, paddingBottom: Math.max(insets.bottom, 16)}]}>
                <Text style={[styles.accountLabel, {color: theme.muted}]}>Signed in</Text>
                <Text style={[styles.accountName, {color: theme.text}]} numberOfLines={1}>
                  {snapshot.user.name}
                </Text>
                <Text style={[styles.accountEmail, {color: theme.muted}]} numberOfLines={1}>
                  {snapshot.user.email}
                </Text>
              </View>
            ) : null}
          </Glass>
        </View>
      ) : null}
    </View>
  );
}

function Thinking({text, openByDefault}: {text: string; openByDefault: boolean}) {
  const theme = useTheme();
  const [open, setOpen] = useState(openByDefault);
  return (
    <View style={styles.thinking}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Thinking"
        accessibilityState={{expanded: open}}
        onPress={() => setOpen(current => !current)}
        style={styles.thinkingButton}>
        <View style={{transform: [{rotate: open ? '90deg' : '0deg'}]}}>
          <Icon.next size={16} color={theme.muted} strokeWidth={2.4} />
        </View>
        <Text style={[styles.thinkingLabel, {color: theme.muted}]}>Thinking</Text>
      </Pressable>
      {open ? <Text style={[styles.thinkingBody, {color: theme.muted}]}>{text}</Text> : null}
    </View>
  );
}

function shownAssumptions(items: string[] | undefined): string[] {
  return (items ?? []).filter(item => !/^Retrieved \d+ source\(s\) from RAG Top-k search\.$/.test(item));
}

function TypingDots() {
  const theme = useTheme();
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setStep(current => (current + 1) % 3), 420);
    return () => clearInterval(timer);
  }, []);
  return (
    <View accessibilityLabel="Sending" style={styles.dots}>
      {[0, 1, 2].map(index => {
        const on = index === step;
        return (
          <View
            key={index}
            style={[
              styles.typingDot,
              {backgroundColor: theme.text, opacity: on ? 1 : 0.28, transform: [{scale: on ? 1 : 0.72}]},
            ]}
          />
        );
      })}
    </View>
  );
}

function threadTitle(thread: Thread): string {
  const question = thread.turns.find(turn => turn.role === 'user')?.text.trim();
  return question || 'New chat';
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
  pill: {flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 8},
  dot: {width: 9, height: 9, borderRadius: 5},
  pillText: {fontWeight: '700', fontSize: scale.caption},
  modeLabel: {fontWeight: '700', fontSize: scale.caption},
  transcript: {gap: 12, paddingVertical: 10},
  userBubble: {alignSelf: 'flex-end', maxWidth: '82%'},
  assistantRow: {flexDirection: 'row', gap: 10, alignItems: 'flex-start'},
  typingRow: {flexDirection: 'row', gap: 10, alignItems: 'center', minHeight: 34},
  dots: {flexDirection: 'row', alignItems: 'center', gap: 6, paddingLeft: 2},
  typingDot: {width: 8, height: 8, borderRadius: 4},
  assistantBubble: {flex: 1},
  badgeGap: {width: 34},
  bubblePad: {paddingHorizontal: 16, paddingVertical: 13},
  bubbleText: {fontSize: scale.body, lineHeight: 24},
  thinking: {marginBottom: 8, gap: 6},
  thinkingButton: {flexDirection: 'row', alignItems: 'center', gap: 6},
  thinkingLabel: {fontSize: scale.caption, fontWeight: '600'},
  thinkingBody: {fontSize: scale.caption, lineHeight: 20},
  evidence: {fontSize: scale.micro, lineHeight: 18, marginTop: 8},
  sourceRow: {flexDirection: 'row', flexWrap: 'wrap', columnGap: 12, rowGap: 4, marginTop: 8},
  source: {fontSize: scale.micro, lineHeight: 18},
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
  drawerBody: {flex: 1, paddingHorizontal: 18, paddingTop: 18, gap: 6},
  chatHeading: {fontSize: scale.micro, fontWeight: '700', letterSpacing: 0.6, marginTop: 16, marginBottom: 4},
  chatList: {gap: 4, paddingBottom: 12},
  account: {borderTopWidth: StyleSheet.hairlineWidth, marginTop: 8, paddingTop: 14, gap: 2},
  accountLabel: {fontSize: scale.micro, fontWeight: '700', letterSpacing: 0.6},
  accountName: {fontSize: scale.body, fontWeight: '700'},
  accountEmail: {fontSize: scale.caption},
  chatRow: {minHeight: 48, borderRadius: 14, paddingLeft: 12, flexDirection: 'row', alignItems: 'center'},
  chatOpen: {flex: 1, justifyContent: 'center', paddingVertical: 10},
  chatDelete: {width: 44, height: 44, alignItems: 'center', justifyContent: 'center'},
  chatTitle: {fontSize: scale.body, lineHeight: 22},
  confirmDelete: {flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 12, paddingBottom: 8},
  confirmCopy: {flex: 1, fontSize: scale.caption},
  confirmAction: {fontSize: scale.caption, fontWeight: '700'},
  drawerBrand: {flexDirection: 'row', alignItems: 'center', gap: 10, paddingBottom: 14},
  drawerName: {fontSize: scale.headline, fontWeight: '700'},
  menuRow: {minHeight: 56, borderRadius: 16, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 14},
  menuText: {flex: 1, fontSize: scale.body, fontWeight: '600'},
});
