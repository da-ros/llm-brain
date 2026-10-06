export type Plan = 'free' | 'premium';
export type ThemeChoice = 'system' | 'light' | 'dark';

export type User = {id: string; name: string; email: string; plan: Plan};

export type Session = {access_token: string; user: User};

export type StoredFile = {filename: string; mime: string; text: string; base64: string};

export type Turn = {role: 'user' | 'assistant' | 'note'; text: string};

export type Thread = {
  id: string;
  turns: Turn[];
  files: StoredFile[];
  serverChatId: string | null;
};

export type Pack = {id: string; path: string; bytes: number; sha256: string};

export type UserSandbox = {
  threads: Thread[];
  activeId: string | null;
  keepOnDevice: boolean;
  theme: ThemeChoice;
};

export type Persisted = {
  byUser: Record<string, UserSandbox>;
  basePack: Pack | null;
  loraByUser: Record<string, Pack>;
  cacheBytes: number;
};

export function emptyPersisted(): Persisted {
  return {byUser: {}, basePack: null, loraByUser: {}, cacheBytes: 0};
}

export interface Store {
  load(): Promise<Persisted>;
  save(data: Persisted): Promise<void>;
}

export class MemoryStore implements Store {
  data: Persisted;

  constructor(seed?: Partial<Persisted>) {
    this.data = {...emptyPersisted(), ...seed};
  }

  async load(): Promise<Persisted> {
    return structuredClone(this.data);
  }

  async save(data: Persisted): Promise<void> {
    this.data = structuredClone(data);
  }
}

export interface Keychain {
  get(): Promise<string | null>;
  set(value: string): Promise<void>;
  clear(): Promise<void>;
}

export class MemoryKeychain implements Keychain {
  value: string | null = null;

  async get(): Promise<string | null> {
    return this.value;
  }

  async set(value: string): Promise<void> {
    this.value = value;
  }

  async clear(): Promise<void> {
    this.value = null;
  }
}

export type DownloadedPack = {path: string; bytes: number; sha256: string};

export interface PackFiles {
  write(filename: string, bytes: Uint8Array): Promise<string>;
  remove(path: string): Promise<void>;
  /** Stream a pack to disk. The in-memory write path cannot hold a 2.7 GB GGUF. */
  download?(url: string, filename: string, token: string | null): Promise<DownloadedPack>;
}

export class MemoryPackFiles implements PackFiles {
  files = new Map<string, Uint8Array>();

  async write(filename: string, bytes: Uint8Array): Promise<string> {
    const path = `documents/packs/${filename}`;
    this.files.set(path, bytes);
    return path;
  }

  async remove(path: string): Promise<void> {
    this.files.delete(path);
  }
}

export type PickedFile = {filename: string; mime: string; bytes: Uint8Array};
export type Picker = (kind: 'file' | 'image') => Promise<PickedFile | null>;
