import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError, workspaceApi } from "../api/client";
import type {
  DevelopmentDraft,
  InterruptDraft,
  MutationPreview,
  WorkspaceSnapshot,
} from "../types/workspace";

const SESSION_KEY = "chess-rulebook-development-session";

interface WorkspaceContextValue {
  workspace: WorkspaceSnapshot | null;
  loading: boolean;
  pending: boolean;
  error: ApiError | null;
  initialize: () => Promise<void>;
  move: (uci: string) => Promise<void>;
  retry: () => Promise<void>;
  continuePolicy: () => Promise<void>;
  acceptHere: () => Promise<void>;
  back: () => Promise<void>;
  restart: () => Promise<void>;
  analyse: () => Promise<void>;
  previewDevelopment: (draft: DevelopmentDraft) => Promise<MutationPreview>;
  applyDevelopment: (draft: DevelopmentDraft) => Promise<void>;
  deleteDevelopment: (alias: string) => Promise<void>;
  previewInterrupt: (draft: InterruptDraft) => Promise<MutationPreview>;
  applyInterrupt: (draft: InterruptDraft) => Promise<void>;
  deleteInterrupt: (alias: string, ruleId: string) => Promise<void>;
  reorderDevelopment: (aliases: string[]) => Promise<void>;
  reorderInterrupts: (refs: string[]) => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: PropsWithChildren) {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const bootstrapStarted = useRef(false);

  const create = useCallback(async () => {
    const created = await workspaceApi.createSession();
    sessionStorage.setItem(SESSION_KEY, created.sessionId);
    setWorkspace(created);
    setError(null);
  }, []);

  const initialize = useCallback(async () => {
    setLoading(true);
    try {
      const id = sessionStorage.getItem(SESSION_KEY);
      if (!id) await create();
      else {
        try {
          setWorkspace(await workspaceApi.getSession(id));
          setError(null);
        } catch (requestError) {
          if (requestError instanceof ApiError && requestError.code === "SESSION_NOT_FOUND") {
            sessionStorage.removeItem(SESSION_KEY);
            await create();
          } else throw requestError;
        }
      }
    } catch (requestError) {
      setError(asApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, [create]);

  useEffect(() => {
    if (bootstrapStarted.current) return;
    bootstrapStarted.current = true;
    void initialize();
  }, [initialize]);

  const operate = useCallback(async (
    operation: (sessionId: string) => Promise<WorkspaceSnapshot>,
  ) => {
    if (!workspace) return;
    setPending(true);
    setError(null);
    try { setWorkspace(await operation(workspace.sessionId)); }
    catch (requestError) { setError(asApiError(requestError)); }
    finally { setPending(false); }
  }, [workspace]);

  const needWorkspace = useCallback(() => {
    if (!workspace) throw new Error("No active workspace.");
    return workspace;
  }, [workspace]);

  const value = useMemo<WorkspaceContextValue>(() => ({
    workspace, loading, pending, error, initialize,
    move: (uci) => operate((id) => workspaceApi.submitMove(id, uci)),
    retry: () => operate(workspaceApi.retry),
    continuePolicy: () => operate(workspaceApi.continuePolicy),
    acceptHere: () => operate(workspaceApi.acceptHere),
    back: () => operate(workspaceApi.back),
    restart: () => operate(workspaceApi.restart),
    analyse: () => operate(workspaceApi.analyse),
    previewDevelopment: (draft) => {
      const current = needWorkspace();
      return workspaceApi.previewDevelopment(current.sessionId, draft);
    },
    applyDevelopment: (draft) => operate((id) => workspaceApi.applyDevelopment(id, draft)),
    deleteDevelopment: (alias) => operate((id) => workspaceApi.deleteDevelopment(id, alias)),
    previewInterrupt: (draft) => {
      const current = needWorkspace();
      return workspaceApi.previewInterrupt(current.sessionId, draft);
    },
    applyInterrupt: (draft) => operate((id) => workspaceApi.applyInterrupt(id, draft)),
    deleteInterrupt: (alias, ruleId) => operate((id) => workspaceApi.deleteInterrupt(id, alias, ruleId)),
    reorderDevelopment: (aliases) => operate((id) => workspaceApi.reorderDevelopment(id, aliases)),
    reorderInterrupts: (refs) => operate((id) => workspaceApi.reorderInterrupts(id, refs)),
  }), [error, initialize, loading, needWorkspace, operate, pending, workspace]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError({
    code: "INVALID_REQUEST",
    message: error instanceof Error ? error.message : "Unexpected request failure.",
    details: {},
  }, 0);
}
