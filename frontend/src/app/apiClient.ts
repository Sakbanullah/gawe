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

let csrfToken: string | null = null;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string };
    };
    return new ApiError(
      response.status,
      body.error?.code ?? "internal_error",
      body.error?.message ?? "Permintaan gagal.",
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
