import {useState} from 'react';
import {Pressable, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';

import {Mark, ScreenHeader, useBrain, useSnapshot, useTheme} from '../ui';
import {useNavigation} from '@react-navigation/native';

export function ChatScreen() {
  const brain = useBrain();
  const snapshot = useSnapshot(brain);
  const theme = useTheme();
  const navigation = useNavigation();
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
      <ScreenHeader
        title="Local AI Chat"
        left={
          <Pressable accessibilityRole="button" accessibilityLabel="Menu" onPress={() => setMenu(true)} style={styles.iconButton}>
            <Text style={[styles.icon, {color: theme.text}]}>≡</Text>
          </Pressable>
        }
        right={
          <Pressable accessibilityRole="button" accessibilityLabel="New chat" onPress={() => brain.newThread()} style={styles.iconButton}>
            <Text style={[styles.icon, {color: theme.text}]}>+</Text>
          </Pressable>
        }
      />
      <View style={styles.pillRow}>
        {premium ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={onDevice ? 'On Device' : 'Digital Brain'}
            onPress={() => brain.setKeepOnDevice(!snapshot.keepOnDevice)}
            style={[styles.pill, {backgroundColor: theme.greenSoft}]}>
            <View style={[styles.dot, {backgroundColor: theme.green}]} />
            <Text style={[styles.pillText, {color: theme.green}]}>{onDevice ? 'On Device' : 'Digital Brain'}</Text>
          </Pressable>
        ) : (
          <View accessibilityLabel="On Device" style={[styles.pill, {backgroundColor: theme.greenSoft}]}>
            <View style={[styles.dot, {backgroundColor: theme.green}]} />
            <Text style={[styles.pillText, {color: theme.green}]}>On Device</Text>
          </View>
        )}
      </View>
      <ScrollView contentContainerStyle={styles.transcript}>
        {(thread?.turns ?? []).map((turn, index) =>
          turn.role === 'user' ? (
            <View key={`${index}-user`} style={[styles.userBubble, {backgroundColor: theme.userBubble}]}>
              <Text style={{color: theme.text}}>{turn.text}</Text>
            </View>
          ) : (
            <View key={`${index}-${turn.role}`} style={styles.assistantRow}>
              {turn.role === 'assistant' ? <Mark size={28} /> : null}
              <View style={[styles.assistantBubble, {backgroundColor: theme.assistantBubble}]}>
                <Text style={{color: turn.role === 'note' ? theme.muted : theme.text}}>{turn.text}</Text>
              </View>
            </View>
          ),
        )}
        {(thread?.files ?? []).map(file => (
          <Text key={file.filename} style={[styles.fileChip, {color: theme.muted}]}>
            {file.filename}
          </Text>
        ))}
      </ScrollView>
      {snapshot.error ? <Text style={[styles.error, {color: theme.danger}]}>{snapshot.error}</Text> : null}
      <View style={[styles.composer, {backgroundColor: theme.card, borderColor: theme.border}]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Attach file" onPress={() => void brain.attach('file')}>
          <Text style={[styles.composerIcon, {color: theme.muted}]}>📎</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Add image" onPress={() => void brain.attach('image')}>
          <Text style={[styles.composerIcon, {color: theme.muted}]}>🖼</Text>
        </Pressable>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Ask anything..."
          placeholderTextColor={theme.muted}
          style={[styles.input, {color: theme.text}]}
        />
        <Pressable accessibilityRole="button" accessibilityLabel="Send" onPress={() => void send()} style={[styles.send, {backgroundColor: theme.primary}]}>
          <Text style={{color: theme.primaryText}}>↑</Text>
        </Pressable>
      </View>
      {onDevice ? (
        <Text style={[styles.footer, {color: theme.muted}]}>Runs completely on your iPhone. No cloud required.</Text>
      ) : (
        <Text style={[styles.footer, {color: theme.muted}]}>Digital Brain uses RAG and memory in the web app.</Text>
      )}
      {menu ? (
        <View style={[styles.menu, {backgroundColor: theme.card, borderColor: theme.border}]}>
          <MenuRow label="Model & Device Status" onPress={() => navigation.navigate('Status')} close={() => setMenu(false)} />
          <MenuRow label="Free vs Premium" onPress={() => navigation.navigate('Compare')} close={() => setMenu(false)} />
          <MenuRow label="Settings" onPress={() => navigation.navigate('Settings')} close={() => setMenu(false)} />
          <Pressable accessibilityRole="button" accessibilityLabel="Close menu" onPress={() => setMenu(false)}>
            <Text style={{color: theme.muted}}>Close</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function MenuRow({label, onPress, close}: {label: string; onPress: () => void; close: () => void}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => {
        close();
        onPress();
      }}
      style={styles.menuRow}>
      <Text style={{color: theme.text, fontSize: 16}}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {flex: 1, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12},
  iconButton: {width: 40, height: 40, alignItems: 'center', justifyContent: 'center'},
  icon: {fontSize: 22},
  pillRow: {alignItems: 'center', marginBottom: 8},
  pill: {flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6},
  dot: {width: 8, height: 8, borderRadius: 4},
  pillText: {fontWeight: '600'},
  transcript: {gap: 10, paddingVertical: 8},
  userBubble: {alignSelf: 'flex-end', maxWidth: '80%', borderRadius: 16, padding: 12},
  assistantRow: {flexDirection: 'row', gap: 8, alignItems: 'flex-start'},
  assistantBubble: {flex: 1, borderRadius: 16, padding: 12},
  fileChip: {fontSize: 12},
  error: {fontSize: 13, marginBottom: 6},
  composer: {
    minHeight: 52,
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    gap: 6,
  },
  composerIcon: {fontSize: 18, paddingHorizontal: 4},
  input: {flex: 1, fontSize: 16, paddingVertical: 10},
  send: {width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center'},
  footer: {textAlign: 'center', fontSize: 12, marginTop: 8},
  menu: {position: 'absolute', top: 56, left: 16, right: 16, borderRadius: 16, borderWidth: 1, padding: 12, gap: 4},
  menuRow: {minHeight: 44, justifyContent: 'center'},
});
