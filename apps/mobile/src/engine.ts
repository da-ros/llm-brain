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
  beginChat(): Promise<void>;
}

export class FakeEngine implements OnDeviceEngine {
  loadedPackId: string | null = null;
  modelBytes = 0;
  cacheBytes = 0;
  replies: {elapsedMs: number; outputTokens: number}[] = [];
  chatsBegun = 0;

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

  async beginChat(): Promise<void> {
    this.chatsBegun += 1;
  }
}

type LlamaTimings = {predicted_n?: number; predicted_ms?: number};

type LlamaContext = {
  completion: (params: {
    prompt: string;
    n_predict: number;
    temperature: number;
    stop: string[];
  }) => Promise<{
    text?: string;
    timings?: LlamaTimings;
  }>;
  stopCompletion: () => void | Promise<void>;
  release: () => void | Promise<void>;
  clearCache: (clearData?: boolean) => void | Promise<void>;
};

type LlamaModule = {
  installJsi: () => Promise<void>;
  releaseAllLlama: () => Promise<void>;
  initLlama: (params: {model: string; n_ctx: number; n_gpu_layers: number; use_mlock: boolean}) => Promise<LlamaContext>;
};

function loadFailure(error: unknown): Error {
  const message = error instanceof Error ? error.message : '';
  if (/failed to load model/i.test(message)) {
    return new Error(
      'The on-device model could not be opened. Force-quit Encefalus and open it again. If that still fails, reinstall the model.',
    );
  }
  return error instanceof Error ? error : new Error('The on-device model did not answer.');
}

const STOP = ['<|im_end|>', '<|endoftext|>'];
const ANSWER_TEMPERATURE = 0.2;

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
  private settled: Promise<void> = Promise.resolve();

  async load(pack: LoadedPack): Promise<void> {
    if (this.ready && this.loadedPackId === pack.id && this.context) {
      return;
    }
    const llama = (await import('llama.rn')) as LlamaModule;
    if (this.context) {
      await this.context.release().catch(() => undefined);
      this.context = null;
      this.ready = false;
    } else {
      // A JS reload drops this object and leaves the native model resident.
      // Opening a second copy then fails with "Failed to load model".
      await llama.installJsi();
      await llama.releaseAllLlama();
    }
    const params = {
      model: modelUri(pack.path),
      n_ctx: 2048,
      n_gpu_layers: 99,
      use_mlock: false,
    };
    try {
      this.context = await llama.initLlama(params);
    } catch (error) {
      this.context = null;
      this.ready = false;
      await llama.installJsi();
      await llama.releaseAllLlama();
      try {
        this.context = await llama.initLlama(params);
      } catch (retryError) {
        throw loadFailure(retryError ?? error);
      }
    }
    this.loadedPackId = pack.id;
    this.modelBytes = pack.bytes;
    this.ready = true;
  }

  async generate(prompt: string): Promise<EngineReply> {
    await this.settled;
    if (!this.context) {
      throw new Error('Load a pack before generate');
    }
    const started = Date.now();
    const result = await this.context.completion({
      prompt,
      n_predict: 1024,
      temperature: ANSWER_TEMPERATURE,
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

  async beginChat(): Promise<void> {
    const job = this.settled.then(async () => {
      await this.context?.clearCache(true);
    });
    this.settled = job.then(
      () => undefined,
      () => undefined,
    );
    await job;
  }
}

export function createEngine(): OnDeviceEngine {
  return new LlamaCppEngine();
}
