import type { ApiErrorItem, WorkspaceSnapshot } from "../types/workspace";

interface ErrorEnvelope {
  error: ApiErrorItem;
}

export class ApiError extends Error {
  readonly code: ApiErrorItem["code"];
  readonly details: Record<string, unknown>;
  readonly status: number;

  constructor(item: ApiErrorItem, status: number) {
    super(item.message);
    this.name = "ApiError";
    this.code = item.code;
    this.details = item.details;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (error) {
    throw new ApiError(
      {
        code: "INVALID_REQUEST",
        message: error instanceof Error ? error.message : "Network request failed.",
        details: {},
      },
      0,
    );
  }
  if (!response.ok) {
    let envelope: ErrorEnvelope;
    try {
      envelope = (await response.json()) as ErrorEnvelope;
    } catch {
      envelope = {
        error: {
          code: "INVALID_REQUEST",
          message: `Request failed with status ${response.status}.`,
          details: {},
        },
      };
    }
    throw new ApiError(envelope.error, response.status);
  }
  return (await response.json()) as T;
}

const post = (path: string, body?: unknown) =>
  request<WorkspaceSnapshot>(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });

export const workspaceApi = {
  createSession: (flowPath?: string) =>
    post("/api/sessions", flowPath ? { flowPath } : {}),
  getSession: (sessionId: string) =>
    request<WorkspaceSnapshot>(`/api/sessions/${sessionId}`),
  submitMove: (sessionId: string, uci: string) =>
    post(`/api/sessions/${sessionId}/moves`, { uci }),
  retryWhite: (sessionId: string) =>
    post(`/api/sessions/${sessionId}/white/retry`),
  keepWhite: (sessionId: string) =>
    post(`/api/sessions/${sessionId}/white/keep`),
  continueWhite: (sessionId: string) =>
    post(`/api/sessions/${sessionId}/white/continue`),
  playNextBlack: (sessionId: string) =>
    post(`/api/sessions/${sessionId}/black/next`),
  back: (sessionId: string) => post(`/api/sessions/${sessionId}/back`),
  restart: (sessionId: string) => post(`/api/sessions/${sessionId}/restart`),
};
