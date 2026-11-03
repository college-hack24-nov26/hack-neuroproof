import type { ApiError, ApiErrorBody } from "../types/api";

type UnauthorizedHandler = () => void;

export interface RequestOptions extends Omit<RequestInit, "body" | "headers"> {
  body?: BodyInit | null;
  headers?: HeadersInit;
  signal?: AbortSignal;
  authenticated?: boolean;
}

export interface UploadOptions {
  data: FormData;
  signal?: AbortSignal;
  onProgress?: (percent: number) => void;
}

class ApiClient {
  private readonly baseUrl: string;
  private accessToken: string | null = null;
  private onUnauthorized: UnauthorizedHandler | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  setAccessToken(token: string | null): void {
    this.accessToken = token;
  }

  setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
    this.onUnauthorized = handler;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { authenticated = true, headers, ...requestOptions } = options;
    const response = await fetch(this.url(path), {
      ...requestOptions,
      headers: this.headers(headers, authenticated),
    });
    return this.parseResponse<T>(response);
  }

  async download(path: string, signal?: AbortSignal): Promise<Blob> {
    const response = await fetch(this.url(path), {
      headers: this.headers(undefined, true),
      signal,
    });
    if (!response.ok) {
      throw await this.toApiError(response);
    }
    return response.blob();
  }

  upload<T>(path: string, options: UploadOptions): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", this.url(path));
      if (this.accessToken) {
        request.setRequestHeader("Authorization", `Bearer ${this.accessToken}`);
      }
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          options.onProgress?.(Math.round((event.loaded / event.total) * 100));
        }
      };
      request.onerror = () => reject(this.networkError());
      request.onabort = () =>
        reject({
          status: 0,
          code: "request_aborted",
          message: "Request cancelled.",
        });
      request.onload = () => {
        const contentType = request.getResponseHeader("content-type") ?? "";
        let body: unknown = null;
        if (contentType.includes("application/json") && request.responseText) {
          try {
            body = JSON.parse(request.responseText) as unknown;
          } catch {
            body = null;
          }
        }
        if (request.status >= 200 && request.status < 300) {
          resolve(body as T);
          return;
        }
        if (request.status === 401) {
          this.onUnauthorized?.();
        }
        reject(this.errorFromBody(request.status, body));
      };
      options.signal?.addEventListener("abort", () => request.abort(), {
        once: true,
      });
      request.send(options.data);
    });
  }

  private url(path: string): string {
    return `${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  }

  private headers(
    headers: HeadersInit | undefined,
    authenticated: boolean,
  ): Headers {
    const result = new Headers(headers);
    if (authenticated && this.accessToken) {
      result.set("Authorization", `Bearer ${this.accessToken}`);
    }
    if (!result.has("Accept")) {
      result.set("Accept", "application/json");
    }
    return result;
  }

  private async parseResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      throw await this.toApiError(response);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }

  private async toApiError(response: Response): Promise<ApiError> {
    const body = await response.json().catch(() => null);
    if (response.status === 401) {
      this.onUnauthorized?.();
    }
    return this.errorFromBody(response.status, body);
  }

  private errorFromBody(status: number, body: unknown): ApiError {
    const error = (body as ApiErrorBody | null)?.error;
    return {
      status,
      code: error?.code ?? "request_failed",
      message:
        error?.message ??
        (status === 0 ? "Network connection failed." : "Request failed."),
      requestId: error?.request_id,
    };
  }

  private networkError(): ApiError {
    return {
      status: 0,
      code: "network_error",
      message: "Network connection failed.",
    };
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export const apiClient = new ApiClient(apiBaseUrl);
