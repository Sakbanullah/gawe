import type { components } from "./api-types.gen";

export type Overview = components["schemas"]["Overview"];
export type Session = components["schemas"]["Session"];
export type MasterCv = components["schemas"]["MasterCv"];
export type MasterCvUploadResult = components["schemas"]["MasterCvUploadResult"];
export type ProfileVersion = components["schemas"]["ProfileVersion"];
export type ProfileSummary = components["schemas"]["ProfileSummary"];
export type ProfileList = components["schemas"]["ProfileList"];
export type Task = components["schemas"]["Task"];
export type TaskCreated = components["schemas"]["TaskCreated"];
export type ConsentStatus = components["schemas"]["ConsentStatus"];
export type ConsentRecord = components["schemas"]["ConsentRecord"];
export type SourceRegistryEntry = components["schemas"]["SourceRegistryEntry"];
export type SourceList = components["schemas"]["SourceList"];
export type SourceCreateRequest = components["schemas"]["SourceCreateRequest"];
export type SourceUpdateRequest = components["schemas"]["SourceUpdateRequest"];
export type DiscoveryRun = components["schemas"]["DiscoveryRun"];
export type DiscoveryRunList = components["schemas"]["DiscoveryRunList"];
export type MatchList = components["schemas"]["MatchList"];
export type MatchItem = components["schemas"]["MatchItem"];
export type MatchDetail = components["schemas"]["MatchDetail"];
export type TierOverrideRequest = components["schemas"]["TierOverrideRequest"];
export type ApplicationList = components["schemas"]["ApplicationList"];
export type ApplicationSummary = components["schemas"]["ApplicationSummary"];
export type ApplicationCreated = components["schemas"]["ApplicationCreated"];
export type ApplicationWorkspace = components["schemas"]["ApplicationWorkspace"];
export type AnalysisRequest = components["schemas"]["AnalysisRequest"];
export type DocumentSummary = components["schemas"]["DocumentSummary"];
export type DocumentVersion = components["schemas"]["DocumentVersion"];
export type DocumentList = components["schemas"]["DocumentList"];
export type GenerateDocumentsRequest = components["schemas"]["GenerateDocumentsRequest"];
export type DocumentRevisionRequest = components["schemas"]["DocumentRevisionRequest"];
export type FindingsReport = components["schemas"]["FindingsReport"];
export type ApprovalRecord = components["schemas"]["ApprovalRecord"];
export type ApprovalRequest = components["schemas"]["ApprovalRequest"];

let csrfToken: string | null = null;

export type ApiErrorDetail = { field?: string; code?: string; message?: string };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: ApiErrorDetail[] = [],
  ) {
    super(message);
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: ApiErrorDetail[] };
    };
    return new ApiError(
      response.status,
      body.error?.code ?? "internal_error",
      body.error?.message ?? "Permintaan gagal.",
      body.error?.details ?? [],
    );
  } catch {
    return new ApiError(response.status, "internal_error", "Permintaan gagal.");
  }
}

export async function ensureSession(): Promise<string> {
  if (csrfToken) {
    return csrfToken;
  }
  const response = await fetch("/api/session", { credentials: "same-origin" });
  if (!response.ok) {
    throw await parseError(response);
  }
  const session = (await response.json()) as Session;
  csrfToken = session.csrf_token;
  return csrfToken;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export async function apiSend<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const token = await ensureSession();
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": token,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const token = await ensureSession();
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": token },
    body: form,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export function getOverview(): Promise<Overview> {
  return apiGet<Overview>("/api/overview");
}

export function getMasterCv(): Promise<MasterCv> {
  return apiGet<MasterCv>("/api/setup/master-cv");
}

export function uploadMasterCv(file: File): Promise<MasterCvUploadResult> {
  return apiUpload<MasterCvUploadResult>("/api/setup/master-cv", file);
}

export function startExtraction(): Promise<TaskCreated> {
  return apiSend<TaskCreated>("POST", "/api/setup/master-cv/extractions");
}

export function getTask(taskId: string): Promise<Task> {
  return apiGet<Task>(`/api/tasks/${taskId}`);
}

export function listProfiles(): Promise<ProfileList> {
  return apiGet<ProfileList>("/api/setup/profiles");
}

export function getProfileVersion(profileVersionId: string): Promise<ProfileVersion> {
  return apiGet<ProfileVersion>(`/api/setup/profiles/${profileVersionId}`);
}

export function correctProfile(
  profileVersionId: string,
  expectedVersion: number,
  corrections: { path: string; value: unknown; reason?: string }[],
): Promise<ProfileVersion> {
  return apiSend<ProfileVersion>("PATCH", `/api/setup/profiles/${profileVersionId}`, {
    expected_version: expectedVersion,
    corrections,
  });
}

export function confirmProfile(
  profileVersionId: string,
  note?: string,
): Promise<ProfileSummary> {
  return apiSend<ProfileSummary>(
    "POST",
    `/api/setup/profiles/${profileVersionId}/confirm`,
    { note: note ?? null },
  );
}

export function rollbackProfile(
  targetProfileVersionId: string,
  reason: string,
): Promise<ProfileSummary> {
  return apiSend<ProfileSummary>("POST", "/api/setup/profile/rollback", {
    target_profile_version_id: targetProfileVersionId,
    reason,
  });
}

export function getConsent(): Promise<ConsentStatus> {
  return apiGet<ConsentStatus>("/api/settings/consent");
}

export function grantConsent(scope: {
  provider_id: string;
  data_classes: string[];
}): Promise<ConsentRecord> {
  return apiSend<ConsentRecord>("POST", "/api/settings/consent", {
    consent_type: "cloud_data_processing",
    scope,
    accepted: true,
  });
}

export function revokeConsent(consentId: string): Promise<ConsentRecord> {
  return apiSend<ConsentRecord>("DELETE", `/api/settings/consent/${consentId}`);
}

export function getBrowserImportToken(): Promise<{ token: string; header: string }> {
  return apiGet<{ token: string; header: string }>("/api/settings/browser-import-token");
}

export type ProviderSettingsView = {
  provider_id: string;
  configured: boolean;
  base_url: string | null;
  roles: Record<string, { model: string | null }>;
  key_source: "keyring" | "env" | "missing";
  key_writable: boolean;
  providers: string[];
};

export type ProviderTestResult = {
  ok: boolean;
  latency_ms: number;
  model_count: number;
  models: string[];
  key_source: string;
};

export function getProviderSettings(): Promise<ProviderSettingsView> {
  return apiGet<ProviderSettingsView>("/api/settings/provider");
}

export function updateProviderSettings(body: {
  provider_id: string;
  base_url: string;
  roles: Record<string, string>;
  api_key?: string;
}): Promise<ProviderSettingsView> {
  return apiSend<ProviderSettingsView>("PUT", "/api/settings/provider", body);
}

export function testProviderConnection(): Promise<ProviderTestResult> {
  return apiSend<ProviderTestResult>("POST", "/api/settings/provider/test", {});
}

export function listSources(): Promise<SourceList> {
  return apiGet<SourceList>("/api/settings/sources?limit=200");
}

export function createSource(body: SourceCreateRequest): Promise<SourceRegistryEntry> {
  return apiSend<SourceRegistryEntry>("POST", "/api/settings/sources", body);
}

export function updateSource(
  sourceId: string,
  body: SourceUpdateRequest,
): Promise<SourceRegistryEntry> {
  return apiSend<SourceRegistryEntry>("PATCH", `/api/settings/sources/${sourceId}`, body);
}

export function listDiscoveryRuns(): Promise<DiscoveryRunList> {
  return apiGet<DiscoveryRunList>("/api/discovery/runs?limit=10");
}

export function startDiscoveryRun(): Promise<TaskCreated> {
  return apiSend<TaskCreated>("POST", "/api/discovery/runs", {});
}

export function retryTask(
  taskId: string,
  scope: "all" | "failed_sources" = "failed_sources",
): Promise<TaskCreated> {
  return apiSend<TaskCreated>("POST", `/api/tasks/${taskId}/retry`, { scope });
}

export type MatchQuery = {
  limit?: number;
  cursor?: string | null;
  eligibility?: "all" | "eligible" | "needs_review" | "ineligible";
  q?: string;
  tier?: string;
  source_id?: string;
  market?: string;
  work_mode?: string;
  min_fit_score?: number;
  sort?: "ranking" | "fit_score_desc" | "posted_at_desc" | "priority_tier";
};

export function listMatches(query: MatchQuery = {}): Promise<MatchList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const suffix = params.toString();
  return apiGet<MatchList>(`/api/matches${suffix ? `?${suffix}` : ""}`);
}

export function getMatch(jobId: string): Promise<MatchDetail> {
  return apiGet<MatchDetail>(`/api/matches/${jobId}`);
}

export function overrideMatchTier(
  jobId: string,
  body: TierOverrideRequest,
): Promise<MatchItem> {
  return apiSend<MatchItem>("PATCH", `/api/matches/${jobId}/tier`, body);
}

export function reviewEligibility(
  jobId: string,
  body: { status: "eligible" | "ineligible" | null; reason?: string | null },
): Promise<MatchDetail> {
  return apiSend<MatchDetail>("PATCH", `/api/matches/${jobId}/eligibility`, body);
}

export function listApplications(
  options: { includeCancelled?: boolean } = {},
): Promise<ApplicationList> {
  const suffix = options.includeCancelled ? "&include_cancelled=true" : "";
  return apiGet<ApplicationList>(`/api/applications?limit=200${suffix}`);
}

export function cancelApplication(
  applicationId: string,
  reason: string | null,
): Promise<{ application_id: string; cancelled_at: string | null }> {
  return apiSend("POST", `/api/applications/${applicationId}/cancel`, { reason });
}

export function createApplication(jobId: string): Promise<ApplicationCreated> {
  return apiSend<ApplicationCreated>("POST", "/api/applications", { job_id: jobId });
}

export function getApplication(applicationId: string): Promise<ApplicationWorkspace> {
  return apiGet<ApplicationWorkspace>(`/api/applications/${applicationId}`);
}

export function rerunApplicationAnalysis(
  applicationId: string,
  body: AnalysisRequest,
): Promise<TaskCreated> {
  return apiSend<TaskCreated>("POST", `/api/applications/${applicationId}/analysis`, body);
}

export function listDocuments(applicationId: string): Promise<DocumentList> {
  return apiGet<DocumentList>(`/api/applications/${applicationId}/documents?limit=200`);
}

export function generateDocuments(
  applicationId: string,
  body: GenerateDocumentsRequest,
): Promise<TaskCreated> {
  return apiSend<TaskCreated>("POST", `/api/applications/${applicationId}/documents`, body);
}

export function getDocumentVersion(
  applicationId: string,
  documentVersionId: string,
): Promise<DocumentVersion> {
  return apiGet<DocumentVersion>(
    `/api/applications/${applicationId}/documents/${documentVersionId}`,
  );
}

export function createDocumentRevision(
  applicationId: string,
  documentVersionId: string,
  body: DocumentRevisionRequest,
): Promise<DocumentVersion> {
  return apiSend<DocumentVersion>(
    "POST",
    `/api/applications/${applicationId}/documents/${documentVersionId}/revisions`,
    body,
  );
}

export function regenerateDocument(
  applicationId: string,
  documentVersionId: string,
  baseContentHash: string,
): Promise<TaskCreated> {
  return apiSend<TaskCreated>(
    "POST",
    `/api/applications/${applicationId}/documents/${documentVersionId}/regenerate`,
    { base_content_hash: baseContentHash, reason: "user_requested" },
  );
}

export function requestDocumentRevision(
  applicationId: string,
  documentVersionId: string,
  body: { base_content_hash: string; reason: string; finding_ids: string[]; note?: string },
): Promise<TaskCreated> {
  return apiSend<TaskCreated>(
    "POST",
    `/api/applications/${applicationId}/documents/${documentVersionId}/revision-request`,
    body,
  );
}

export function runDocumentReview(
  applicationId: string,
  documentVersionId: string,
): Promise<TaskCreated> {
  return apiSend<TaskCreated>(
    "POST",
    `/api/applications/${applicationId}/documents/${documentVersionId}/review`,
  );
}

export function getDocumentFindings(
  applicationId: string,
  documentVersionId: string,
): Promise<FindingsReport> {
  return apiGet<FindingsReport>(
    `/api/applications/${applicationId}/documents/${documentVersionId}/findings`,
  );
}

export function approveDocumentVersion(
  applicationId: string,
  documentVersionId: string,
  body: ApprovalRequest,
): Promise<ApprovalRecord> {
  return apiSend<ApprovalRecord>(
    "POST",
    `/api/applications/${applicationId}/documents/${documentVersionId}/approval`,
    body,
  );
}

export type ExportRecord = components["schemas"]["ExportRecord"];
export type ExportList = components["schemas"]["ExportList"];
export type ExportRequest = components["schemas"]["ExportRequest"];

export function createApplicationFromUrl(
  url: string,
  text?: string,
): Promise<ApplicationCreated> {
  return apiSend<ApplicationCreated>("POST", "/api/applications", {
    url,
    ...(text ? { text } : {}),
  });
}

export function listExports(applicationId: string): Promise<ExportList> {
  return apiGet<ExportList>(`/api/applications/${applicationId}/exports?limit=200`);
}

export function createExport(
  applicationId: string,
  body: ExportRequest,
): Promise<TaskCreated> {
  return apiSend<TaskCreated>("POST", `/api/applications/${applicationId}/exports`, body);
}

export function documentPdfUrl(applicationId: string, documentVersionId: string): string {
  return `/api/applications/${applicationId}/documents/${documentVersionId}/pdf`;
}

export function exportDownloadUrl(applicationId: string, exportId: string): string {
  return `/api/applications/${applicationId}/exports/${exportId}/download`;
}
