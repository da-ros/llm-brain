import {API_BASE_URL} from './config';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type FetchImpl = typeof fetch;

export class RouterApi {
  token: string | null = null;

  constructor(
    readonly base: string = API_BASE_URL,
    private fetchImpl: FetchImpl = fetch,
  ) {
    if (/:(800[1-8])\b/.test(base)) {
      throw new Error('The phone calls only the API Router');
    }
  }

  get<T>(path: string): Promise<T> {
    return this.request(path, {method: 'GET'});
  }

  post<T>(path: string, body: unknown): Promise<T> {
    return this.request(path, {method: 'POST', body});
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request(path, {method: 'PATCH', body});
  }

  async delete(path: string): Promise<void> {
    const response = await this.send(path, {method: 'DELETE'});
    if (!response.ok) {
      throw await this.fail(response);
    }
  }

  async file(path: string): Promise<Uint8Array> {
    const response = await this.send(path, {method: 'GET'});
    if (!response.ok) {
      throw await this.fail(response);
    }
    const buffer = await response.arrayBuffer();
    return new Uint8Array(buffer);
  }

  private async request<T>(path: string, init: {method: string; body?: unknown}): Promise<T> {
    const response = await this.send(path, init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw await this.fail(response, payload);
    }
    return payload as T;
  }

  private async send(path: string, init: {method: string; body?: unknown}): Promise<Response> {
    const headers: Record<string, string> = {
      'X-Request-ID': `mobile-${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`,
    };
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }
    let body: string | undefined;
    if (init.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(init.body);
    }
    return this.fetchImpl(`${this.base}${path}`, {method: init.method, headers, body});
  }

  private async fail(response: Response, payload?: {detail?: unknown}): Promise<ApiError> {
    const body = payload ?? (await response.json().catch(() => ({})));
    return new ApiError(response.status, detailMessage(body, response.status));
  }
}

function detailMessage(body: {detail?: unknown}, status: number): string {
  if (typeof body.detail === 'string') {
    return body.detail;
  }
  if (Array.isArray(body.detail) && body.detail[0] && typeof body.detail[0] === 'object') {
    const msg = (body.detail[0] as {msg?: string}).msg;
    if (msg) {
      return msg;
    }
  }
  return `Request failed (${status})`;
}
