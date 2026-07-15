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
import type { OverrideUpdate, RuleUpdate, WorkspaceSnapshot } from "../types/workspace";

const SESSION_KEY = "chess-flow-development-session";

interface WorkspaceContextValue {
  workspace: WorkspaceSnapshot | null;
  loading: boolean;
  pending: boolean;
  error: ApiError | null;
  initialize: () => Promise<void>;
  submitMove: (uci: string) => Promise<void>;
  submitSanMove: (san: string) => Promise<void>;
  retryPolicy: () => Promise<void>;
  continuePolicy: () => Promise<void>;
  playNextOpponent: () => Promise<void>;
  analysePosition: () => Promise<void>;
  updateRule: (ruleId: string, update: RuleUpdate) => Promise<void>;
  updateOverride: (overrideId: string, update: OverrideUpdate) => Promise<void>;
  back: () => Promise<void>;
  restart: () => Promise<void>;
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
      const sessionId = sessionStorage.getItem(SESSION_KEY);
      if (!sessionId) {
        await create();
      } else {
        try {
          setWorkspace(await workspaceApi.getSession(sessionId));
          setError(null);
        } catch (requestError) {
          if (requestError instanceof ApiError && requestError.code === "SESSION_NOT_FOUND") {
            sessionStorage.removeItem(SESSION_KEY);
            await create();
          } else {
            throw requestError;
          }
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

  const operate = useCallback(
    async (operation: (sessionId: string) => Promise<WorkspaceSnapshot>) => {
      if (!workspace) return;
      setPending(true);
      setError(null);
      try {
        setWorkspace(await operation(workspace.sessionId));
      } catch (requestError) {
        setError(asApiError(requestError));
      } finally {
        setPending(false);
      }
    },
    [workspace],
  );

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      workspace,
      loading,
      pending,
      error,
      initialize,
      submitMove: (uci) => operate((id) => workspaceApi.submitMove(id, uci)),
      submitSanMove: (san) => operate((id) => workspaceApi.submitSanMove(id, san)),
      retryPolicy: () => operate(workspaceApi.retryPolicy),
      continuePolicy: () => operate(workspaceApi.continuePolicy),
      playNextOpponent: () => operate(workspaceApi.playNextOpponent),
      analysePosition: () => operate(workspaceApi.analysePosition),
      updateRule: (ruleId, update) => operate((id) => workspaceApi.updateRule(id, ruleId, update)),
      updateOverride: (overrideId, update) => operate((id) => workspaceApi.updateOverride(id, overrideId, update)),
      back: () => operate(workspaceApi.back),
      restart: () => operate(workspaceApi.restart),
    }),
    [error, initialize, loading, operate, pending, workspace],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(
    {
      code: "INVALID_REQUEST",
      message: error instanceof Error ? error.message : "Unexpected request failure.",
      details: {},
    },
    0,
  );
}
