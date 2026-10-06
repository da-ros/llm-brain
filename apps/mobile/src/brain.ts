import {NativeModules} from 'react-native';

import {RouterApi} from './api';
import {checksum, toBase64} from './bytes';
import {API_BASE_URL} from './config';
import {createEngine, type OnDeviceEngine} from './engine';
import {buildPrompt, extractText, isImage} from './files';
import {
  emptyPersisted,
  MemoryKeychain,
  MemoryPackFiles,
  MemoryStore,
  type Keychain,
  type Pack,
  type PackFiles,
  type Persisted,
  type PickedFile,
  type Picker,
  type Plan,
  type Session,
  type Store,
  type ThemeChoice,
  type Thread,
  type UserSandbox,
} from './storage';

export type Snapshot = {
  ready: boolean;
  token: string | null;
  user: Session['user'] | null;
  threads: Thread[];
  activeId: string | null;
  keepOnDevice: boolean;
  theme: ThemeChoice;
  basePack: Pack | null;
  loraPack: Pack | null;
  cacheBytes: number;
  error: string | null;
  notice: string | null;
  confirmUpgrade: boolean;
  confirmClear: boolean;
};

const PERSONAL_NOTE = 'Your personal model is not built yet.';

function emptySnapshot(): Snapshot {
  return {
    ready: false,
    token: null,
    user: null,
    threads: [],
    activeId: null,
    keepOnDevice: true,
    theme: 'system',
    basePack: null,
    loraPack: null,
    cacheBytes: 0,
    error: null,
    notice: null,
    confirmUpgrade: false,
    confirmClear: false,
  };
}

export type BrainDeps = {
  api: RouterApi;
  store: Store;
  keychain: Keychain;
  engine: OnDeviceEngine;
  files: PackFiles;
  picker: Picker;
};

export class Brain {
  snapshot: Snapshot = emptySnapshot();
  private listeners = new Set<(snapshot: Snapshot) => void>();
  private persisted: Persisted = emptyPersisted();
  private booted = false;

  constructor(private deps: BrainDeps) {}

  subscribe(listener: (snapshot: Snapshot) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async boot(): Promise<void> {
    if (this.booted) {
      return;
    }
    this.booted = true;
    this.persisted = await this.deps.store.load();
    this.snapshot.basePack = this.persisted.basePack;
    this.snapshot.cacheBytes = this.persisted.cacheBytes;
    if ('cacheBytes' in this.deps.engine) {
      (this.deps.engine as OnDeviceEngine & {cacheBytes: number}).cacheBytes = this.persisted.cacheBytes;
    }
    const raw = await this.deps.keychain.get();
    if (raw) {
      try {
        this.applySession(JSON.parse(raw) as Session);
      } catch {
        this.snapshot.token = null;
      }
    }
    this.snapshot.ready = true;
    this.commit();
  }

  async signIn(email: string, password: string): Promise<void> {
    await this.auth('/api/auth/signin', {email, password});
  }

  async signUp(name: string, email: string, password: string): Promise<void> {
    await this.auth('/api/auth/signup', {name, email, password, plan: 'free'});
  }

  async signOut(): Promise<void> {
    const userId = this.snapshot.user?.id;
    if (userId) {
      const lora = this.persisted.loraByUser[userId];
      if (lora) {
        await this.deps.files.remove(lora.path);
      }
      delete this.persisted.loraByUser[userId];
      delete this.persisted.byUser[userId];
    }
    await this.deps.keychain.clear();
    await this.deps.store.save(this.persisted);
    this.snapshot = {
      ...emptySnapshot(),
      ready: true,
      basePack: this.persisted.basePack,
      cacheBytes: this.persisted.cacheBytes,
    };
    this.commit();
  }

  newThread(): void {
    const thread = blankThread();
    this.snapshot.threads = [thread, ...this.snapshot.threads];
    this.snapshot.activeId = thread.id;
    this.snapshot.error = null;
    this.commit();
    void this.persistUser();
  }

  setTheme(theme: ThemeChoice): void {
    this.snapshot.theme = theme;
    this.commit();
    void this.persistUser();
  }

  cycleTheme(): void {
    const order: ThemeChoice[] = ['system', 'light', 'dark'];
    const next = order[(order.indexOf(this.snapshot.theme) + 1) % order.length];
    this.setTheme(next);
  }

  setKeepOnDevice(on: boolean): void {
    if (this.snapshot.user?.plan !== 'premium') {
      this.snapshot.keepOnDevice = true;
      this.commit();
      return;
    }
    this.snapshot.keepOnDevice = on;
    this.snapshot.notice = null;
    this.commit();
    void this.persistUser();
  }

  askUpgrade(): void {
    if (this.snapshot.user?.plan === 'premium') {
      this.snapshot.notice = 'The Digital Brain is the web app.';
      this.snapshot.confirmUpgrade = false;
      this.commit();
      return;
    }
    this.snapshot.confirmUpgrade = true;
    this.commit();
  }

  async upgrade(): Promise<void> {
    if (this.snapshot.user?.plan === 'premium') {
      return;
    }
    this.syncToken();
    try {
      const session = await this.deps.api.patch<Session>('/api/account', {plan: 'premium'});
      await this.remember(session);
      this.snapshot.confirmUpgrade = false;
      this.snapshot.notice = null;
      this.commit();
    } catch (error) {
      this.fail(error);
    }
  }

  askClear(): void {
    this.snapshot.confirmClear = true;
    this.commit();
  }

  cancelClear(): void {
    this.snapshot.confirmClear = false;
    this.commit();
  }

  async clearAll(): Promise<void> {
    if (this.snapshot.basePack) {
      await this.deps.files.remove(this.snapshot.basePack.path);
    }
    if (this.snapshot.loraPack) {
      await this.deps.files.remove(this.snapshot.loraPack.path);
    }
    const userId = this.snapshot.user?.id;
    if (userId) {
      delete this.persisted.loraByUser[userId];
      const sandbox = this.persisted.byUser[userId];
      if (sandbox) {
        sandbox.threads = [];
        sandbox.activeId = null;
      }
    }
    this.persisted.basePack = null;
    this.persisted.cacheBytes = 0;
    this.deps.engine.clearCache();
    this.snapshot.basePack = null;
    this.snapshot.loraPack = null;
    this.snapshot.cacheBytes = 0;
    this.snapshot.threads = [];
    this.snapshot.activeId = null;
    this.snapshot.confirmClear = false;
    this.snapshot.notice = 'Conversations, cache, and model files were removed from this iPhone.';
    await this.deps.store.save(this.persisted);
    this.commit();
  }

  async clearCache(): Promise<void> {
    this.deps.engine.clearCache();
    this.persisted.cacheBytes = 0;
    this.snapshot.cacheBytes = 0;
    await this.deps.store.save(this.persisted);
    this.commit();
  }

  async attach(kind: 'file' | 'image'): Promise<void> {
    const picked = await this.deps.picker(kind);
    if (!picked) {
      return;
    }
    const thread = this.ensureThread();
    if (thread.files.length >= 5) {
      this.snapshot.error = 'You can attach up to five files.';
      this.commit();
      return;
    }
    const image = kind === 'image' || isImage(picked.filename, picked.mime);
    if (this.onDevice() && image) {
      this.snapshot.error = 'Images are not sent to the on-device model.';
      this.commit();
      return;
    }
    const text = extractText(picked.filename, picked.bytes) ?? '';
    if (this.onDevice() && !text.trim()) {
      this.snapshot.error = 'This file has no text the phone can read.';
      this.commit();
      return;
    }
    thread.files.push({
      filename: picked.filename,
      mime: picked.mime,
      text,
      base64: toBase64(picked.bytes),
    });
    this.snapshot.error = null;
    this.commit();
    await this.persistUser();
  }

  async send(text: string): Promise<boolean> {
    const question = text.trim();
    if (!question) {
      return false;
    }
    const thread = this.ensureThread();
    if (this.onDevice()) {
      return this.sendOnDevice(thread, question);
    }
    return this.sendCloud(thread, question);
  }

  async reinstall(): Promise<void> {
    this.syncToken();
    const previousBase = this.snapshot.basePack;
    const previousLora = this.snapshot.loraPack;
    try {
      const meta = await this.deps.api.get<{
        id: string;
        filename: string;
        sha256: string;
        ready: boolean;
      }>('/api/models/on-device');
      if (!meta.ready || !meta.filename || !meta.sha256) {
        this.snapshot.error = 'The on-device pack is not ready.';
        this.commit();
        return;
      }
      const pack = await this.fetchPack(meta);
      if (!pack) {
        this.snapshot.basePack = previousBase;
        this.snapshot.loraPack = previousLora;
        this.snapshot.error = 'The download did not match its checksum. The installed pack was kept.';
        this.commit();
        return;
      }
      if (this.snapshot.user?.plan === 'premium') {
        this.snapshot.loraPack = pack;
        if (this.snapshot.user) {
          this.persisted.loraByUser[this.snapshot.user.id] = pack;
        }
      } else {
        this.snapshot.basePack = pack;
        this.persisted.basePack = pack;
      }
      this.snapshot.error = null;
      this.snapshot.notice = 'Model installed.';
      await this.deps.store.save(this.persisted);
      this.commit();
    } catch (error) {
      this.snapshot.basePack = previousBase;
      this.snapshot.loraPack = previousLora;
      this.fail(error, 'The download failed. The installed pack was kept.');
    }
  }

  private async fetchPack(meta: {id: string; filename: string; sha256: string}): Promise<Pack | null> {
    const expected = meta.sha256.toLowerCase();
    if (this.deps.files.download) {
      const saved = await this.deps.files.download(
        `${API_BASE_URL}/api/models/on-device/file`,
        meta.filename,
        this.snapshot.token,
      );
      if (saved.sha256.toLowerCase() !== expected) {
        await this.deps.files.remove(saved.path);
        return null;
      }
      return {id: meta.id, path: saved.path, bytes: saved.bytes, sha256: expected};
    }
    const bytes = await this.deps.api.file('/api/models/on-device/file');
    if (checksum(bytes) !== expected) {
      return null;
    }
    const path = await this.deps.files.write(meta.filename, bytes);
    return {id: meta.id, path, bytes: bytes.byteLength, sha256: expected};
  }

  onDevice(): boolean {
    if (this.snapshot.user?.plan !== 'premium') {
      return true;
    }
    return this.snapshot.keepOnDevice;
  }

  averageShortMs(): number | null {
    const shorts = this.deps.engine.stats().replies.filter(reply => reply.outputTokens <= 64);
    if (!shorts.length) {
      return null;
    }
    return shorts.reduce((sum, reply) => sum + reply.elapsedMs, 0) / shorts.length;
  }

  activeThread(): Thread | null {
    return this.snapshot.threads.find(thread => thread.id === this.snapshot.activeId) ?? null;
  }

  measuredStorage(): number {
    const packs = (this.snapshot.basePack?.bytes ?? 0) + (this.snapshot.loraPack?.bytes ?? 0);
    const files = this.snapshot.threads.reduce(
      (sum, thread) => sum + thread.files.reduce((inner, file) => inner + file.base64.length, 0),
      0,
    );
    return packs + this.snapshot.cacheBytes + files;
  }

  private async sendOnDevice(thread: Thread, question: string): Promise<boolean> {
    const choice = this.devicePack();
    if (!choice.pack) {
      this.snapshot.error = 'Download the model to chat on this iPhone.';
      this.commit();
      return false;
    }
    try {
      await this.deps.engine.load(choice.pack);
      const result = await this.deps.engine.generate(buildPrompt(question, thread.files));
      const correlationId = `mobile-${Date.now().toString(16)}`;
      const timestamp = new Date().toISOString().slice(0, 19);
      console.info(
        `${timestamp} [${correlationId}] INFO mobile: on-device generate pack=${choice.pack.id}`,
      );
      thread.turns.push({role: 'user', text: question});
      if (choice.fallback) {
        thread.turns.push({role: 'note', text: PERSONAL_NOTE});
      }
      thread.turns.push({role: 'assistant', text: result.text});
      this.snapshot.error = null;
      this.commit();
      await this.persistUser();
      return true;
    } catch (error) {
      this.fail(error, 'The on-device model did not answer.');
      return false;
    }
  }

  private async sendCloud(thread: Thread, question: string): Promise<boolean> {
    this.syncToken();
    try {
      if (!thread.serverChatId) {
        const created = await this.deps.api.post<{id: string}>('/api/chats', {});
        thread.serverChatId = created.id;
      }
      const attachments = thread.files.slice(0, 5).map(file => ({
        filename: file.filename,
        content_base64: file.base64,
      }));
      const response = await this.deps.api.post<{response: string}>('/api/chat', {
        message: question,
        use_rag: true,
        session_id: thread.serverChatId,
        attachments,
      });
      thread.turns.push({role: 'user', text: question});
      thread.turns.push({role: 'assistant', text: response.response || ''});
      this.snapshot.error = null;
      this.commit();
      await this.persistUser();
      return true;
    } catch (error) {
      this.fail(error);
      return false;
    }
  }

  private devicePack(): {pack: Pack | null; fallback: boolean} {
    if (this.snapshot.user?.plan === 'premium') {
      if (this.snapshot.loraPack) {
        return {pack: this.snapshot.loraPack, fallback: false};
      }
      return {pack: this.snapshot.basePack, fallback: this.snapshot.basePack != null};
    }
    return {pack: this.snapshot.basePack, fallback: false};
  }

  private async auth(path: string, body: unknown): Promise<void> {
    try {
      const session = await this.deps.api.post<Session>(path, body);
      await this.remember(session);
    } catch (error) {
      this.fail(error);
    }
  }

  private async remember(session: Session): Promise<void> {
    await this.deps.keychain.set(JSON.stringify(session));
    this.applySession(session);
    this.snapshot.error = null;
    this.commit();
  }

  private applySession(session: Session): void {
    const sandbox = this.persisted.byUser[session.user.id] ?? defaultSandbox();
    this.persisted.byUser[session.user.id] = sandbox;
    this.snapshot.token = session.access_token;
    this.snapshot.user = session.user;
    this.snapshot.threads = sandbox.threads;
    this.snapshot.activeId = sandbox.activeId;
    this.snapshot.keepOnDevice = session.user.plan === 'premium' ? sandbox.keepOnDevice : true;
    this.snapshot.theme = sandbox.theme;
    this.snapshot.loraPack = this.persisted.loraByUser[session.user.id] ?? null;
    this.snapshot.basePack = this.persisted.basePack;
    this.deps.api.token = session.access_token;
  }

  private ensureThread(): Thread {
    const existing = this.activeThread();
    if (existing) {
      return existing;
    }
    const thread = blankThread();
    this.snapshot.threads = [thread, ...this.snapshot.threads];
    this.snapshot.activeId = thread.id;
    return thread;
  }

  private syncToken(): void {
    this.deps.api.token = this.snapshot.token;
  }

  private async persistUser(): Promise<void> {
    const user = this.snapshot.user;
    if (!user) {
      return;
    }
    this.persisted.byUser[user.id] = {
      threads: this.snapshot.threads,
      activeId: this.snapshot.activeId,
      keepOnDevice: this.snapshot.keepOnDevice,
      theme: this.snapshot.theme,
    };
    this.persisted.cacheBytes = this.snapshot.cacheBytes;
    this.persisted.basePack = this.snapshot.basePack;
    if (this.snapshot.loraPack) {
      this.persisted.loraByUser[user.id] = this.snapshot.loraPack;
    }
    await this.deps.store.save(this.persisted);
  }

  private fail(error: unknown, fallback = 'Something went wrong.'): void {
    this.snapshot.error = error instanceof Error && error.message ? error.message : fallback;
    this.commit();
  }

  private commit(): void {
    this.snapshot = JSON.parse(JSON.stringify(this.snapshot)) as Snapshot;
    this.listeners.forEach(listener => listener(this.snapshot));
  }
}

function blankThread(): Thread {
  return {id: `t-${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`, turns: [], files: [], serverChatId: null};
}

function defaultSandbox(): UserSandbox {
  return {threads: [], activeId: null, keepOnDevice: true, theme: 'system'};
}

export function createBrain(overrides: Partial<BrainDeps> = {}): Brain {
  const api = overrides.api ?? new RouterApi(API_BASE_URL);
  return new Brain({
    api,
    store: overrides.store ?? createStore(),
    keychain: overrides.keychain ?? createKeychain(),
    engine: overrides.engine ?? createEngine(),
    files: overrides.files ?? createPackFiles(),
    picker: overrides.picker ?? nativePicker,
  });
}

function createKeychain(): Keychain {
  const native = NativeModules.EncefalusKeychain as
    | {get: () => Promise<string>; set: (value: string) => Promise<boolean>; clear: () => Promise<boolean>}
    | undefined;
  if (!native) {
    return new MemoryKeychain();
  }
  return {
    async get() {
      const value = await native.get();
      return value || null;
    },
    async set(value: string) {
      await native.set(value);
    },
    async clear() {
      await native.clear();
    },
  };
}

function createStore(): Store {
  const native = NativeModules.EncefalusSandbox as
    | {load: () => Promise<string>; save: (json: string) => Promise<boolean>}
    | undefined;
  if (!native) {
    return new MemoryStore();
  }
  return {
    async load() {
      const text = await native.load();
      if (!text) {
        return emptyPersisted();
      }
      return {...emptyPersisted(), ...(JSON.parse(text) as Persisted)};
    },
    async save(data: Persisted) {
      await native.save(JSON.stringify(data));
    },
  };
}

function createPackFiles(): PackFiles {
  const native = NativeModules.EncefalusSandbox as
    | {
        writePack: (filename: string, base64: string) => Promise<string>;
        remove: (path: string) => Promise<boolean>;
        downloadPack?: (url: string, filename: string, token: string) => Promise<{path: string; bytes: number; sha256: string}>;
      }
    | undefined;
  if (!native?.writePack) {
    return new MemoryPackFiles();
  }
  return {
    async write(filename: string, bytes: Uint8Array) {
      return native.writePack(filename, toBase64(bytes));
    },
    async remove(path: string) {
      await native.remove(path);
    },
    download: native.downloadPack
      ? (url, filename, token) => native.downloadPack!(url, filename, token ?? '')
      : undefined,
  };
}

export const nativePicker: Picker = async kind => {
  const picker = NativeModules.EncefalusPicker as
    | {pick: (kind: string) => Promise<{filename?: string; mime?: string; base64?: string}>}
    | undefined;
  if (!picker) {
    return null;
  }
  const picked = await picker.pick(kind);
  if (!picked?.filename || !picked.base64) {
    return null;
  }
  const {fromBase64} = await import('./bytes');
  return {
    filename: picked.filename,
    mime: picked.mime || 'application/octet-stream',
    bytes: fromBase64(picked.base64),
  };
};

export type {PickedFile, Plan};
