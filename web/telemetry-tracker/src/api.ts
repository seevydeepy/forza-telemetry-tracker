import type {
  AppAboutPayload,
  AppUpdateCheckResponse,
  AppUpdateInstallResponse,
  AppUpdateTokenResponse,
  CaptureMode,
  CaptureStatus,
  DeltaResponse,
  DiagnosticsPayload,
  GhostResponse,
  LapMarkersResponse,
  LapSamplesResponse,
  LapSummary,
  LapSummaryResponse,
  RawPointResponse,
  RawTelemetryImportJob,
  RawTelemetryImportJobResponse,
  RawTelemetryImportJobsResponse,
  RawTelemetryImportResponse,
  RecentLivePayload,
  ReferenceResponse,
  ReferenceScope,
  SessionDeleteResponse,
  SessionFilters,
  SessionPageResponse,
  SessionResponse,
  SessionSummary,
  StatsSummary,
  StatusPayload,
  TelemetryDeleteResponse,
  TelemetryExportDefaults,
  TelemetryExportJob,
  TelemetryExportJobRequest,
  TelemetryExportJobResponse,
  TelemetryExportJobsResponse,
  TrackAsset,
  TrackAssetCreateInput,
  TrackAssetDeleteResponse,
  TrackAssetResponse,
  TrackAssetTransform,
  TrackAssetsResponse,
  TrackProfile,
  TrackMatchResponse,
  TrackProfileAssignmentResponse,
  TrackProfileAssignInput,
  TrackProfileCreateInput,
  TrackProfileMergeInput,
  TrackProfileMergeResponse,
  TrackProfileResponse,
  TrackProfileUpdateInput,
  VisualiserSettings,
  VisualiserSettingsUpdate,
  WorldMapSeason,
  WorldMapSettings,
  WorldMapStatus
} from './types';

async function expectJson<T>(response: Response, message: string): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown };
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        detail = payload.detail.trim();
      } else if (typeof payload.message === 'string' && payload.message.trim()) {
        detail = payload.message.trim();
      }
    } catch {
      // Fall through to the status-only error below.
    }
    throw new Error(detail ? `${message}: ${detail}` : `${message}: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchStatus(): Promise<StatusPayload> {
  const response = await fetch('/api/status');
  return expectJson<StatusPayload>(response, 'Status request failed');
}

export async function fetchCaptureStatus(): Promise<CaptureStatus> {
  const response = await fetch('/api/capture');
  return expectJson<CaptureStatus>(response, 'Capture status request failed');
}

export async function fetchDiagnostics(): Promise<DiagnosticsPayload> {
  const response = await fetch('/api/diagnostics');
  return expectJson<DiagnosticsPayload>(response, 'Diagnostics request failed');
}

export async function fetchAppAbout(): Promise<AppAboutPayload> {
  const response = await fetch('/api/app/about');
  return expectJson<AppAboutPayload>(response, 'About request failed');
}

export async function checkForUpdates(force = false): Promise<AppUpdateCheckResponse> {
  const response = await fetch('/api/app/update/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force })
  });
  return expectJson<AppUpdateCheckResponse>(response, 'Update check request failed');
}

export async function installAppUpdate(version?: string | null): Promise<AppUpdateInstallResponse> {
  const response = await fetch('/api/app/update/install', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Forza-App-Action': '1'
    },
    body: JSON.stringify(version ? { version } : {})
  });
  return expectJson<AppUpdateInstallResponse>(response, 'Update install request failed');
}

export async function saveAppUpdateToken(token: string): Promise<AppUpdateTokenResponse> {
  const response = await fetch('/api/app/update/token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Forza-App-Action': '1'
    },
    body: JSON.stringify({ token })
  });
  return expectJson<AppUpdateTokenResponse>(response, 'Update token save request failed');
}

export async function clearAppUpdateToken(): Promise<AppUpdateTokenResponse> {
  const response = await fetch('/api/app/update/token', {
    method: 'DELETE',
    headers: { 'X-Forza-App-Action': '1' }
  });
  return expectJson<AppUpdateTokenResponse>(response, 'Update token clear request failed');
}

export async function restartListener(): Promise<StatusPayload['listener']> {
  const response = await fetch('/api/listener/restart', { method: 'POST' });
  return expectJson<StatusPayload['listener']>(response, 'Listener restart request failed');
}

export async function deleteAllTelemetry(): Promise<TelemetryDeleteResponse> {
  const response = await fetch('/api/telemetry/delete-all', { method: 'DELETE' });
  return expectJson<TelemetryDeleteResponse>(response, 'Delete all telemetry request failed');
}

export async function updateVisualiserSettings(input: VisualiserSettingsUpdate): Promise<VisualiserSettings> {
  const response = await fetch('/api/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<VisualiserSettings>(response, 'Settings update request failed');
}

export async function fetchWorldMapStatus(): Promise<WorldMapStatus> {
  const response = await fetch('/api/map/status');
  return expectJson<WorldMapStatus>(response, 'World map status request failed');
}

export async function updateWorldMapSettings(input: Partial<WorldMapSettings>): Promise<WorldMapStatus> {
  const response = await fetch('/api/map/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<WorldMapStatus>(response, 'World map settings request failed');
}

export async function buildWorldMapCache(season?: WorldMapSeason): Promise<WorldMapStatus> {
  const response = await fetch('/api/map/cache/build', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(season ? { season } : {})
  });
  return expectJson<WorldMapStatus>(response, 'World map cache build request failed');
}

export async function setCaptureMode(mode: CaptureMode): Promise<CaptureStatus> {
  const response = await fetch('/api/capture/mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  return expectJson<CaptureStatus>(response, 'Capture mode request failed');
}

export async function startCapture(): Promise<CaptureStatus> {
  const response = await fetch('/api/capture/start', { method: 'POST' });
  return expectJson<CaptureStatus>(response, 'Capture start request failed');
}

export async function stopCapture(): Promise<CaptureStatus> {
  const response = await fetch('/api/capture/stop', { method: 'POST' });
  return expectJson<CaptureStatus>(response, 'Capture stop request failed');
}

export async function fetchRecentLiveSamples(limit = 200): Promise<RecentLivePayload> {
  const response = await fetch(`/api/live/recent?limit=${limit}`);
  return expectJson<RecentLivePayload>(response, 'Recent live samples request failed');
}

export async function importRawTelemetryFile(input: { file: File; label?: string }): Promise<RawTelemetryImportResponse> {
  const body = new FormData();
  body.append('file', input.file);
  const label = input.label?.trim();
  if (label) {
    body.append('label', label);
  }
  const response = await fetch('/api/replay/upload', {
    method: 'POST',
    body
  });
  return expectJson<RawTelemetryImportResponse>(response, 'Raw telemetry import request failed');
}

export async function createRawTelemetryImportJob(input: {
  files: File[];
  label?: string;
  sourceType?: 'file' | 'files' | 'folder';
}): Promise<RawTelemetryImportJob> {
  const body = new FormData();
  for (const file of input.files) {
    const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath?.trim();
    body.append('files', file, relativePath || file.name);
  }
  const label = input.label?.trim();
  if (label) {
    body.append('label', label);
  }
  if (input.sourceType) {
    body.append('source_type', input.sourceType);
  }
  const response = await fetch('/api/replay/import-jobs/upload', {
    method: 'POST',
    body
  });
  const payload = await expectJson<RawTelemetryImportJobResponse>(response, 'Raw telemetry import job request failed');
  return payload.job;
}

export async function fetchRawTelemetryImportJobs(): Promise<RawTelemetryImportJob[]> {
  const response = await fetch('/api/replay/import-jobs');
  const payload = await expectJson<RawTelemetryImportJobsResponse>(response, 'Raw telemetry import jobs request failed');
  return payload.jobs;
}

export async function cancelRawTelemetryImportJob(jobId: string): Promise<RawTelemetryImportJob> {
  const response = await fetch(`/api/replay/import-jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
  const payload = await expectJson<RawTelemetryImportJobResponse>(response, 'Raw telemetry import job cancel request failed');
  return payload.job;
}

export async function fetchTelemetryExportDefaults(): Promise<TelemetryExportDefaults> {
  const response = await fetch('/api/telemetry/export-defaults');
  return expectJson<TelemetryExportDefaults>(response, 'Telemetry export defaults request failed');
}

export async function createTelemetryExportJob(input: TelemetryExportJobRequest): Promise<TelemetryExportJob> {
  const response = await fetch('/api/telemetry/export-jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Forza-Telemetry-Export': '1'
    },
    body: JSON.stringify(input)
  });
  const payload = await expectJson<TelemetryExportJobResponse>(response, 'Telemetry export job request failed');
  return payload.job;
}

export async function fetchTelemetryExportJobs(): Promise<TelemetryExportJob[]> {
  const response = await fetch('/api/telemetry/export-jobs');
  const payload = await expectJson<TelemetryExportJobsResponse>(response, 'Telemetry export jobs request failed');
  return payload.jobs;
}

export async function cancelTelemetryExportJob(jobId: string): Promise<TelemetryExportJob> {
  const response = await fetch(`/api/telemetry/export-jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
  const payload = await expectJson<TelemetryExportJobResponse>(response, 'Telemetry export job cancel request failed');
  return payload.job;
}

export async function fetchLaps(): Promise<LapSummary[]> {
  const response = await fetch('/api/laps');
  const payload = await expectJson<{ laps: LapSummary[] }>(response, 'Laps request failed');
  return payload.laps;
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  return (await fetchSessionPage()).sessions;
}

export async function fetchStatsSummary(): Promise<StatsSummary> {
  const response = await fetch('/api/stats');
  const payload = await expectJson<{ stats: StatsSummary }>(response, 'Stats request failed');
  return payload.stats;
}

function sessionFilterParams(filters: SessionFilters = {}): URLSearchParams {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 100));
  if (filters.name) params.set('name', filters.name);
  if (filters.createdFrom !== undefined) params.set('created_from', String(filters.createdFrom));
  if (filters.createdTo !== undefined) params.set('created_to', String(filters.createdTo));
  if (filters.lastActiveFrom !== undefined) params.set('last_active_from', String(filters.lastActiveFrom));
  if (filters.lastActiveTo !== undefined) params.set('last_active_to', String(filters.lastActiveTo));
  if (filters.lapCountMin !== undefined) params.set('lap_count_min', String(filters.lapCountMin));
  if (filters.lapCountMax !== undefined) params.set('lap_count_max', String(filters.lapCountMax));
  if (filters.track) params.set('track', filters.track);
  if (filters.car) params.set('car', filters.car);
  return params;
}

export async function fetchSessionPage(filters: SessionFilters = {}): Promise<SessionPageResponse> {
  const response = await fetch(`/api/sessions?${sessionFilterParams(filters).toString()}`);
  return expectJson<SessionPageResponse>(response, 'Sessions request failed');
}

export async function fetchActiveSession(): Promise<SessionSummary | null> {
  const response = await fetch('/api/sessions/active');
  const payload = await expectJson<SessionResponse>(response, 'Active session request failed');
  return payload.session;
}

export async function startSession(label?: string): Promise<SessionSummary> {
  const init: RequestInit = { method: 'POST' };
  if (label !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify({ label });
  }
  const response = await fetch('/api/sessions/start', init);
  const payload = await expectJson<SessionResponse>(response, 'Session start request failed');
  if (!payload.session) throw new Error('Session start request did not return a session');
  return payload.session;
}

export async function activateSession(sessionId: string): Promise<SessionSummary> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/activate`, { method: 'POST' });
  const payload = await expectJson<SessionResponse>(response, 'Session activation request failed');
  if (!payload.session) throw new Error('Session activation request did not return a session');
  return payload.session;
}

export async function endSession(sessionId: string): Promise<SessionSummary> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/end`, { method: 'POST' });
  const payload = await expectJson<SessionResponse>(response, 'Session end request failed');
  if (!payload.session) throw new Error('Session end request did not return a session');
  return payload.session;
}

export async function renameSession(sessionId: string, label: string): Promise<SessionSummary> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label })
  });
  const payload = await expectJson<SessionResponse>(response, 'Session rename request failed');
  if (!payload.session) throw new Error('Session rename request did not return a session');
  return payload.session;
}

export async function deleteSession(sessionId: string): Promise<SessionDeleteResponse> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  return expectJson<SessionDeleteResponse>(response, 'Session delete request failed');
}

export async function fetchSessionLaps(sessionId: string): Promise<LapSummary[]> {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/laps`);
  const payload = await expectJson<{ session_id: string; laps: LapSummary[] }>(response, 'Session laps request failed');
  return payload.laps;
}

export async function fetchTrackProfiles(): Promise<TrackProfile[]> {
  const response = await fetch('/api/tracks/profiles');
  const payload = await expectJson<{ profiles: TrackProfile[] }>(response, 'Track profiles request failed');
  return payload.profiles;
}

export async function fetchLapTrackMatch(lapId: string): Promise<TrackMatchResponse> {
  const response = await fetch(`/api/laps/${encodeURIComponent(lapId)}/track-match`);
  return expectJson<TrackMatchResponse>(response, 'Track match request failed');
}

export async function matchLapTrack(lapId: string): Promise<TrackMatchResponse> {
  const response = await fetch(`/api/laps/${encodeURIComponent(lapId)}/track-match`, { method: 'POST' });
  return expectJson<TrackMatchResponse>(response, 'Track match request failed');
}

export async function createTrackProfile(input: TrackProfileCreateInput): Promise<TrackProfileResponse> {
  const response = await fetch('/api/tracks/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<TrackProfileResponse>(response, 'Track profile create request failed');
}

export async function updateTrackProfile(profileId: string, input: TrackProfileUpdateInput): Promise<TrackProfileResponse> {
  const response = await fetch(`/api/tracks/profiles/${encodeURIComponent(profileId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<TrackProfileResponse>(response, 'Track profile update request failed');
}

export async function assignTrackProfile(profileId: string, input: TrackProfileAssignInput): Promise<TrackProfileAssignmentResponse> {
  const response = await fetch(`/api/tracks/profiles/${encodeURIComponent(profileId)}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<TrackProfileAssignmentResponse>(response, 'Track profile assign request failed');
}

export async function mergeTrackProfiles(input: TrackProfileMergeInput): Promise<TrackProfileMergeResponse> {
  const response = await fetch('/api/tracks/profiles/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<TrackProfileMergeResponse>(response, 'Track profile merge request failed');
}

export async function fetchTrackAssets(profileId: string): Promise<TrackAsset[]> {
  const response = await fetch(`/api/tracks/profiles/${encodeURIComponent(profileId)}/assets`);
  const payload = await expectJson<TrackAssetsResponse>(response, 'Track assets request failed');
  return payload.assets;
}

export async function createTrackAsset(profileId: string, input: TrackAssetCreateInput): Promise<TrackAssetResponse> {
  const response = await fetch(`/api/tracks/profiles/${encodeURIComponent(profileId)}/assets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  return expectJson<TrackAssetResponse>(response, 'Track asset create request failed');
}

export async function updateTrackAssetTransform(assetId: string, transform: TrackAssetTransform): Promise<TrackAssetResponse> {
  const response = await fetch(`/api/tracks/assets/${encodeURIComponent(assetId)}/transform`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(transform)
  });
  return expectJson<TrackAssetResponse>(response, 'Track asset transform request failed');
}

export async function deleteTrackAsset(assetId: string): Promise<TrackAssetDeleteResponse> {
  const response = await fetch(`/api/tracks/assets/${encodeURIComponent(assetId)}`, { method: 'DELETE' });
  return expectJson<TrackAssetDeleteResponse>(response, 'Track asset delete request failed');
}

export async function fetchLapSamples(lapId: string) {
  const response = await fetch(`/api/laps/${lapId}/samples`);
  const payload = await expectJson<LapSamplesResponse>(response, 'Lap samples request failed');
  return payload.samples;
}

export async function deleteLap(lapId: string): Promise<{ deleted: boolean; lap_id: string; session_id: string }> {
  const response = await fetch(`/api/laps/${encodeURIComponent(lapId)}`, { method: 'DELETE' });
  return expectJson<{ deleted: boolean; lap_id: string; session_id: string }>(response, 'Lap delete request failed');
}

export async function fetchLapSummary(lapId: string, startSequence?: number, endSequence?: number) {
  const params = new URLSearchParams();
  if (startSequence !== undefined && endSequence !== undefined) {
    params.set('start_sequence', String(startSequence));
    params.set('end_sequence', String(endSequence));
  }
  const query = params.size > 0 ? `?${params.toString()}` : '';
  const response = await fetch(`/api/laps/${lapId}/summary${query}`);
  return expectJson<LapSummaryResponse>(response, 'Lap summary request failed');
}

export async function fetchLapMarkers(lapId: string) {
  const response = await fetch(`/api/laps/${lapId}/markers`);
  return expectJson<LapMarkersResponse>(response, 'Lap markers request failed');
}

function scopedLapUrl(lapId: string, path: 'reference' | 'ghost' | 'delta', scope: ReferenceScope, startSequence?: number, endSequence?: number) {
  const params = new URLSearchParams({ scope });
  if (startSequence !== undefined && endSequence !== undefined) {
    params.set('start_sequence', String(startSequence));
    params.set('end_sequence', String(endSequence));
  }
  return `/api/laps/${encodeURIComponent(lapId)}/${path}?${params.toString()}`;
}

export async function fetchReference(lapId: string, scope: ReferenceScope = 'track_car') {
  const response = await fetch(scopedLapUrl(lapId, 'reference', scope));
  return expectJson<ReferenceResponse>(response, 'Reference request failed');
}

export async function fetchGhost(lapId: string, scope: ReferenceScope = 'track_car') {
  const response = await fetch(scopedLapUrl(lapId, 'ghost', scope));
  return expectJson<GhostResponse>(response, 'Ghost request failed');
}

export async function fetchDelta(lapId: string, scope: ReferenceScope = 'track_car', startSequence?: number, endSequence?: number) {
  const response = await fetch(scopedLapUrl(lapId, 'delta', scope, startSequence, endSequence));
  return expectJson<DeltaResponse>(response, 'Delta request failed');
}

export async function fetchRawPoint(sessionId: string, sequence: number) {
  const response = await fetch(`/api/sessions/${sessionId}/points/${sequence}`);
  return expectJson<RawPointResponse>(response, 'Raw point request failed');
}
