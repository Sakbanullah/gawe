import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  confirmProfile,
  correctProfile,
  createSource,
  getConsent,
  getMasterCv,
  getOverview,
  getProfileVersion,
  getTask,
  grantConsent,
  listDiscoveryRuns,
  listProfiles,
  listSources,
  retryTask,
  revokeConsent,
  rollbackProfile,
  startDiscoveryRun,
  startExtraction,
  updateSource,
  uploadMasterCv,
} from "./apiClient";

export function useOverview() {
  return useQuery({ queryKey: ["overview"], queryFn: getOverview });
}

export function useMasterCv() {
  return useQuery({
    queryKey: ["master-cv"],
    queryFn: async () => {
      try {
        return await getMasterCv();
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
  });
}

export function useProfiles() {
  return useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
}

export function useProfileVersion(profileVersionId: string | null) {
  return useQuery({
    queryKey: ["profile", profileVersionId],
    queryFn: () => getProfileVersion(profileVersionId as string),
    enabled: profileVersionId !== null,
  });
}

function useSetupMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
  });
}

export function useUploadMasterCv() {
  return useSetupMutation(uploadMasterCv);
}

export function useStartExtraction() {
  return useSetupMutation(startExtraction);
}

export function useCorrectProfile() {
  return useSetupMutation(
    (args: { profileVersionId: string; expectedVersion: number; path: string; value: unknown }) =>
      correctProfile(args.profileVersionId, args.expectedVersion, [
        { path: args.path, value: args.value },
      ]),
  );
}

export function useConfirmProfile() {
  return useSetupMutation((args: { profileVersionId: string }) =>
    confirmProfile(args.profileVersionId),
  );
}

export function useRollbackProfile() {
  return useSetupMutation((args: { targetProfileVersionId: string; reason: string }) =>
    rollbackProfile(args.targetProfileVersionId, args.reason),
  );
}

export function useConsent() {
  return useQuery({ queryKey: ["consent"], queryFn: getConsent });
}

export function useGrantConsent() {
  return useSetupMutation((args: { providerId: string; dataClasses: string[] }) =>
    grantConsent({ provider_id: args.providerId, data_classes: args.dataClasses }),
  );
}

export function useRevokeConsent() {
  return useSetupMutation((consentId: string) => revokeConsent(consentId));
}

export function useSources() {
  return useQuery({ queryKey: ["sources"], queryFn: listSources });
}

export function useDiscoveryRuns() {
  return useQuery({ queryKey: ["discovery-runs"], queryFn: listDiscoveryRuns });
}

export function useTask(taskId: string | null) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId as string),
    enabled: taskId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "processing" ? 1000 : false;
    },
  });
}

export function useCreateSource() {
  return useSetupMutation((body: Parameters<typeof createSource>[0]) => createSource(body));
}

export function useUpdateSource() {
  return useSetupMutation(
    (args: { sourceId: string; body: Parameters<typeof updateSource>[1] }) =>
      updateSource(args.sourceId, args.body),
  );
}

export function useStartDiscoveryRun() {
  return useSetupMutation(() => startDiscoveryRun());
}

export function useRetryTask() {
  return useSetupMutation(
    (args: { taskId: string; scope?: "all" | "failed_sources" }) =>
      retryTask(args.taskId, args.scope ?? "failed_sources"),
  );
}
