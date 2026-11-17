import React from 'react';
import TestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';

import App from '../App';
import {RouterApi} from '../src/api';
import {checksum} from '../src/bytes';
import {API_BASE_URL} from '../src/config';
import {createBrain} from '../src/brain';
import {FakeEngine} from '../src/engine';
import {extractText, buildPrompt, splitThinking} from '../src/files';
import {MemoryKeychain, MemoryPackFiles, MemoryStore, type Persisted, type PickedFile, type Picker} from '../src/storage';

type NavState = {stack: string[]; listeners: Set<() => void>; key?: string};

function navState(): NavState {
  const globalNav = global as typeof global & {__ENCEF_NAV?: NavState};
  if (!globalNav.__ENCEF_NAV) {
    globalNav.__ENCEF_NAV = {stack: [], listeners: new Set()};
  }
  return globalNav.__ENCEF_NAV;
}

jest.mock('react-native-safe-area-context', () => {
  const ReactLib = require('react');
  const inset = {top: 0, right: 0, bottom: 0, left: 0};
  return {
    SafeAreaProvider: ({children}: {children: React.ReactNode}) => ReactLib.createElement(ReactLib.Fragment, null, children),
    SafeAreaView: ({children}: {children: React.ReactNode}) => ReactLib.createElement(ReactLib.Fragment, null, children),
    useSafeAreaInsets: () => inset,
  };
});

jest.mock('@react-native-community/blur', () => {
  const ReactLib = require('react');
  const {View} = require('react-native');
  return {
    BlurView: ({children, style}: {children?: React.ReactNode; style?: unknown}) =>
      ReactLib.createElement(View, {style}, children),
  };
});

// Lucide ships one component per icon. The test only needs them to render.
jest.mock('lucide-react-native', () => {
  const ReactLib = require('react');
  const {View} = require('react-native');
  const made = new Map<string, unknown>();
  return new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === '__esModule') {
          return true;
        }
        if (typeof prop !== 'string') {
          return undefined;
        }
        if (!made.has(prop)) {
          const Glyph = () => ReactLib.createElement(View, null);
          Glyph.displayName = prop;
          made.set(prop, Glyph);
        }
        return made.get(prop);
      },
    },
  );
});

jest.mock('@react-navigation/native', () => {
  const nav = (global as typeof global & {__ENCEF_NAV?: NavState}).__ENCEF_NAV ?? {
    stack: [] as string[],
    listeners: new Set<() => void>(),
  };
  (global as typeof global & {__ENCEF_NAV?: NavState}).__ENCEF_NAV = nav;
  return {
    NavigationContainer: ({children}: {children: React.ReactNode}) => children,
    useNavigation: () => ({
      navigate: (name: string) => {
        nav.stack.push(name);
        nav.listeners.forEach(listener => listener());
      },
      goBack: () => {
        if (nav.stack.length > 1) {
          nav.stack.pop();
        }
        nav.listeners.forEach(listener => listener());
      },
    }),
  };
});

jest.mock('@react-navigation/native-stack', () => {
  const ReactLib = require('react');
  const nav = (global as typeof global & {__ENCEF_NAV?: NavState & {key?: string}}).__ENCEF_NAV ?? {
    stack: [] as string[],
    listeners: new Set<() => void>(),
    key: '',
  };
  (global as typeof global & {__ENCEF_NAV?: NavState & {key?: string}}).__ENCEF_NAV = nav;
  return {
    createNativeStackNavigator: () => ({
      Navigator({children}: {children: React.ReactNode}) {
        const [, redraw] = ReactLib.useState(0);
        ReactLib.useEffect(() => {
          const listener = () => redraw((value: number) => value + 1);
          nav.listeners.add(listener);
          return () => nav.listeners.delete(listener);
        }, []);
        const screens = ReactLib.Children.toArray(children).filter(ReactLib.isValidElement);
        const names = screens.map(screen => String(screen.props.name));
        const key = names.join('|');
        if (key && nav.key !== key) {
          nav.key = key;
          const top = nav.stack[nav.stack.length - 1];
          if (!names.includes(top)) {
            nav.stack = [names[0]];
          }
        }
        const current = nav.stack[nav.stack.length - 1];
        const shown = names.includes(current) ? current : names[0];
        const match = screens.find(screen => String(screen.props.name) === shown);
        const Comp = match?.props.component;
        return Comp ? ReactLib.createElement(Comp, null) : null;
      },
      Screen() {
        return null;
      },
    }),
  };
});

type Call = {url: string; init?: RequestInit};

function jsonResponse(status: number, body: unknown = {}, bytes = new Uint8Array()) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  };
}

function flatten(child: unknown): string {
  if (child == null || typeof child === 'boolean') {
    return '';
  }
  if (typeof child === 'string' || typeof child === 'number') {
    return String(child);
  }
  if (Array.isArray(child)) {
    return child.map(flatten).join('');
  }
  return '';
}

function collect(renderer: TestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAllByType(Text)
    .map(node => flatten(node.props.children))
    .join('\n');
}

function press(renderer: TestRenderer.ReactTestRenderer, label: string) {
  const node = renderer.root.findAll(
    item => item.props?.accessibilityLabel === label && typeof item.props?.onPress === 'function',
  )[0];
  if (!node) {
    throw new Error(`Missing control ${label}\n${collect(renderer)}`);
  }
  node.props.onPress();
}

function typeInto(renderer: TestRenderer.ReactTestRenderer, placeholder: string, value: string) {
  renderer.root.findByProps({placeholder}).props.onChangeText(value);
}

function calls(fetchImpl: jest.Mock): Call[] {
  return fetchImpl.mock.calls.map(([url, init]) => ({url: String(url), init}));
}

function paths(fetchImpl: jest.Mock): string[] {
  return calls(fetchImpl).map(call => new URL(call.url).pathname);
}

function makeApp(seed?: Partial<Persisted>) {
  const store = new MemoryStore(seed);
  const keychain = new MemoryKeychain();
  const engine = new FakeEngine();
  if (seed?.cacheBytes) {
    engine.cacheBytes = seed.cacheBytes;
  }
  const files = new MemoryPackFiles();
  const queue: PickedFile[] = [];
  const picker: Picker = async () => queue.shift() ?? null;
  const fetchImpl = jest.fn(async () => jsonResponse(404, {detail: 'not stubbed'}));
  const api = new RouterApi(API_BASE_URL, fetchImpl as unknown as typeof fetch);
  const brain = createBrain({api, store, keychain, engine, files, picker});
  return {brain, store, keychain, engine, files, queue, fetchImpl};
}

async function render(brain: ReturnType<typeof createBrain>) {
  await brain.boot();
  let renderer!: TestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = TestRenderer.create(<App brain={brain} />);
  });
  mounted = renderer;
  return renderer;
}

function user(id: string, plan: 'free' | 'premium') {
  return {id, name: 'Ada', email: `${id}@example.com`, plan};
}

let mounted: TestRenderer.ReactTestRenderer | null = null;

beforeEach(() => {
  const nav = navState();
  nav.stack = [];
  nav.key = '';
  nav.listeners.clear();
});

afterEach(() => {
  if (mounted) {
    act(() => {
      mounted?.unmount();
    });
  }
  mounted = null;
});

test('sha256 of abc and a pdf literal string', () => {
  const bytes = new TextEncoder().encode('abc');
  expect(checksum(bytes)).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  expect(extractText('note.pdf', new TextEncoder().encode('%PDF-1.4 (Hello PDF)'))).toBe('Hello PDF');
});

test('a new chat clears the loaded model state and keeps the pack', async () => {
  const {brain, engine} = makeApp();
  await brain.boot();
  brain.newThread();
  const nora = brain.snapshot.activeId;
  brain.newThread();
  expect(brain.snapshot.activeId).not.toBe(nora);
  expect(engine.loadedPackId).toBeNull();
  expect(engine.chatsBegun).toBe(2);
  brain.openThread(brain.snapshot.activeId!);
  expect(engine.chatsBegun).toBe(2);
  brain.openThread(nora!);
  expect(engine.chatsBegun).toBe(3);
});

test('on-device questions use the fine-tune lead-in and thinking stays separate', () => {
  expect(buildPrompt('Who is Theo Park?', [])).toBe(
    "<|im_start|>system\n" +
      "When the question is about this person's record, answer with that fact. For any other question, answer normally.<|im_end|>\n" +
      "<|im_start|>user\n" +
      "Who is Theo Park?<|im_end|>\n" +
      "<|im_start|>assistant\n" +
      "<think>\n",
  );
  expect(splitThinking('<think>\nrecall the record\n</think>\n\nTheo Park is the engineer.')).toEqual({
    thinking: 'recall the record',
    answer: 'Theo Park is the engineer.',
  });
  expect(splitThinking('Just the answer.')).toEqual({thinking: '', answer: 'Just the answer.'});
  expect(
    buildPrompt('What about her?', [], [
      {role: 'user', text: "What is the name of Nora's cat?"},
      {role: 'assistant', text: "Nora's orange cat is named Pixel.", thinking: 'Pixel.'},
    ]),
  ).toBe(
    "<|im_start|>system\n" +
      "When the question is about this person's record, answer with that fact. For any other question, answer normally.<|im_end|>\n" +
      "<|im_start|>user\n" +
      "What is the name of Nora's cat?<|im_end|>\n" +
      "<|im_start|>assistant\n" +
      "<think>\n" +
      "Pixel.\n" +
      "</think>\n\n" +
      "Nora's orange cat is named Pixel.<|im_end|>\n" +
      "<|im_start|>user\n" +
      "What about her?<|im_end|>\n" +
      "<|im_start|>assistant\n" +
      "<think>\n",
  );
  const long = 'word '.repeat(800);
  const packed = buildPrompt('Latest?', [], [
    {role: 'user', text: long},
    {role: 'assistant', text: long},
    {role: 'user', text: 'Second question'},
    {role: 'assistant', text: 'Second answer'},
  ]);
  expect(packed).not.toContain('word word word');
  expect(packed).toContain('Second question');
  expect(packed).toContain('Latest?');
});

test('no token shows auth and omits Apple, Google, forgot password, and the microphone', async () => {
  const {brain} = makeApp();
  const renderer = await render(brain);
  const text = collect(renderer);
  expect(text).toContain('Encefalus');
  expect(text).toContain('AI-Augmented Brain');
  expect(text).toContain('Your memories. Sharper decisions.');
  expect(text).toContain('Sign in');
  expect(text).toContain('Runs private. Built for your personal AI.');
  expect(text).toContain('Free local AI on iPhone · Premium Digital Brain on web');
  expect(text).not.toContain('Local AI Chat');
  expect(text).not.toContain('Apple');
  expect(text).not.toContain('Google');
  expect(text).not.toContain('Forgot password');
  expect(text.toLowerCase()).not.toContain('or continue with');
  expect(text.toLowerCase()).not.toContain('microphone');
  const labels = renderer.root.findAll(node => node.props?.accessibilityLabel).map(node => node.props.accessibilityLabel);
  expect(labels).not.toContain('Microphone');
});

test('sign up sends plan free and sign in opens chat', async () => {
  const {brain, fetchImpl, keychain} = makeApp();
  fetchImpl.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    if (path === '/api/auth/signup') {
      return jsonResponse(201, {access_token: 'tok-new', user: user('new', 'free'), sent: body});
    }
    return jsonResponse(404, {detail: 'missing'});
  });
  const renderer = await render(brain);
  await act(async () => {
    press(renderer, 'Sign up');
  });
  await act(async () => {
    typeInto(renderer, 'Your name', 'Ada');
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  const signup = calls(fetchImpl).find(call => call.url.endsWith('/api/auth/signup'));
  expect(JSON.parse(String(signup?.init?.body))).toEqual({
    name: 'Ada',
    email: 'ada@example.com',
    password: 'secret123',
    plan: 'free',
  });
  expect(signup?.init?.headers).toEqual(expect.objectContaining({'X-Request-ID': expect.any(String)}));
  expect(collect(renderer)).toContain('Local AI Chat');
  expect(JSON.parse((await keychain.get()) || '{}').access_token).toBe('tok-new');
});

test('401 and 409 stay on auth and show the router detail', async () => {
  const {brain, fetchImpl} = makeApp();
  fetchImpl.mockImplementation(async (url: string) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/auth/signin') {
      return jsonResponse(401, {detail: 'Invalid email or password.'});
    }
    if (path === '/api/auth/signup') {
      return jsonResponse(409, {detail: 'An account with this email already exists.'});
    }
    return jsonResponse(404, {detail: 'missing'});
  });
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'nope');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  expect(collect(renderer)).toContain('Invalid email or password.');
  expect(collect(renderer)).not.toContain('Local AI Chat');
  await act(async () => {
    press(renderer, 'Sign up');
  });
  await act(async () => {
    typeInto(renderer, 'Your name', 'Ada');
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  expect(collect(renderer)).toContain('An account with this email already exists.');
  expect(collect(renderer)).not.toContain('Local AI Chat');
});

test('free chat uses the base pack, keeps five local files, and does not call cloud chat', async () => {
  const {brain, fetchImpl, engine, queue} = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'documents/packs/base.pte', bytes: 2048, sha256: 'aa'},
    loraByUser: {ada: {id: 'qwen3.5-4b-finetuned-q4', path: 'documents/packs/lora.pte', bytes: 10, sha256: 'bb'}},
  });
  fetchImpl.mockImplementation(async (url: string) => {
    if (new URL(String(url)).pathname === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok', user: user('ada', 'free')});
    }
    return jsonResponse(500, {detail: 'cloud was called'});
  });
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  expect(collect(renderer)).toContain('On Device');
  expect(collect(renderer)).toContain('Runs completely on your iPhone. No cloud required.');
  // The composer only offers the paperclip, so an image arrives through it.
  queue.push({filename: 'photo.png', mime: 'image/png', bytes: Uint8Array.from([1, 2, 3])});
  expect(renderer.root.findAll(node => node.props?.accessibilityLabel === 'Add image')).toHaveLength(0);
  await act(async () => {
    press(renderer, 'Attach file');
  });
  expect(collect(renderer)).toContain('Images are not sent to the on-device model.');
  expect(paths(fetchImpl)).not.toContain('/api/upload');
  for (let index = 0; index < 6; index += 1) {
    queue.push({
      filename: `note-${index}.txt`,
      mime: 'text/plain',
      bytes: new TextEncoder().encode(`file-${index}`),
    });
    await act(async () => {
      press(renderer, 'Attach file');
    });
  }
  expect(collect(renderer)).toContain('You can attach up to five files.');
  expect(brain.activeThread()?.files).toHaveLength(5);
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'Plan the day');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  const reply = collect(renderer);
  expect(reply).toContain('file-0');
  expect(reply).toContain('file-4');
  expect(reply).not.toContain('file-5');
  expect(engine.stats().loadedPackId).toBe('qwen3.5-4b-base-q4');
  expect(paths(fetchImpl)).not.toContain('/api/chat');
  expect(paths(fetchImpl)).not.toContain('/api/upload');
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'What about lunch?');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  expect(engine.stats().replies).toHaveLength(2);
  expect(collect(renderer)).toContain('file-0');
  expect(paths(fetchImpl).some(path => path.startsWith('/api/chat'))).toBe(false);
});

test('a Digital Brain send shows the question until the reply arrives', async () => {
  const harness = makeApp();
  let release: (() => void) | null = null;
  harness.fetchImpl.mockImplementation(async (url: string) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok', user: user('ada', 'premium')});
    }
    if (path === '/api/chats') {
      return jsonResponse(201, {id: 'chat-9'});
    }
    if (path === '/api/chat') {
      return new Promise(resolve => {
        release = () => resolve(jsonResponse(200, {response: 'from memory'}));
      });
    }
    return jsonResponse(404, {detail: path});
  });
  await harness.brain.boot();
  await harness.brain.signIn('ada@example.com', 'secret123');
  harness.brain.setKeepOnDevice(false);
  const flight = harness.brain.send('What do I like to do at the beach?');
  expect(harness.brain.snapshot.sending).toBe(true);
  expect(harness.brain.snapshot.pending).toBe('What do I like to do at the beach?');
  for (let i = 0; i < 8 && !release; i += 1) {
    await Promise.resolve();
  }
  release?.();
  await flight;
  expect(harness.brain.snapshot.sending).toBe(false);
  expect(harness.brain.snapshot.pending).toBeNull();
  expect(harness.brain.activeThread()?.turns.map(turn => turn.text)).toEqual([
    'What do I like to do at the beach?',
    'from memory',
  ]);
});

test('a missing base pack does not fall back to cloud chat', async () => {
  const {brain, fetchImpl} = makeApp();
  fetchImpl.mockImplementation(async () => jsonResponse(200, {access_token: 'tok', user: user('ada', 'free')}));
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  fetchImpl.mockClear();
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'Hello');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  expect(collect(renderer)).toContain('Download the model to chat on this iPhone.');
  expect(fetchImpl).not.toHaveBeenCalled();
});

test('menu reaches status, compare, and settings, and a new thread keeps the old one', async () => {
  const {brain, fetchImpl} = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 2048, sha256: 'aa'},
    cacheBytes: 4096,
  });
  fetchImpl.mockImplementation(async () => jsonResponse(200, {access_token: 'tok', user: user('ada', 'free')}));
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'first thread');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  await act(async () => {
    press(renderer, 'New chat');
  });
  expect(collect(renderer)).not.toContain('first thread');
  expect(brain.snapshot.threads).toHaveLength(2);
  await act(async () => {
    press(renderer, 'Menu');
  });
  expect(collect(renderer)).toContain('Signed in');
  expect(collect(renderer)).toContain('ada@example.com');
  await act(async () => {
    press(renderer, 'Model & Device Status');
  });
  const status = collect(renderer);
  expect(status).toContain('Qwen 3.5 4B');
  expect(status).toContain('Open source LLM · 4.0B parameters');
  expect(status).toContain('A capable, efficient model for everyday questions, writing, and analysis.');
  expect(status).toContain('4.1 GB');
  expect(status).toContain('40 ms');
  expect(status).toContain('Works without internet');
  expect(status).toContain('Download or update model files');
  expect(status).not.toContain('2.8');
  expect(status).not.toContain('320');
  await act(async () => {
    press(renderer, 'Clear Cache');
  });
  expect(collect(renderer)).toContain('0 B');
  expect(brain.snapshot.threads.some(thread => thread.turns.some(turn => turn.text === 'first thread'))).toBe(true);
  expect(brain.snapshot.basePack?.id).toBe('qwen3.5-4b-base-q4');
  await act(async () => {
    press(renderer, 'Back');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Free vs Premium');
  });
  const compare = collect(renderer);
  expect(compare).toContain('Go further with Encefalus');
  expect(compare).toContain('Lifelong Memory');
  expect(compare).toContain('Shield (Safety layer)');
  expect(compare).toContain('Use the web app for memory, RAG, analytics and more.');
  await act(async () => {
    press(renderer, 'Back');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Settings');
  });
  expect(collect(renderer)).toContain('Keep data on device');
  expect(collect(renderer)).toContain('Conversations and files stay on this iPhone. Nothing is sent to the cloud.');
  const toggle = renderer.root.findByProps({accessibilityLabel: 'Keep data on device'});
  await act(async () => {
    toggle.props.onValueChange(false);
  });
  expect(renderer.root.findByProps({accessibilityLabel: 'Keep data on device'}).props.value).toBe(true);
  expect(brain.onDevice()).toBe(true);
});

test('deleting a chat removes it from the menu and from the Digital Brain', async () => {
  const harness = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 20, sha256: 'aa'},
    loraByUser: {
      ada: {id: 'qwen3.5-4b-finetuned-q4', path: 'lora.pte', bytes: 30, sha256: 'bb'},
    },
  });
  harness.fetchImpl.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? 'GET';
    if (path === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok', user: user('ada', 'premium')});
    }
    if (path === '/api/chats' && method === 'POST') {
      return jsonResponse(201, {id: 'chat-1'});
    }
    if (path === '/api/chat') {
      return jsonResponse(200, {response: 'cloud answer', assumptions: ['No personal context was found.']});
    }
    if (path === '/api/chats/chat-1' && method === 'DELETE') {
      return jsonResponse(204);
    }
    return jsonResponse(404, {detail: path});
  });
  const renderer = await render(harness.brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'keep this one');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  await act(async () => {
    press(renderer, 'New chat');
  });
  const mode = renderer.root.findByProps({accessibilityLabel: 'On Device'});
  await act(async () => {
    mode.props.onValueChange(true);
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'cloud thread');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Delete cloud thread');
  });
  expect(collect(renderer)).toContain('Remove this chat?');
  await act(async () => {
    press(renderer, 'Cancel delete');
  });
  expect(harness.brain.snapshot.threads).toHaveLength(2);
  await act(async () => {
    press(renderer, 'Delete cloud thread');
  });
  await act(async () => {
    press(renderer, 'Confirm delete');
  });
  expect(harness.brain.snapshot.threads).toHaveLength(1);
  expect(harness.brain.snapshot.threads[0].turns.some(turn => turn.text === 'keep this one')).toBe(true);
  expect(collect(renderer)).not.toContain('cloud thread');
  expect(paths(harness.fetchImpl)).toContain('/api/chats/chat-1');
  const removed = calls(harness.fetchImpl).find(call => new URL(call.url).pathname === '/api/chats/chat-1');
  expect(removed?.init?.method).toBe('DELETE');
  await act(async () => {
    press(renderer, 'Delete keep this one');
  });
  await act(async () => {
    press(renderer, 'Confirm delete');
  });
  expect(harness.brain.snapshot.threads).toHaveLength(0);
  expect(paths(harness.fetchImpl).filter(path => path.startsWith('/api/chats/'))).toHaveLength(1);
});

test('theme persists and clear all data stays on the phone', async () => {
  const harness = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 100, sha256: 'aa'},
  });
  harness.fetchImpl.mockImplementation(async () =>
    jsonResponse(200, {access_token: 'tok', user: user('ada', 'free')}),
  );
  const renderer = await render(harness.brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'keep me');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Settings');
  });
  const beforeHelp = harness.fetchImpl.mock.calls.length;
  await act(async () => {
    press(renderer, 'Help & FAQ');
  });
  expect(collect(renderer)).toContain('Where do free answers run?');
  expect(harness.fetchImpl.mock.calls.length).toBe(beforeHelp);
  await act(async () => {
    press(renderer, 'Back');
  });
  await act(async () => {
    press(renderer, 'About Encefalus');
  });
  expect(collect(renderer)).toContain('v1.0.0');
  await act(async () => {
    press(renderer, 'Back');
  });
  await act(async () => {
    press(renderer, 'Theme');
    press(renderer, 'Theme');
  });
  expect(collect(renderer)).toContain('Dark');
  await act(async () => {
    press(renderer, 'Clear All Data');
  });
  harness.fetchImpl.mockClear();
  await act(async () => {
    press(renderer, 'Confirm clear');
  });
  expect(harness.fetchImpl).not.toHaveBeenCalled();
  expect(paths(harness.fetchImpl)).not.toContain('/api/data');
  expect(harness.brain.snapshot.basePack).toBeNull();
  expect(harness.brain.snapshot.threads).toHaveLength(0);
  expect(harness.brain.snapshot.token).toBe('tok');
  const relaunch = createBrain({
    api: new RouterApi(API_BASE_URL, harness.fetchImpl as unknown as typeof fetch),
    store: harness.store,
    keychain: harness.keychain,
    engine: new FakeEngine(),
    files: harness.files,
    picker: async () => null,
  });
  await relaunch.boot();
  expect(relaunch.snapshot.theme).toBe('dark');
});

test('reinstall swaps only when the checksum matches', async () => {
  const harness = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'old.pte', bytes: 10, sha256: 'old'},
  });
  const good = new TextEncoder().encode('new-weights');
  const goodSha = checksum(good);
  let sha = 'deadbeef';
  harness.fetchImpl.mockImplementation(async (url: string) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok', user: user('ada', 'free')});
    }
    if (path === '/api/models/on-device') {
      return jsonResponse(200, {
        id: 'qwen3.5-4b-base-q4',
        filename: 'qwen3.5-4b-base-q4.pte',
        sha256: sha,
        ready: true,
        bytes: good.byteLength,
      });
    }
    if (path === '/api/models/on-device/file') {
      return jsonResponse(200, {}, good);
    }
    return jsonResponse(404, {detail: 'missing'});
  });
  const renderer = await render(harness.brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Model & Device Status');
  });
  await act(async () => {
    press(renderer, 'Reinstall Model');
  });
  expect(collect(renderer)).toContain('checksum');
  expect(harness.brain.snapshot.basePack?.sha256).toBe('old');
  sha = goodSha;
  await act(async () => {
    press(renderer, 'Reinstall Model');
  });
  expect(harness.brain.snapshot.basePack?.sha256).toBe(goodSha);
  expect(harness.brain.snapshot.basePack?.bytes).toBe(good.byteLength);
  const fileCall = calls(harness.fetchImpl).find(call => call.url.endsWith('/api/models/on-device/file'));
  expect(fileCall?.init?.headers).toEqual(
    expect.objectContaining({Authorization: 'Bearer tok', 'X-Request-ID': expect.any(String)}),
  );
  expect(calls(harness.fetchImpl).every(call => call.url.startsWith(`${API_BASE_URL}/api/`))).toBe(true);
});

test('status names the installed personal model by its fine-tune tag', async () => {
  const harness = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 20, sha256: 'aa'},
    loraByUser: {
      ada: {id: 'qwen3.5-4b-finetuned-q4', path: 'lora.pte', bytes: 30, sha256: 'bb'},
    },
  });
  harness.fetchImpl.mockImplementation(async (url: string) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok', user: user('ada', 'premium')});
    }
    if (path === '/api/models/on-device') {
      return jsonResponse(200, {
        id: 'qwen3.5-4b-finetuned-q4',
        filename: 'qwen3.5-4b-finetuned-q4.gguf',
        sha256: 'bb',
        ready: true,
        bytes: 30,
        tag: 'qwen3.5-4b-lora-v5',
      });
    }
    return jsonResponse(404, {detail: 'missing'});
  });
  const renderer = await render(harness.brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Model & Device Status');
  });
  expect(collect(renderer)).toContain('qwen3.5-4b-lora-v5');
  expect(harness.brain.snapshot.loraPack?.tag).toBe('qwen3.5-4b-lora-v5');
  harness.fetchImpl.mockImplementation(async () =>
    jsonResponse(200, {
      id: 'qwen3.5-4b-finetuned-q4',
      sha256: 'cc',
      ready: true,
      tag: 'qwen3.5-4b-lora-v9',
    }),
  );
  await act(async () => {
    await harness.brain.refreshInstalledTag();
  });
  expect(harness.brain.snapshot.loraPack?.tag).toBe('qwen3.5-4b-lora-v5');
});

test('premium on device uses the LoRA pack and digital brain uses chat with RAG', async () => {
  const harness = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 20, sha256: 'aa'},
    loraByUser: {
      ada: {id: 'qwen3.5-4b-finetuned-q4', path: 'lora.pte', bytes: 30, sha256: 'bb'},
    },
  });
  harness.fetchImpl.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok', user: user('ada', 'premium')});
    }
    if (path === '/api/chats') {
      return jsonResponse(200, {id: 'chat-1'});
    }
    if (path === '/api/chat') {
      return jsonResponse(200, {response: 'cloud answer'});
    }
    if (path === '/api/account') {
      return jsonResponse(200, {access_token: 'tok-premium', user: user('ada', 'premium')});
    }
    return jsonResponse(404, {detail: path, body: init?.body});
  });
  const renderer = await render(harness.brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'local question');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  expect(harness.engine.stats().loadedPackId).toBe('qwen3.5-4b-finetuned-q4');
  expect(paths(harness.fetchImpl)).not.toContain('/api/chat');
  const mode = renderer.root.findByProps({accessibilityLabel: 'On Device'});
  await act(async () => {
    mode.props.onValueChange(true);
  });
  expect(collect(renderer)).toContain('Digital Brain');
  expect(collect(renderer)).not.toContain('No cloud required');
  harness.queue.push({
    filename: 'notes.txt',
    mime: 'text/plain',
    bytes: new TextEncoder().encode('remember this'),
  });
  await act(async () => {
    press(renderer, 'Attach file');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'cloud question');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  const chatCall = calls(harness.fetchImpl).filter(call => new URL(call.url).pathname === '/api/chat');
  expect(chatCall).toHaveLength(1);
  expect(JSON.parse(String(chatCall[0].init?.body))).toEqual({
    message: 'cloud question',
    use_rag: true,
    session_id: 'chat-1',
    attachments: [{filename: 'notes.txt', content_base64: expect.any(String)}],
  });
  expect(paths(harness.fetchImpl)).not.toContain('/api/upload');
  expect(paths(harness.fetchImpl).filter(path => path === '/api/chats')).toHaveLength(1);
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'second cloud');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  expect(paths(harness.fetchImpl).filter(path => path === '/api/chats')).toHaveLength(1);
  const digital = renderer.root.findByProps({accessibilityLabel: 'Digital Brain'});
  await act(async () => {
    digital.props.onValueChange(false);
  });
  const cloudCalls = paths(harness.fetchImpl).filter(path => path === '/api/chat').length;
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'back on device');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  expect(paths(harness.fetchImpl).filter(path => path === '/api/chat')).toHaveLength(cloudCalls);
  expect(harness.engine.stats().loadedPackId).toBe('qwen3.5-4b-finetuned-q4');
});

test('premium without a personal pack uses the base pack and says so', async () => {
  const {brain, fetchImpl, engine} = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 20, sha256: 'aa'},
  });
  fetchImpl.mockImplementation(async () => jsonResponse(200, {access_token: 'tok', user: user('ada', 'premium')}));
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'hello');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  expect(engine.stats().loadedPackId).toBe('qwen3.5-4b-base-q4');
  expect(collect(renderer)).toContain('Your personal model is not built yet.');
  expect(paths(fetchImpl)).not.toContain('/api/chat');
});

test('a second account does not see the first account threads', async () => {
  const {brain, fetchImpl} = makeApp({
    basePack: {id: 'qwen3.5-4b-base-q4', path: 'base.pte', bytes: 20, sha256: 'aa'},
  });
  let who = 'ada';
  fetchImpl.mockImplementation(async () => jsonResponse(200, {access_token: `tok-${who}`, user: user(who, 'free')}));
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    typeInto(renderer, 'Ask anything...', 'secret from Ada');
  });
  await act(async () => {
    press(renderer, 'Send');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Settings');
  });
  who = 'bea';
  await act(async () => {
    press(renderer, 'Sign out');
  });
  expect(collect(renderer)).not.toContain('Local AI Chat');
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'bea@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  expect(collect(renderer)).not.toContain('secret from Ada');
  expect(brain.snapshot.user?.id).toBe('bea');
});

test('free upgrade stores the new premium session and premium does not patch again', async () => {
  const {brain, fetchImpl} = makeApp();
  fetchImpl.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/auth/signin') {
      return jsonResponse(200, {access_token: 'tok-free', user: user('ada', 'free')});
    }
    if (path === '/api/account') {
      return jsonResponse(200, {access_token: 'tok-premium', user: user('ada', 'premium')});
    }
    return jsonResponse(404, {detail: 'missing', body: init?.body});
  });
  const renderer = await render(brain);
  await act(async () => {
    typeInto(renderer, 'you@company.com', 'ada@example.com');
    typeInto(renderer, 'Enter your password', 'secret123');
  });
  await act(async () => {
    press(renderer, 'Continue');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Free vs Premium');
  });
  await act(async () => {
    press(renderer, 'Upgrade to Premium');
  });
  await act(async () => {
    press(renderer, 'Confirm upgrade');
  });
  const patch = calls(fetchImpl).find(call => call.url.endsWith('/api/account'));
  expect(JSON.parse(String(patch?.init?.body))).toEqual({plan: 'premium'});
  expect(brain.snapshot.user?.plan).toBe('premium');
  expect(brain.snapshot.token).toBe('tok-premium');
  fetchImpl.mockClear();
  await act(async () => {
    press(renderer, 'Back');
  });
  await act(async () => {
    press(renderer, 'Menu');
  });
  await act(async () => {
    press(renderer, 'Free vs Premium');
  });
  expect(collect(renderer)).toContain('The Digital Brain is the web app.');
  expect(fetchImpl).not.toHaveBeenCalled();
});
