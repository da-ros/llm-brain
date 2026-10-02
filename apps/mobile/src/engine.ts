import {NativeModules} from 'react-native';

export type EngineReply = {text: string; elapsedMs: number; outputTokens: number};

export type EngineStats = {
  loadedPackId: string | null;
  modelBytes: number;
  cacheBytes: number;
  ready: boolean;
  replies: {elapsedMs: number; outputTokens: number}[];
};

export type LoadedPack = {id: string; path: string; bytes: number};

export interface OnDeviceEngine {
  load(pack: LoadedPack): Promise<void>;
  generate(prompt: string): Promise<EngineReply>;
  cancel(): void;
  stats(): EngineStats;
  clearCache(): void;
}

export class FakeEngine implements OnDeviceEngine {
  loadedPackId: string | null = null;
  modelBytes = 0;
  cacheBytes = 0;
  replies: {elapsedMs: number; outputTokens: number}[] = [];

  async load(pack: LoadedPack): Promise<void> {
    this.loadedPackId = pack.id;
    this.modelBytes = pack.bytes;
  }

  async generate(prompt: string): Promise<EngineReply> {
    const reply = {text: `Received: ${prompt}`, elapsedMs: 40, outputTokens: 12};
    this.replies.push({elapsedMs: reply.elapsedMs, outputTokens: reply.outputTokens});
    return reply;
  }

  cancel(): void {}

  stats(): EngineStats {
    return {
      loadedPackId: this.loadedPackId,
      modelBytes: this.modelBytes,
      cacheBytes: this.cacheBytes,
      ready: this.loadedPackId != null,
      replies: this.replies,
    };
  }

  clearCache(): void {
    this.cacheBytes = 0;
  }
}

type NativeLlm = {
  load: (path: string) => Promise<{ready: boolean; bytes: number}>;
  generate: (prompt: string) => Promise<EngineReply>;
  cancel: () => void;
  stats: () => Promise<{modelBytes: number; cacheBytes: number; ready: boolean}>;
};

export class NativeOnDeviceEngine implements OnDeviceEngine {
  loadedPackId: string | null = null;
  modelBytes = 0;
  cacheBytes = 0;
  ready = false;

  constructor(private native: NativeLlm) {}

  async load(pack: LoadedPack): Promise<void> {
    const result = await this.native.load(pack.path);
    this.loadedPackId = pack.id;
    this.modelBytes = result.bytes || pack.bytes;
    this.ready = result.ready;
  }

  async generate(prompt: string): Promise<EngineReply> {
    return this.native.generate(prompt);
  }

  cancel(): void {
    this.native.cancel();
  }

  stats(): EngineStats {
    return {
      loadedPackId: this.loadedPackId,
      modelBytes: this.modelBytes,
      cacheBytes: this.cacheBytes,
      ready: this.ready,
      replies: [],
    };
  }

  clearCache(): void {
    this.cacheBytes = 0;
  }
}

export function createEngine(): OnDeviceEngine {
  const native = NativeModules.OnDeviceLlm as NativeLlm | undefined;
  if (native && typeof native.generate === 'function') {
    return new NativeOnDeviceEngine(native);
  }
  return new FakeEngine();
}
