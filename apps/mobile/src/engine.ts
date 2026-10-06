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

type LlamaTimings = {predicted_n?: number; predicted_ms?: number};

type LlamaContext = {
  completion: (params: {prompt: string; n_predict: number; stop: string[]}) => Promise<{
    text?: string;
    timings?: LlamaTimings;
  }>;
  stopCompletion: () => void | Promise<void>;
  release: () => void | Promise<void>;
};

const STOP = ['<|im_end|>', '<|endoftext|>'];

function modelUri(path: string): string {
  if (path.startsWith('file://')) {
    return path;
  }
  return `file://${path}`;
}

/** Q4 GGUF on the iPhone GPU through llama.cpp (Metal). */
export class LlamaCppEngine implements OnDeviceEngine {
  loadedPackId: string | null = null;
  modelBytes = 0;
  cacheBytes = 0;
  ready = false;
  replies: {elapsedMs: number; outputTokens: number}[] = [];
  private context: LlamaContext | null = null;

  async load(pack: LoadedPack): Promise<void> {
    const {initLlama} = (await import('llama.rn')) as {
      initLlama: (params: {model: string; n_ctx: number; n_gpu_layers: number; use_mlock: boolean}) => Promise<LlamaContext>;
    };
    if (this.context) {
      await this.context.release();
      this.context = null;
      this.ready = false;
    }
    this.context = await initLlama({
      model: modelUri(pack.path),
      n_ctx: 2048,
      n_gpu_layers: 99,
      use_mlock: false,
    });
    this.loadedPackId = pack.id;
    this.modelBytes = pack.bytes;
    this.ready = true;
  }

  async generate(prompt: string): Promise<EngineReply> {
    if (!this.context) {
      throw new Error('Load a pack before generate');
    }
    const started = Date.now();
    const result = await this.context.completion({
      prompt,
      n_predict: 256,
      stop: STOP,
    });
    const text = (result.text ?? '').trim();
    const elapsedMs = result.timings?.predicted_ms ?? Date.now() - started;
    const outputTokens = result.timings?.predicted_n ?? Math.max(1, text.split(/\s+/).filter(Boolean).length);
    const reply = {text, elapsedMs, outputTokens};
    this.replies.push({elapsedMs, outputTokens});
    return reply;
  }

  cancel(): void {
    void this.context?.stopCompletion();
  }

  stats(): EngineStats {
    return {
      loadedPackId: this.loadedPackId,
      modelBytes: this.modelBytes,
      cacheBytes: this.cacheBytes,
      ready: this.ready,
      replies: this.replies,
    };
  }

  clearCache(): void {
    this.cacheBytes = 0;
  }
}

export function createEngine(): OnDeviceEngine {
  return new LlamaCppEngine();
}
