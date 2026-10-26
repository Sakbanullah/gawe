import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  confirmProfile,
  correctProfile,
  createApplication,
  createApplicationFromUrl,
  createExport,
  createSource,
  getApplication,
  getBrowserImportToken,
  getConsent,
  getDocumentFindings,
  getDocumentVersion,
  getMasterCv,
  getMatch,
  getOverview,
  getProfileVersion,
  getTask,
  grantConsent,
  listApplications,
  listDiscoveryRuns,
  listExports,
  listMatches,
  listProfiles,
  listSources,
  cancelApplication,
  overrideMatchTier,
  rerunApplicationAnalysis,
  retryTask,
  reviewEligibility,
  revokeConsent,
  rollbackProfile,
  startDiscoveryRun,
  startExtraction,
  updateSource,
  uploadMasterCv,
  approveDocumentVersion,
  createDocumentRevision,
  generateDocuments,
  requestDocumentRevision,
  runDocumentReview,
  type MatchQuery,
  type ExportRequest,
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

export function useImportToken() {
  return useSetupMutation(() => getBrowserImportToken());
}

export function useReviewEligibility() {
  return useSetupMutation(
    (args: { jobId: string; status: "eligible" | "ineligible"; reason: string }) =>
      reviewEligibility(args.jobId, { status: args.status, reason: args.reason }),
  );
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

export function useMatches(query: MatchQuery) {
  return useQuery({
    queryKey: ["matches", query],
    queryFn: () => listMatches(query),
  });
}

export function useMatchDetail(jobId: string | null) {
  return useQuery({
    queryKey: ["match", jobId],
    queryFn: () => getMatch(jobId as string),
    enabled: jobId !== null,
  });
}

export function useOverrideMatchTier() {
  return useSetupMutation(
    (args: {
      jobId: string;
      tier: "P1" | "P2" | "P3" | "P4" | "unclassified" | null;
      reason: string | null;
    }) => overrideMatchTier(args.jobId, { tier: args.tier, reason: args.reason }),
  );
}

export function useApplications(includeCancelled = true) {
  return useQuery({
    queryKey: ["applications", includeCancelled],
    queryFn: () => listApplications({ includeCancelled }),
  });
}

export function useCancelApplication() {
  return useSetupMutation((args: { applicationId: string; reason: string | null }) =>
    cancelApplication(args.applicationId, args.reason),
  );
}

export function useApplication(applicationId: string | undefined) {
  return useQuery({
    queryKey: ["application", applicationId],
    queryFn: () => getApplication(applicationId as string),
    enabled: Boolean(applicationId),
  });
}

export function useCreateApplication() {
  return useSetupMutation((jobId: string) => createApplication(jobId));
}

export function useRerunAnalysis() {
  return useSetupMutation((applicationId: string) =>
    rerunApplicationAnalysis(applicationId, { reason: "user_requested" }),
  );
}

export function useGenerateDocuments() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      applicationId: string;
      kinds: ("cv" | "cover_letter")[];
      language: "en" | "id";
    }) =>
      generateDocuments(args.applicationId, {
        kinds: args.kinds,
        language: args.language,
      }),
    // Generating a CV must not refetch the cover letter and vice versa. Both are
    // read from the application payload, so only that query is refreshed.
    onSuccess: async (_data, args) => {
      await queryClient.invalidateQueries({ queryKey: ["application", args.applicationId] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useDocumentVersion(applicationId: string, documentVersionId: string | null) {
  return useQuery({
    queryKey: ["document", applicationId, documentVersionId],
    queryFn: () =>
      getDocumentVersion(applicationId, documentVersionId as string),
    enabled: Boolean(applicationId && documentVersionId),
  });
}

export function useDocumentFindings(
  applicationId: string,
  documentVersionId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["document-findings", applicationId, documentVersionId],
    queryFn: () => getDocumentFindings(applicationId, documentVersionId as string),
    enabled: Boolean(applicationId && documentVersionId && enabled),
  });
}

export function useCreateDocumentRevision() {
  return useSetupMutation(
    (args: {
      applicationId: string;
      documentVersionId: string;
      baseContentHash: string;
      path: string;
      value: unknown;
    }) =>
      createDocumentRevision(args.applicationId, args.documentVersionId, {
        base_content_hash: args.baseContentHash,
        edits: [{ path: args.path, value: args.value }],
      }),
  );
}

export function useRequestDocumentRevision() {
  return useSetupMutation(
    (args: {
      applicationId: string;
      documentVersionId: string;
      contentHash: string;
      findingIds: string[];
      note?: string;
    }) =>
      requestDocumentRevision(args.applicationId, args.documentVersionId, {
        base_content_hash: args.contentHash,
        reason: "review_changes",
        finding_ids: args.findingIds,
        ...(args.note ? { note: args.note } : {}),
      }),
  );
}

export function useRunDocumentReview() {
  return useSetupMutation(
    (args: { applicationId: string; documentVersionId: string }) =>
      runDocumentReview(args.applicationId, args.documentVersionId),
  );
}

export function useApproveDocument() {
  return useSetupMutation(
    (args: {
      applicationId: string;
      documentVersionId: string;
      contentHash: string;
      decision: "approved" | "rejected" | "changes_requested";
      note?: string | null;
    }) =>
      approveDocumentVersion(args.applicationId, args.documentVersionId, {
        decision: args.decision,
        content_hash: args.contentHash,
        note: args.note ?? undefined,
      }),
  );
}

export function useCreateApplicationFromUrl() {
  return useSetupMutation((args: { url: string; text?: string }) =>
    createApplicationFromUrl(args.url, args.text),
  );
}

export function useExports(applicationId: string | undefined) {
  return useQuery({
    queryKey: ["exports", applicationId],
    queryFn: () => listExports(applicationId as string),
    enabled: Boolean(applicationId),
  });
}

export function useCreateExport() {
  return useSetupMutation(
    (args: { applicationId: string; body: ExportRequest }) =>
      createExport(args.applicationId, args.body),
  );
}
