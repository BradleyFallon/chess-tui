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
import type { ClientEffect, DevelopmentRuleDraft, DevelopmentRuleValidation, OverrideUpdate, RuleUpdate, StructureUpdate, TypedCommand, WorkspaceSnapshot } from "../types/workspace";

const SESSION_KEY = "chess-flow-development-session";

interface WorkspaceContextValue {
  workspace: WorkspaceSnapshot | null;
  loading: boolean;
  pending: boolean;
  error: ApiError | null;
  effects: ClientEffect[];
  initialize: () => Promise<void>;
  sendChat: (text: string) => Promise<void>;
  executeCommand: (command: TypedCommand) => Promise<void>;
  updateRule: (ruleId: string, update: RuleUpdate) => Promise<void>;
  updateOverride: (overrideId: string, update: OverrideUpdate) => Promise<void>;
  validateDevelopmentRule: (draft: DevelopmentRuleDraft) => Promise<DevelopmentRuleValidation>;
  applyDevelopmentRule: (draft: DevelopmentRuleDraft) => Promise<void>;
  deleteDevelopmentRule: (ruleId: string) => Promise<void>;
  reorderDevelopmentRules: (ruleIds: string[]) => Promise<void>;
  reorderPolicySection: (
    section: "response" | "development" | "continuation",
    itemIds: string[],
  ) => Promise<void>;
  updateStructure: (structureId: string, update: StructureUpdate) => Promise<void>;
  reorderStructures: (structureIds: string[]) => Promise<void>;
  addOpeningTag: (recordId: number) => Promise<void>;
  removeOpeningTag: (recordId: number) => Promise<void>;
  updateAnalysisSettings: (profileId: string) => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: PropsWithChildren) {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [effects, setEffects] = useState<ClientEffect[]>([]);
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
      setEffects([]);
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

  const operateCommand = useCallback(
    async (operation: (sessionId: string) => ReturnType<typeof workspaceApi.sendChat>) => {
      if (!workspace) return;
      setPending(true);
      setError(null);
      setEffects([]);
      try {
        const response = await operation(workspace.sessionId);
        setWorkspace(response.workspace);
        setEffects(response.effects);
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
      effects,
      initialize,
      sendChat: (text) => operateCommand((id) => workspaceApi.sendChat(id, text)),
      executeCommand: (command) => operateCommand((id) => workspaceApi.executeCommand(id, command)),
      updateRule: (ruleId, update) => operate((id) => workspaceApi.updateRule(id, ruleId, update)),
      updateOverride: (overrideId, update) => operate((id) => workspaceApi.updateOverride(id, overrideId, update)),
      validateDevelopmentRule: (draft) => {
        if (!workspace) return Promise.reject(new Error("No active workspace."));
        return workspaceApi.validateDevelopmentRule(workspace.sessionId, draft);
      },
      applyDevelopmentRule: (draft) => operate((id) => workspaceApi.applyDevelopmentRule(id, draft)),
      deleteDevelopmentRule: (ruleId) => operate((id) => workspaceApi.deleteDevelopmentRule(id, ruleId)),
      reorderDevelopmentRules: (ruleIds) => operate((id) => workspaceApi.reorderDevelopmentRules(id, ruleIds)),
      reorderPolicySection: (section, itemIds) =>
        operate((id) => workspaceApi.reorderPolicySection(id, section, itemIds)),
      updateStructure: (structureId, update) =>
        operate((id) => workspaceApi.updateStructure(id, structureId, update)),
      reorderStructures: (structureIds) =>
        operate((id) => workspaceApi.reorderStructures(id, structureIds)),
      addOpeningTag: (recordId) => operate((id) => workspaceApi.addOpeningTag(id, recordId)),
      removeOpeningTag: (recordId) => operate((id) => workspaceApi.removeOpeningTag(id, recordId)),
      updateAnalysisSettings: (profileId) =>
        operate((id) => workspaceApi.updateAnalysisSettings(id, profileId)),
    }),
    [effects, error, initialize, loading, operate, operateCommand, pending, workspace],
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
