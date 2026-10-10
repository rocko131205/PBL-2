import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Credibility, Workspace, WorkspaceLoaded } from "./types";

export const WORKSPACE_KEY = ["workspace"] as const;

export function useWorkspace() {
  return useQuery({ queryKey: WORKSPACE_KEY, queryFn: () => api<Workspace>("/workspace") });
}

/** The loaded workspace, or undefined while loading / when nothing is loaded. */
export function useLoadedWorkspace(): WorkspaceLoaded | undefined {
  const { data } = useWorkspace();
  return data?.loaded ? data : undefined;
}

/**
 * Any call that returns a fresh workspace view goes through here: the cache is replaced and the
 * credibility report (computed from the data) is thrown away so it is recomputed.
 */
export function useWorkspaceMutation<TVars>(fn: (vars: TVars) => Promise<Workspace>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (ws) => {
      qc.setQueryData(WORKSPACE_KEY, ws);
      qc.removeQueries({ queryKey: ["credibility"] });
    },
  });
}

export function useCredibility(enabled: boolean) {
  return useQuery({
    queryKey: ["credibility"],
    queryFn: () => api<Credibility>("/workspace/credibility"),
    enabled,
    staleTime: Infinity,
  });
}

export function useClearWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/workspace", { method: "DELETE" }),
    onSuccess: () => {
      qc.setQueryData(WORKSPACE_KEY, { loaded: false });
      qc.removeQueries({ queryKey: ["credibility"] });
    },
  });
}
