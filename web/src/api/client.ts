import type {
  ApiErrorItem,
  DevelopmentDraft,
  InterruptDraft,
  MutationPreview,
  WorkspaceSnapshot,
} from "../types/workspace";

interface ErrorEnvelope { error: ApiErrorItem }

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
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (error) {
    throw new ApiError({
      code: "INVALID_REQUEST",
      message: error instanceof Error ? error.message : "Network request failed.",
      details: {},
    }, 0);
  }
  if (!response.ok) {
    const fallback: ErrorEnvelope = {
      error: { code: "INVALID_REQUEST", message: `Request failed with status ${response.status}.`, details: {} },
    };
    let envelope = fallback;
    try { envelope = await response.json() as ErrorEnvelope; } catch { /* use fallback */ }
    throw new ApiError(envelope.error, response.status);
  }
  return await response.json() as T;
}

const post = (path: string, body: unknown = {}) =>
  request<WorkspaceSnapshot>(path, { method: "POST", body: JSON.stringify(body) });
const put = (path: string, body: unknown) =>
  request<WorkspaceSnapshot>(path, { method: "PUT", body: JSON.stringify(body) });
const remove = (path: string) =>
  request<WorkspaceSnapshot>(path, { method: "DELETE" });
const preview = (path: string, body: unknown) =>
  request<MutationPreview>(path, { method: "POST", body: JSON.stringify(body) });

export const workspaceApi = {
  createSession: (flowPath?: string) => post("/api/sessions", flowPath ? { flowPath } : {}),
  getSession: (id: string) => request<WorkspaceSnapshot>(`/api/sessions/${id}`),
  submitMove: (id: string, uci: string) => post(`/api/sessions/${id}/moves`, { uci }),
  retry: (id: string) => post(`/api/sessions/${id}/policy/retry`),
  continuePolicy: (id: string) => post(`/api/sessions/${id}/policy/continue`),
  acceptHere: (id: string) => post(`/api/sessions/${id}/attempt/accept-here`),
  back: (id: string) => post(`/api/sessions/${id}/back`),
  restart: (id: string) => post(`/api/sessions/${id}/restart`),
  analyse: (id: string) => post(`/api/sessions/${id}/analysis`),
  previewDevelopment: (id: string, draft: DevelopmentDraft) =>
    preview(`/api/sessions/${id}/development/validate`, draft),
  applyDevelopment: (id: string, draft: DevelopmentDraft) =>
    post(`/api/sessions/${id}/development`, draft),
  deleteDevelopment: (id: string, alias: string) =>
    remove(`/api/sessions/${id}/development/${encodeURIComponent(alias)}`),
  previewInterrupt: (id: string, draft: InterruptDraft) =>
    preview(`/api/sessions/${id}/interrupts/validate`, draft),
  applyInterrupt: (id: string, draft: InterruptDraft) =>
    post(`/api/sessions/${id}/interrupts`, draft),
  deleteInterrupt: (id: string, alias: string, ruleId: string) =>
    remove(`/api/sessions/${id}/interrupts/${encodeURIComponent(alias)}/${encodeURIComponent(ruleId)}`),
  reorderDevelopment: (id: string, aliases: string[]) =>
    put(`/api/sessions/${id}/orders/development`, { aliases }),
  reorderInterrupts: (id: string, ruleRefs: string[]) =>
    put(`/api/sessions/${id}/orders/interrupts`, { ruleRefs }),
};
