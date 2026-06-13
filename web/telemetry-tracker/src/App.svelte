<script lang="ts">
  import { onMount, tick } from 'svelte';
  import {
    activateSession,
    assignTrackProfile,
    cancelRawTelemetryImportJob,
    cancelTelemetryExportJob,
    createTelemetryExportJob,
    createRawTelemetryImportJob,
    deleteAllTelemetry,
    deleteLap,
    deleteSession,
    fetchActiveSession,
    fetchCaptureStatus,
    fetchDelta,
    fetchDiagnostics,
    fetchGhost,
    fetchLapMarkers,
    fetchLapSamples,
    fetchLapSummary,
    fetchReference,
    fetchRawTelemetryImportJobs,
    fetchRecentLiveSamples,
    fetchSessionLaps,
    fetchSessionPage,
    fetchStatsSummary,
    fetchStatus,
    fetchTelemetryExportDefaults,
    fetchTelemetryExportJobs,
    fetchTrackAssets,
    fetchTrackProfiles,
    fetchWorldMapStatus,
    matchLapTrack,
    renameSession,
    restartListener,
    setCaptureMode,
    startCapture,
    startSession,
    stopCapture,
    updateWorldMapSettings
  } from './api';
  import AboutModal from './AboutModal.svelte';
  import CanvasModeToggle from './CanvasModeToggle.svelte';
  import DashboardPlaybackBar from './DashboardPlaybackBar.svelte';
  import DashboardWidgetVisibilityPopover from './DashboardWidgetVisibilityPopover.svelte';
  import DiagnosticsPanel from './DiagnosticsPanel.svelte';
  import FloatingCaptureControls from './FloatingCaptureControls.svelte';
  import FloatingCarInfo from './FloatingCarInfo.svelte';
  import FloatingSectionSummary from './FloatingSectionSummary.svelte';
  import IconButton from './IconButton.svelte';
  import ExportTelemetryModal from './ExportTelemetryModal.svelte';
  import ImportTelemetryModal from './ImportTelemetryModal.svelte';
  import { actionForKey } from './KeyboardShortcuts';
  import LiveFollowButton from './LiveFollowButton.svelte';
  import OverlayToolbar from './OverlayToolbar.svelte';
  import IssuePopover from './IssuePopover.svelte';
  import RightHistoryDrawer from './RightHistoryDrawer.svelte';
  import ReviewTimeline from './ReviewTimeline.svelte';
  import SettingsModal from './SettingsModal.svelte';
  import SessionBrowserModal from './SessionBrowserModal.svelte';
  import ShortcutHelp from './ShortcutHelp.svelte';
  import StatsModal from './StatsModal.svelte';
  import SlideOutMenu, { type MenuAction } from './SlideOutMenu.svelte';
  import StatusStrip from './StatusStrip.svelte';
  import TelemetryCanvas from './TelemetryCanvas.svelte';
  import TelemetryDashboard from './TelemetryDashboard.svelte';
  import ToastStack from './ToastStack.svelte';
  import WorldMapSetupPanel from './WorldMapSetupPanel.svelte';
  import {
    buildPlaybackTimeline,
    nextPlaybackTime,
    playbackPointInTimelineAtTime,
    type DashboardPlaybackPoint,
    type DashboardPlaybackTimeline
  } from './dashboardPlayback';
  import { defaultDashboardWidgetVisibility } from './dashboardWidgets';
  import TrackAssignmentPicker from './TrackAssignmentPicker.svelte';
  import type {
    AnalysisSummary,
    CanvasMode,
    CaptureMode,
    CarInfo,
    CaptureStatus,
    DeltaSummary,
    DeltaResponse,
    DashboardPlaybackSource,
    DashboardWidgetId,
    DiagnosticsPayload,
    GhostResponse,
    GhostSample,
    IssueMarker,
    LapMarkersResponse,
    LapSummary,
    LapSummaryResponse,
    ListenerStatus,
    LiveSample,
    OverlayId,
    RawTelemetryImportJob,
    ReferenceLap,
    ReferenceResponse,
    ReferenceScope,
    SequenceRange,
    SessionFilters,
    SessionPageResponse,
    SessionSummary,
    LapHistoryView,
    StatsSummary,
    StatusPayload,
    TelemetryExportDefaults,
    TelemetryExportJob,
    TelemetryExportKind,
    TrackAsset,
    TrackMatchCandidate,
    TrackMatchResponse,
    TrackProfile,
    ToastMessage,
    UnitSystem,
    WorldMapTileSet,
    VisualiserSettings,
    WorldMapStatus
  } from './types';

  const RECENT_LIVE_SAMPLE_LIMIT = 200;
  const LIVE_SAMPLE_HISTORY_LIMIT = 2_000;
  const RECONNECT_DELAY_MS = 500;
  const IMPORT_JOB_POLL_DELAY_MS = 1000;
  const EXPORT_JOB_POLL_DELAY_MS = 1000;
  const SECTION_SUMMARY_DEBOUNCE_MS = 150;
  const FIT_TO_SCREEN_RESUME_DELAY_MS = 10_000;
  const MALFORMED_EVENT_TOAST_MESSAGE = 'Malformed telemetry event data received';
  const DEFAULT_OVERLAY: OverlayId = 'issues';
  const EMPTY_DASHBOARD_TIMELINE: DashboardPlaybackTimeline = {
    source: 'synthetic',
    durationMs: 0,
    points: []
  };
  const FALLBACK_LIVE_OVERLAY: OverlayId = 'speed';
  const ISSUES_UNAVAILABLE_DURING_RECORDING_MESSAGE = 'Issues overlay is only available for completed laps.';
  const VALID_OVERLAYS: OverlayId[] = ['issues', 'speed', 'inputs', 'grip', 'temperature', 'suspension', 'rpm'];
  const SUMMARY_FALLBACK_DRAG_LIMIT_PX = 600;
  const SUMMARY_VISIBLE_EDGE_PX = 80;
  const SUMMARY_HEADER_REACHABLE_PX = 56;
  const POPOVER_VISIBLE_EDGE_PX = 56;
  const POPOVER_HEADER_REACHABLE_PX = 56;
  const LIVE_TELEPORT_DISTANCE_METERS = 1000;
  const LEGACY_MENU_SAMPLE_EPSILON = 0.0001;
  const LAP_CONTEXT_CACHE_LIMIT = 8;

  type UtilityModal = 'settings' | 'import' | 'export' | 'session-browser' | 'stats' | 'about';
  type ZoomCommand = 'in' | 'out' | 'fit';
  type ComparisonPayloads = {
    referencePayload: ReferenceResponse;
    ghostPayload: GhostResponse;
    deltaPayload: DeltaResponse;
  };
  type LapContextCacheEntry = {
    summaryPayload: LapSummaryResponse;
    markersPayload: LapMarkersResponse;
    samples: LiveSample[];
    comparisons: Map<string, ComparisonPayloads>;
  };

  const defaultListener: ListenerStatus = {
    state: 'starting',
    udp_host: '127.0.0.1',
    udp_port: 5400,
    packets_received: 0,
    packets_recorded: 0,
    message: 'starting tracker'
  };

  const defaultSettings: StatusPayload['settings'] = {
    capture_mode: 'auto',
    udp_host: defaultListener.udp_host,
    udp_port: defaultListener.udp_port,
    preferred_overlay: DEFAULT_OVERLAY,
    unit_system: 'imperial'
  };

  const defaultCapture: CaptureStatus = {
    mode: 'auto',
    phase: 'idle',
    packet_receipt: {
      state: 'waiting',
      has_received_packets: false,
      packets_observed: 0,
      last_timestamp_ms: null,
      last_is_race_on: null,
      last_packet_type: 'unknown'
    },
    recording: {
      active: false,
      phase: 'idle',
      mode: 'auto',
      total_live_packets_recorded_excluding_prebuffer: 0
    },
    prebuffer: {
      capacity: 0,
      size: 0
    },
    auto_detection: {
      last_signals: {},
      last_reason: 'waiting_for_packet'
    }
  };

  let listener: ListenerStatus = defaultListener;
  let capture: CaptureStatus = defaultCapture;
  let latestStatus: StatusPayload = {
    listener: defaultListener,
    settings: defaultSettings,
    capture: { ...defaultCapture, listener: defaultListener, settings: defaultSettings }
  };
  let worldMapStatus: WorldMapStatus | null = null;
  let readyWorldMapTileSet: WorldMapTileSet | null = null;
  let activeWorldMapTileSet: WorldMapTileSet | null = null;
  let mapSetupPanelOpen = false;
  let worldMapStatusVersion = 0;
  let summaryUnitSystem: UnitSystem = 'imperial';
  let laps: LapSummary[] = [];
  let sessions: SessionSummary[] = [];
  let activeSession: SessionSummary | null = null;
  let loadedSessionId: string | null = null;
  let sessionPage: SessionPageResponse = {
    sessions: [],
    page: 1,
    page_size: 100,
    total: 0,
    total_pages: 0
  };
  let sessionBrowserBusy = false;
  let sessionBrowserError: string | null = null;
  let statsSummary: StatsSummary | null = null;
  let statsLoading = false;
  let statsError: string | null = null;
  let sessionFilters: SessionFilters = { page: 1, pageSize: 100 };
  let trackProfiles: TrackProfile[] = [];
  let liveSamples: LiveSample[] = [];
  let liveSampleVersion = 0;
  let lapSamples: LiveSample[] = [];
  let markers: IssueMarker[] = [];
  let selectedOverlay: OverlayId = DEFAULT_OVERLAY;
  let toasts: ToastMessage[] = [];
  let nextToastId = 1;
  let eventSource: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof window.setTimeout> | null = null;
  let summaryDebounceTimer: ReturnType<typeof window.setTimeout> | null = null;
  let importJobPollTimer: ReturnType<typeof window.setTimeout> | null = null;
  let exportJobPollTimer: ReturnType<typeof window.setTimeout> | null = null;
  let disconnectedToastId: number | null = null;
  let disposed = false;

  $: summaryUnitSystem = normaliseUnitSystem(latestStatus.settings?.unit_system ?? capture.settings?.unit_system);
  $: readyWorldMapTileSet = worldMapStatus?.tile_set?.status === 'ready' ? worldMapStatus.tile_set : null;
  $: hasReadyWorldMapCache = readyWorldMapTileSet !== null;
  $: mapOverlayEnabled = Boolean(worldMapStatus?.settings.world_map_enabled && hasReadyWorldMapCache);
  $: activeWorldMapTileSet = mapOverlayEnabled ? readyWorldMapTileSet : null;
  $: mapToggleLabel = hasReadyWorldMapCache ? (mapOverlayEnabled ? 'Hide map overlay' : 'Show map overlay') : 'Set up map overlay';
  $: mapToggleTitle = hasReadyWorldMapCache
    ? mapOverlayEnabled
      ? 'Hide FH6 world map tile overlay'
      : 'Show FH6 world map tile overlay'
    : 'Set up the local FH6 world map cache';
  let captureBusy = false;
  let mapToggleBusy = false;
  let malformedEventToastShown = false;
  let overlayTouchedByUser = false;
  let liveSessionId: string | null = null;
  let selectedLapId: string | null = null;
  let issuesUnavailable = false;
  let disabledOverlays: OverlayId[] = [];
  let disabledOverlayReasons: Partial<Record<OverlayId, string>> = {};
  let selectedLap: LapSummary | null = null;
  let selectedSession: SessionSummary | null = null;
  let displayedSamples: LiveSample[] = [];
  let selectedLapSummary: AnalysisSummary | null = null;
  let selectedCarInfo: CarInfo | null = null;
  let liveCarInfo: CarInfo | null = null;
  let selectedDeltaSummary: DeltaSummary | null = null;
  let fullLapBounds: SequenceRange | null = null;
  let selectedRange: SequenceRange | null = null;
  let showReviewedLapBoundsOnCanvas = false;
  let referenceScope: ReferenceScope = 'track_car';
  let referenceContextKey: string | null = null;
  let referenceLap: ReferenceLap | null = null;
  let ghostSamples: GhostSample[] = [];
  let comparisonBusy = false;
  type CanvasLoadingState = { token: number; message: string; progress: number | null };
  type CanvasLoadingScope = { token: number; baseProgress: number; progressSpan: number };
  let canvasLoading: CanvasLoadingState | null = null;
  let canvasLoadingToken = 0;
  let canvasLoadingProgressPercent: number | null = null;
  type IssuePopoverItem = { marker: IssueMarker; sample: LiveSample | null; elapsedMs: number | null };
  type IssueInteractionDetail = { marker: IssueMarker; markers: IssueMarker[]; sample: LiveSample; canvasX?: number; canvasY?: number };

  let issuePopoverOpen = false;
  let issuePopoverItems: IssuePopoverItem[] = [];
  let issuePopoverPinned = false;
  let issuePopoverX = 16;
  let issuePopoverY = 16;
  let issuePopoverDragged = false;
  let lapContextRequestId = 0;
  let comparisonRequestId = 0;
  let referenceVersion = 0;
  let lapContextCache = new Map<string, LapContextCacheEntry>();
  let lapContextCacheGeneration = 0;
  let comparisonCacheGeneration = 0;
  let summaryRequestId = 0;
  let trackAssignmentLapId: string | null = null;
  let trackAssignmentCandidates: TrackMatchCandidate[] = [];
  let trackAssignmentBusy = false;
  let trackAssignmentError: string | null = null;
  let trackAssignmentRequestId = 0;
  let trackProfileBusy = false;
  let importBusy = false;
  let importJobs: RawTelemetryImportJob[] = [];
  let importJobsLoading = false;
  let importJobsRequestId = 0;
  let importJobStatuses: Record<string, string> = {};
  let cancellingImportJobIds: string[] = [];
  let exportBusy = false;
  let exportDefaults: TelemetryExportDefaults | null = null;
  let exportDefaultsLoading = false;
  let exportDefaultsRequestId = 0;
  let exportJobs: TelemetryExportJob[] = [];
  let exportJobsLoading = false;
  let exportJobsRequestId = 0;
  let exportJobStatuses: Record<string, string> = {};
  let cancellingExportJobIds: string[] = [];
  let trackAssets: TrackAsset[] = [];
  let selectedTrackAssetId: string | null = null;
  let trackAssetProfileRequestId = 0;
  let currentTrackAssetProfileId: string | null = null;
  let diagnosticsOpen = false;
  let diagnosticsLoading = false;
  let diagnosticsRestarting = false;
  let diagnosticsDeletingTelemetry = false;
  let diagnosticsPayload: DiagnosticsPayload | null = null;
  let diagnosticsRequestId = 0;
  let diagnosticsOpener: HTMLElement | null = null;
  let shortcutHelpOpen = false;
  let shortcutHelpOpener: HTMLElement | null = null;
  let liveFollowPaused = false;
  let menuExpanded = false;
  let activeUtilityModal: UtilityModal | null = null;
  let historyDrawerOpen = true;
  let historyView: LapHistoryView = 'laps';
  let deletingLapIds: string[] = [];
  let summaryCardVisible = true;
  let summaryCardX = 0;
  let summaryCardY = 0;
  let carCardVisible = true;
  let carCardExpanded = false;
  let carCardX = 0;
  let carCardY = 0;
  let lastStatusEvent = 'Dashboard starting';
  let floatingCaptureControlsElement: HTMLDivElement | null = null;
  let visualisationStageElement: HTMLElement | null = null;
  let canvasWrapElement: HTMLDivElement | null = null;
  let summaryCardElement: HTMLElement | null = null;
  let carCardElement: HTMLElement | null = null;
  let summaryToggleContainerElement: HTMLDivElement | null = null;
  let issuePopoverElement: HTMLElement | null = null;
  let zoomCommand: ZoomCommand | null = null;
  let zoomCommandId = 0;
  let fitToScreenEnabled = true;
  let fitToScreenSuspended = false;
  let fitToScreenActive = true;
  let fitToScreenButtonLabel = 'Disable fit to screen';
  let fitToScreenButtonTitle = 'Fit to screen is on';
  let fitToScreenResumeTimer: number | null = null;
  let displayedCarInfo: CarInfo | null = null;
  let carCardShown = false;
  let canvasMode: CanvasMode = 'route';
  let dashboardWidgetVisibility: Record<DashboardWidgetId, boolean> = defaultDashboardWidgetVisibility();
  let dashboardSource: DashboardPlaybackSource = 'live';
  let dashboardTimeline = EMPTY_DASHBOARD_TIMELINE;
  let dashboardPlaybackPoint: DashboardPlaybackPoint | null = null;
  let dashboardCurrentSample: LiveSample | null = null;
  let dashboardCurrentIndex = -1;
  let dashboardDurationMs = 0;
  let dashboardElapsedMs = 0;
  let dashboardTotalElapsedMs = 0;
  let dashboardProgress = 0;
  let dashboardPlaybackPlaying = false;
  let dashboardPlaybackTimeMs = 0;
  let dashboardPlaybackFrame: number | null = null;
  let dashboardPlaybackLastFrameMs: number | null = null;
  let previousDashboardLapId: string | null = null;

  const ACTIVE_LAP_STATUSES = new Set(['recording', 'active', 'in_progress']);

  function normaliseLapStatus(status: string | null | undefined): string {
    return String(status ?? '').trim().toLowerCase();
  }

  function hasCompletedLapTime(lap: LapSummary): boolean {
    return (
      typeof lap.lap_time_ms === 'number' &&
      Number.isFinite(lap.lap_time_ms) &&
      lap.lap_time_ms >= 0
    );
  }

  function isSelectableCompletedLap(lap: LapSummary): boolean {
    return (
      (lap.ended_at_ms !== null || hasCompletedLapTime(lap)) &&
      !ACTIVE_LAP_STATUSES.has(normaliseLapStatus(lap.status))
    );
  }

  function newestSelectableCompletedLapId(items: LapSummary[]): string | null {
    const completed = items.filter(isSelectableCompletedLap);
    if (completed.length === 0) return null;
    return [...completed]
      .sort((left, right) => {
        const leftTime = left.ended_at_ms ?? left.started_at_ms;
        const rightTime = right.ended_at_ms ?? right.started_at_ms;
        return rightTime - leftTime;
      })[0]?.id ?? null;
  }

  function normaliseOverlay(value: string | undefined | null): OverlayId {
    return value && VALID_OVERLAYS.includes(value as OverlayId) ? (value as OverlayId) : DEFAULT_OVERLAY;
  }

  function preferredOverlayForCapture(nextCapture: CaptureStatus | null | undefined = capture): OverlayId {
    return normaliseOverlay(nextCapture?.settings?.preferred_overlay ?? latestStatus.settings?.preferred_overlay);
  }

  function preferredLiveOverlay(nextCapture: CaptureStatus | null | undefined = capture): OverlayId {
    const preferredOverlay = preferredOverlayForCapture(nextCapture);
    return preferredOverlay === 'issues' ? FALLBACK_LIVE_OVERLAY : preferredOverlay;
  }

  function normaliseUnitSystem(value: string | undefined | null): UnitSystem {
    return value === 'metric' ? 'metric' : 'imperial';
  }

  function isRecordingActive(nextCapture: CaptureStatus | null | undefined): boolean {
    return Boolean(nextCapture?.recording?.active);
  }

  function issuesUnavailableForCapture(nextCapture: CaptureStatus | null | undefined = capture): boolean {
    return isRecordingActive(nextCapture);
  }

  function overlayAllowedForCapture(overlay: OverlayId, nextCapture: CaptureStatus | null | undefined = capture): boolean {
    return !(overlay === 'issues' && issuesUnavailableForCapture(nextCapture));
  }

  function overlayForCaptureContext(overlay: OverlayId, nextCapture: CaptureStatus | null | undefined = capture): OverlayId {
    return overlayAllowedForCapture(overlay, nextCapture) ? overlay : preferredLiveOverlay(nextCapture);
  }

  function overlayAllowedForCurrentContext(overlay: OverlayId): boolean {
    if (overlay !== 'issues') return true;
    if (selectedLapId) {
      return !!selectedLap && isSelectableCompletedLap(selectedLap);
    }
    return !issuesUnavailableForCapture();
  }

  function nextAvailableOverlayFrom(current: OverlayId): OverlayId {
    const availableOverlays = VALID_OVERLAYS.filter(overlayAllowedForCurrentContext);
    if (availableOverlays.length === 0) return current;
    const currentIndex = availableOverlays.indexOf(current);
    const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % availableOverlays.length : 0;
    return availableOverlays[nextIndex];
  }

  function stopDashboardPlaybackLoop() {
    if (dashboardPlaybackFrame !== null) {
      window.cancelAnimationFrame(dashboardPlaybackFrame);
      dashboardPlaybackFrame = null;
    }
    dashboardPlaybackLastFrameMs = null;
  }

  function dashboardPlaybackTick(now: number) {
    if (!dashboardPlaybackPlaying || canvasMode !== 'dashboard' || !selectedLapId) {
      stopDashboardPlaybackLoop();
      return;
    }
    const deltaMs = dashboardPlaybackLastFrameMs === null ? 0 : now - dashboardPlaybackLastFrameMs;
    dashboardPlaybackLastFrameMs = now;
    const next = nextPlaybackTime(dashboardPlaybackTimeMs, deltaMs, dashboardDurationMs);
    dashboardPlaybackTimeMs = next.timeMs;
    if (next.ended) {
      dashboardPlaybackPlaying = false;
      stopDashboardPlaybackLoop();
      return;
    }
    dashboardPlaybackFrame = window.requestAnimationFrame(dashboardPlaybackTick);
  }

  function syncDashboardPlaybackLoop() {
    if (!dashboardPlaybackPlaying || canvasMode !== 'dashboard' || !selectedLapId) {
      stopDashboardPlaybackLoop();
      return;
    }
    if (dashboardPlaybackFrame === null) {
      dashboardPlaybackFrame = window.requestAnimationFrame(dashboardPlaybackTick);
    }
  }

  function handleCanvasModeChange(nextMode: CanvasMode) {
    if (nextMode !== canvasMode) {
      closeIssuePopover();
    }
    canvasMode = nextMode;
    if (nextMode !== 'dashboard') {
      dashboardPlaybackPlaying = false;
      stopDashboardPlaybackLoop();
    }
  }

  function showLiveRouteView() {
    if (canvasMode !== 'route') {
      handleCanvasModeChange('route');
    } else if (dashboardPlaybackPlaying) {
      dashboardPlaybackPlaying = false;
      stopDashboardPlaybackLoop();
    }
    if (selectedLapId) {
      clearLapContext();
    }
  }

  function handleDashboardPlay() {
    if (!selectedLapId || displayedSamples.length === 0) return;
    dashboardPlaybackPlaying = true;
    syncDashboardPlaybackLoop();
  }

  function handleDashboardPause() {
    dashboardPlaybackPlaying = false;
    stopDashboardPlaybackLoop();
  }

  function handleDashboardScrub(timeMs: number) {
    dashboardPlaybackTimeMs = clampNumber(timeMs, 0, dashboardDurationMs);
    dashboardPlaybackLastFrameMs = null;
  }

  function toggleDashboardWidget(widgetId: DashboardWidgetId) {
    dashboardWidgetVisibility = {
      ...dashboardWidgetVisibility,
      [widgetId]: !dashboardWidgetVisibility[widgetId]
    };
  }

  function showAllDashboardWidgets() {
    dashboardWidgetVisibility = defaultDashboardWidgetVisibility();
  }

  function capLiveSampleHistory(nextSamples: LiveSample[]): LiveSample[] {
    if (nextSamples.length <= LIVE_SAMPLE_HISTORY_LIMIT) return nextSamples;
    return nextSamples.slice(-LIVE_SAMPLE_HISTORY_LIMIT);
  }

  function resetLiveSamples(nextSamples: LiveSample[] = []) {
    liveSamples = capLiveSampleHistory(nextSamples);
    liveSampleVersion += 1;
  }

  function isNearZero(value: number | null | undefined): boolean {
    return Math.abs(Number(value ?? 0)) <= LEGACY_MENU_SAMPLE_EPSILON;
  }

  function looksLikeLegacyNonRaceSample(sample: LiveSample): boolean {
    if (sample.is_race_on !== undefined) return false;
    return (
      sample.lap_number === 0 &&
      isNearZero(sample.current_lap) &&
      isNearZero(sample.current_race_time) &&
      isNearZero(sample.x) &&
      isNearZero(sample.y) &&
      isNearZero(sample.z) &&
      isNearZero(sample.speed_mps) &&
      sample.throttle === 0 &&
      sample.brake === 0 &&
      sample.steer === 0 &&
      sample.gear === 0
    );
  }

  function isRaceLiveSample(sample: LiveSample): boolean {
    if (sample.is_race_on === false) return false;
    if (sample.is_race_on === true) return true;
    return !looksLikeLegacyNonRaceSample(sample);
  }

  function distanceBetweenSamples(a: LiveSample, b: LiveSample): number {
    return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  }

  function hasImplausibleLiveJump(a: LiveSample, b: LiveSample): boolean {
    return distanceBetweenSamples(a, b) > LIVE_TELEPORT_DISTANCE_METERS;
  }

  function isLiveTraceGap(previousSample: LiveSample, nextSample: LiveSample): boolean {
    return hasImplausibleLiveJump(previousSample, nextSample) || nextSample.uncertainty === 'teleport';
  }

  function withoutImpossibleLiveTail(nextSamples: LiveSample[]): LiveSample[] {
    let trimIndex = nextSamples.length;
    for (let index = nextSamples.length - 1; index >= 0; index -= 1) {
      const sample = nextSamples[index];
      if (looksLikeLegacyNonRaceSample(sample)) {
        trimIndex = index;
        continue;
      }
      if (index > 0 && hasImplausibleLiveJump(nextSamples[index - 1], sample)) {
        trimIndex = index;
        break;
      }
    }
    return trimIndex === nextSamples.length ? nextSamples : nextSamples.slice(0, trimIndex);
  }

  function latestRaceLapId(nextSamples: LiveSample[]): string | null {
    for (let index = nextSamples.length - 1; index >= 0; index -= 1) {
      const lapId = nextSamples[index]?.lap_id;
      if (typeof lapId === 'string' && lapId.length > 0) {
        return lapId;
      }
    }
    return null;
  }

  function raceLiveSamplesForCurrentTrace(nextSamples: LiveSample[]): LiveSample[] {
    const raceSamples = nextSamples.filter(isRaceLiveSample);
    const lapId = latestRaceLapId(raceSamples);
    const currentTraceSamples = lapId ? raceSamples.filter((sample) => sample.lap_id === lapId) : raceSamples;
    return withoutImpossibleLiveTail(currentTraceSamples);
  }

  function startsNewLiveTrace(nextSample: LiveSample): boolean {
    if (liveSamples.length === 0) return false;
    if (nextSample.lap_action === 'finalize_and_start') return true;

    const previousSample = liveSamples[liveSamples.length - 1];
    if (
      nextSample.lap_action === 'start' &&
      typeof nextSample.lap_id === 'string' &&
      typeof previousSample?.lap_id === 'string' &&
      nextSample.lap_id !== previousSample.lap_id
    ) {
      return true;
    }

    return false;
  }

  function appendLiveSample(nextSample: LiveSample) {
    if (!isRaceLiveSample(nextSample)) return;

    if (startsNewLiveTrace(nextSample)) {
      resetLiveSamples([nextSample]);
      return;
    }

    const previousSample = liveSamples[liveSamples.length - 1];
    if (previousSample && isLiveTraceGap(previousSample, nextSample)) {
      resetLiveSamples([nextSample]);
      if (!selectedLapId) {
        closeIssuePopover();
      }
      return;
    }

    liveSamples.push(nextSample);
    liveSamples = capLiveSampleHistory(liveSamples);
    liveSampleVersion += 1;
  }

  function isNonRacePacketReceipt(nextCapture: CaptureStatus): boolean {
    const packetReceipt = nextCapture.packet_receipt;
    return packetReceipt?.last_is_race_on === false || packetReceipt?.last_packet_type === 'non_race';
  }

  function isRacePacketReceipt(nextCapture: CaptureStatus): boolean {
    const packetReceipt = nextCapture.packet_receipt;
    return packetReceipt?.last_is_race_on === true || packetReceipt?.last_packet_type === 'race';
  }

  function prunePauseEdgeLiveOutlier() {
    const nextSamples = withoutImpossibleLiveTail(liveSamples);
    if (nextSamples === liveSamples) return;
    liveSamples = nextSamples;
    liveSampleVersion += 1;
  }

  function resetLiveSamplesForLapBoundary() {
    if (liveFollowPaused || !isRecordingActive(capture)) return;
    resetLiveSamples();
    if (!selectedLapId) {
      closeIssuePopover();
    }
  }

  function hasKnownTrack(lap: LapSummary | null): boolean {
    return !!lap?.track_profile_id && !!lap.track_profile_name && !!lap.track_profile_layout;
  }

  function sameRange(left: SequenceRange | null, right: SequenceRange | null) {
    return left?.startSequence === right?.startSequence && left?.endSequence === right?.endSequence;
  }

  function isFullLapRange(range: SequenceRange | null, bounds: SequenceRange | null = fullLapBounds) {
    return !!range && !!bounds && sameRange(range, bounds);
  }

  function comparisonCacheKey(scope: ReferenceScope, range: SequenceRange | null) {
    return range ? `${scope}:${range.startSequence}-${range.endSequence}` : `${scope}:full`;
  }

  function touchLapContextCacheEntry(lapId: string, entry: LapContextCacheEntry) {
    lapContextCache.delete(lapId);
    lapContextCache.set(lapId, entry);
    while (lapContextCache.size > LAP_CONTEXT_CACHE_LIMIT) {
      const oldestLapId = lapContextCache.keys().next().value;
      if (typeof oldestLapId !== 'string') break;
      lapContextCache.delete(oldestLapId);
    }
  }

  function cachedLapContext(lapId: string): LapContextCacheEntry | null {
    const entry = lapContextCache.get(lapId);
    if (!entry) return null;
    touchLapContextCacheEntry(lapId, entry);
    return entry;
  }

  function rememberLapContext(
    lapId: string,
    summaryPayload: LapSummaryResponse,
    markersPayload: LapMarkersResponse,
    samples: LiveSample[],
    cacheGeneration = lapContextCacheGeneration
  ): LapContextCacheEntry {
    const existing = lapContextCache.get(lapId);
    const entry: LapContextCacheEntry = {
      summaryPayload,
      markersPayload,
      samples,
      comparisons: existing?.comparisons ?? new Map<string, ComparisonPayloads>()
    };
    if (cacheGeneration === lapContextCacheGeneration) {
      touchLapContextCacheEntry(lapId, entry);
    }
    return entry;
  }

  function restoreLapContext(entry: LapContextCacheEntry, showFullRangeOnCanvas: boolean) {
    selectedLapSummary = entry.summaryPayload.summary;
    selectedCarInfo = entry.summaryPayload.car ?? null;
    carCardVisible = true;
    carCardExpanded = false;
    markers = entry.markersPayload.markers;
    lapSamples = entry.samples;
    fullLapBounds = {
      startSequence: entry.summaryPayload.summary.start_sequence,
      endSequence: entry.summaryPayload.summary.end_sequence
    };
    showReviewedLapBoundsOnCanvas = showFullRangeOnCanvas;
  }

  function cachedComparison(lapId: string, scope: ReferenceScope, range: SequenceRange | null): ComparisonPayloads | null {
    const entry = cachedLapContext(lapId);
    return entry?.comparisons.get(comparisonCacheKey(scope, range)) ?? null;
  }

  function rememberComparison(
    lapId: string,
    scope: ReferenceScope,
    range: SequenceRange | null,
    payloads: ComparisonPayloads,
    cacheGeneration = comparisonCacheGeneration
  ) {
    if (cacheGeneration !== comparisonCacheGeneration) return;
    const entry = cachedLapContext(lapId);
    if (!entry) return;
    entry.comparisons.set(comparisonCacheKey(scope, range), payloads);
    touchLapContextCacheEntry(lapId, entry);
  }

  function comparisonReferencesLap(payloads: ComparisonPayloads, lapId: string) {
    return (
      payloads.referencePayload.reference?.lap_id === lapId ||
      payloads.ghostPayload.reference?.lap_id === lapId ||
      payloads.deltaPayload.reference?.lap_id === lapId
    );
  }

  function comparisonReferencesSession(payloads: ComparisonPayloads, sessionId: string) {
    return (
      payloads.referencePayload.reference?.session_id === sessionId ||
      payloads.ghostPayload.reference?.session_id === sessionId ||
      payloads.deltaPayload.reference?.session_id === sessionId
    );
  }

  function invalidateCachedComparisons(
    predicate?: (payloads: ComparisonPayloads, key: string, entry: LapContextCacheEntry, lapId: string) => boolean
  ) {
    for (const [lapId, entry] of lapContextCache.entries()) {
      for (const [key, payloads] of [...entry.comparisons.entries()]) {
        if (!predicate || predicate(payloads, key, entry, lapId)) {
          entry.comparisons.delete(key);
        }
      }
    }
    comparisonCacheGeneration += 1;
  }

  function invalidateLapContextCache(lapId: string) {
    lapContextCache.delete(lapId);
    invalidateCachedComparisons((payloads) => comparisonReferencesLap(payloads, lapId));
    lapContextCacheGeneration += 1;
  }

  function invalidateComparisonCache(scope?: ReferenceScope) {
    invalidateCachedComparisons((_payloads, key) => !scope || key.startsWith(`${scope}:`));
  }

  function lapContextEntryBelongsToSession(entry: LapContextCacheEntry, sessionId: string) {
    return entry.summaryPayload.session_id === sessionId || entry.markersPayload.session_id === sessionId;
  }

  function selectedLapBelongsToEventSession(sessionId: string | null) {
    if (!selectedLapId) return false;
    if (!sessionId) return true;
    return loadedSessionId === sessionId || laps.some((lap) => lap.id === selectedLapId && lap.session_id === sessionId);
  }

  function invalidateSessionComparisonCache(sessionId: string | null) {
    if (!sessionId) {
      invalidateComparisonCache();
      return;
    }
    invalidateCachedComparisons((payloads, _key, entry) =>
      lapContextEntryBelongsToSession(entry, sessionId) || comparisonReferencesSession(payloads, sessionId)
    );
  }

  function refreshSelectedComparisonForReferenceEvent(sessionId: string | null) {
    if (!selectedLapId || !selectedLapBelongsToEventSession(sessionId)) return;
    const lapId = selectedLapId;
    referenceVersion += 1;
    invalidateSectionSummaryRequests();
    clearComparisonState();
    void loadComparisonForLap(lapId, referenceScope, selectedRange);
  }

  function invalidateSessionLapContextCache(sessionId: string) {
    for (const [lapId, entry] of [...lapContextCache.entries()]) {
      if (entry.summaryPayload.session_id === sessionId || entry.markersPayload.session_id === sessionId) {
        lapContextCache.delete(lapId);
      }
    }
    invalidateCachedComparisons((payloads) => comparisonReferencesSession(payloads, sessionId));
    lapContextCacheGeneration += 1;
  }

  function clearLapContextCache() {
    lapContextCache = new Map<string, LapContextCacheEntry>();
    lapContextCacheGeneration += 1;
    comparisonCacheGeneration += 1;
  }

  function clampNumber(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value));
  }

  function clampSummaryCardPosition(x: number, y: number) {
    let minX = -SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    let maxX = SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    let minY = -SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    let maxY = SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    const stageRect = visualisationStageElement?.getBoundingClientRect();
    const cardRect = summaryCardElement?.getBoundingClientRect();

    if (stageRect && cardRect && stageRect.width > 0 && stageRect.height > 0 && cardRect.width > 0 && cardRect.height > 0) {
      const baseLeft = cardRect.left - summaryCardX;
      const baseRight = cardRect.right - summaryCardX;
      const baseTop = cardRect.top - summaryCardY;

      minX = stageRect.left + SUMMARY_VISIBLE_EDGE_PX - baseRight;
      maxX = stageRect.right - SUMMARY_VISIBLE_EDGE_PX - baseLeft;
      minY = stageRect.top - baseTop;
      maxY = stageRect.bottom - SUMMARY_HEADER_REACHABLE_PX - baseTop;
    }

    return {
      x: Math.round(clampNumber(x, minX, maxX)),
      y: Math.round(clampNumber(y, minY, maxY))
    };
  }

  function clampCarCardPosition(x: number, y: number) {
    let minX = -SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    let maxX = SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    let minY = -SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    let maxY = SUMMARY_FALLBACK_DRAG_LIMIT_PX;
    const stageRect = visualisationStageElement?.getBoundingClientRect();
    const cardRect = carCardElement?.getBoundingClientRect();

    if (stageRect && cardRect && stageRect.width > 0 && stageRect.height > 0 && cardRect.width > 0 && cardRect.height > 0) {
      const baseLeft = cardRect.left - carCardX;
      const baseRight = cardRect.right - carCardX;
      const baseTop = cardRect.top - carCardY;

      minX = stageRect.left + SUMMARY_VISIBLE_EDGE_PX - baseRight;
      maxX = stageRect.right - SUMMARY_VISIBLE_EDGE_PX - baseLeft;
      minY = stageRect.top - baseTop;
      maxY = stageRect.bottom - SUMMARY_HEADER_REACHABLE_PX - baseTop;
    }

    return {
      x: Math.round(clampNumber(x, minX, maxX)),
      y: Math.round(clampNumber(y, minY, maxY))
    };
  }

  function clampIssuePopoverPosition(x: number, y: number) {
    const wrapRect = canvasWrapElement?.getBoundingClientRect();
    const cardRect = issuePopoverElement?.getBoundingClientRect();

    if (!wrapRect || !cardRect || wrapRect.width <= 0 || wrapRect.height <= 0 || cardRect.width <= 0 || cardRect.height <= 0) {
      return {
        x: Math.round(Math.max(0, x)),
        y: Math.round(Math.max(0, y))
      };
    }

    const minX = POPOVER_VISIBLE_EDGE_PX - cardRect.width;
    const maxX = wrapRect.width - POPOVER_VISIBLE_EDGE_PX;
    const minY = 0;
    const maxY = wrapRect.height - POPOVER_HEADER_REACHABLE_PX;

    return {
      x: Math.round(clampNumber(x, minX, maxX)),
      y: Math.round(clampNumber(y, minY, maxY))
    };
  }

  function pushToast(level: ToastMessage['level'], message: string, sticky = false) {
    const toast = { id: nextToastId++, level, message, sticky };
    lastStatusEvent = message;
    toasts = [...toasts, toast];
    if (!sticky) {
      window.setTimeout(() => {
        toasts = toasts.filter((item) => item.id !== toast.id);
      }, 4000);
    }
    return toast;
  }

  function dismissToast(id: number) {
    toasts = toasts.filter((toast) => toast.id !== id);
    if (disconnectedToastId === id) {
      disconnectedToastId = null;
    }
  }

  function showDisconnectedToast() {
    if (disconnectedToastId !== null && toasts.some((toast) => toast.id === disconnectedToastId)) {
      return;
    }
    const toast = pushToast('error', 'Telemetry stream disconnected', true);
    disconnectedToastId = toast.id;
  }

  function clearDisconnectedToast() {
    if (disconnectedToastId !== null) {
      dismissToast(disconnectedToastId);
    }
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function clearSummaryDebounceTimer() {
    if (summaryDebounceTimer !== null) {
      window.clearTimeout(summaryDebounceTimer);
      summaryDebounceTimer = null;
    }
  }

  function closeEvents() {
    eventSource?.close();
    eventSource = null;
  }

  function applyCaptureState(nextCapture: CaptureStatus) {
    const wasRecording = isRecordingActive(capture);
    const nextRecording = isRecordingActive(nextCapture);
    const nextPacketIsNonRace = isNonRacePacketReceipt(nextCapture);
    capture = { ...capture, ...nextCapture };
    if (nextCapture.listener) {
      listener = { ...listener, ...nextCapture.listener };
    }
    latestStatus = {
      listener,
      settings: capture.settings ?? latestStatus.settings,
      capture: { ...capture, listener, settings: capture.settings ?? latestStatus.settings }
    };
    if (!wasRecording && nextRecording) {
      resetLiveSamples();
      liveSessionId = null;
      liveCarInfo = null;
      liveFollowPaused = false;
      carCardVisible = true;
      carCardExpanded = false;
      if (activeSession) {
        loadedSessionId = activeSession.id;
      }
      clearLapContext();
      if (canvasMode !== 'route') {
        handleCanvasModeChange('route');
      }
      if (selectedOverlay === 'issues') {
        selectedOverlay = preferredLiveOverlay();
      }
      pushToast('success', 'Live recording view enabled', false);
    } else if (wasRecording && !nextRecording) {
      resetLiveSamples();
      liveSessionId = null;
      liveCarInfo = null;
    } else if (wasRecording && nextRecording && nextPacketIsNonRace) {
      prunePauseEdgeLiveOutlier();
    } else if (wasRecording && nextRecording && !liveFollowPaused && isRacePacketReceipt(nextCapture)) {
      showLiveRouteView();
    }
  }

  function parseSseJson(event: MessageEvent): Record<string, unknown> | null {
    try {
      const parsed = JSON.parse(event.data);
      if (parsed && typeof parsed === 'object') {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // handled below
    }

    if (!malformedEventToastShown) {
      malformedEventToastShown = true;
      pushToast('warning', MALFORMED_EVENT_TOAST_MESSAGE);
    }
    return null;
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value && typeof value === 'object' && !Array.isArray(value));
  }

  function trackMatchAssignmentAssigned(value: unknown): boolean {
    if (!isRecord(value)) return false;
    const assignment = isRecord(value.assignment) ? value.assignment : null;
    return assignment?.assigned === true;
  }

  function eventTrackMatchAssigned(data: Record<string, unknown>): boolean {
    return trackMatchAssignmentAssigned(data.track_match);
  }

  function trackMatchResponseAssigned(response: TrackMatchResponse): boolean {
    return trackMatchAssignmentAssigned(response);
  }

  function eventSessionId(data: Record<string, unknown>): string | null {
    return typeof data.session_id === 'string' ? data.session_id : null;
  }

  function shouldRefreshLoadedSessionForEvent(sessionId: string | null): boolean {
    return sessionId
      ? loadedSessionId === sessionId
      : Boolean(loadedSessionId && activeSession?.id === loadedSessionId);
  }

  async function refreshTrackProfilesList() {
    const nextProfiles = await fetchTrackProfiles();
    if (disposed) return;
    trackProfiles = nextProfiles;
  }

  function refreshHistoryForSessionEvent(sessionId: string | null) {
    if (shouldRefreshLoadedSessionForEvent(sessionId)) {
      void refreshLoadedSessionLaps();
    }
    void refreshSessionPage(sessionFilters);
  }

  function handleAutomaticTrackAssignmentEvent(data: Record<string, unknown>) {
    const lapId = typeof data.lap_id === 'string' ? data.lap_id : null;
    const sessionId = eventSessionId(data);
    if (lapId) {
      invalidateLapContextCache(lapId);
    }
    if (eventTrackMatchAssigned(data)) {
      invalidateSessionComparisonCache(sessionId);
      refreshSelectedComparisonForReferenceEvent(sessionId);
    }
    void refreshTrackProfilesList();
    refreshHistoryForSessionEvent(sessionId);
  }

  function listenerStatusFromEvent(data: Record<string, unknown>): Partial<ListenerStatus> {
    return isRecord(data.listener) ? (data.listener as Partial<ListenerStatus>) : (data as Partial<ListenerStatus>);
  }

  function isInitialSsePlaceholderStatus(data: Partial<ListenerStatus>) {
    return (
      data.state === 'waiting' &&
      data.message === 'waiting for telemetry' &&
      data.udp_host === undefined &&
      data.udp_port === undefined &&
      data.packets_received === undefined
    );
  }

  function invalidateSectionSummaryRequests() {
    summaryRequestId += 1;
    clearSummaryDebounceTimer();
  }

  function clearComparisonState() {
    comparisonRequestId += 1;
    referenceContextKey = null;
    referenceLap = null;
    ghostSamples = [];
    selectedDeltaSummary = null;
    comparisonBusy = false;
  }

  function clearLapDrilldownState() {
    invalidateSectionSummaryRequests();
    lapSamples = [];
    markers = [];
    fullLapBounds = null;
    selectedRange = null;
    showReviewedLapBoundsOnCanvas = false;
    selectedLapSummary = null;
    selectedCarInfo = null;
    carCardExpanded = false;
    clearComparisonState();
  }

  function clearLapContext() {
    selectedLapId = null;
    clearLapDrilldownState();
    closeIssuePopover();
  }

  function closeIssuePopover() {
    issuePopoverOpen = false;
    issuePopoverItems = [];
    issuePopoverPinned = false;
    issuePopoverDragged = false;
  }

  function clampCanvasLoadingProgress(progress: number) {
    return Math.max(0, Math.min(1, progress));
  }

  function canvasLoadingProgress(scope: CanvasLoadingScope, progress: number) {
    return clampCanvasLoadingProgress(scope.baseProgress + scope.progressSpan * progress);
  }

  function beginCanvasLoading(message: string, progress: number | null = 0): CanvasLoadingScope {
    const token = ++canvasLoadingToken;
    canvasLoading = {
      token,
      message,
      progress: progress === null ? null : clampCanvasLoadingProgress(progress)
    };
    return { token, baseProgress: 0, progressSpan: 1 };
  }

  function childCanvasLoadingScope(scope: CanvasLoadingScope, baseProgress: number, progressSpan: number): CanvasLoadingScope {
    return {
      token: scope.token,
      baseProgress: canvasLoadingProgress(scope, baseProgress),
      progressSpan: scope.progressSpan * progressSpan
    };
  }

  function updateCanvasLoading(scope: CanvasLoadingScope | null, message: string, progress?: number | null) {
    if (!scope || canvasLoading?.token !== scope.token) return;
    canvasLoading = {
      token: scope.token,
      message,
      progress: progress === undefined ? canvasLoading.progress : progress === null ? null : canvasLoadingProgress(scope, progress)
    };
  }

  function finishCanvasLoading(scope: CanvasLoadingScope | null) {
    if (scope && canvasLoading?.token === scope.token) {
      canvasLoading = null;
    }
  }

  function telemetrySampleCountLabel(count: number) {
    return `${count.toLocaleString()} telemetry ${count === 1 ? 'sample' : 'samples'}`;
  }

  function lapCountLabel(count: number) {
    return `${count.toLocaleString()} ${count === 1 ? 'lap' : 'laps'}`;
  }

  function issueMarkerCountLabel(count: number) {
    return `${count.toLocaleString()} issue ${count === 1 ? 'marker' : 'markers'}`;
  }

  async function fetchLapSummaryForSelection(
    lapId: string,
    scope: ReferenceScope,
    range: SequenceRange | null,
    requestId: number,
    requestReferenceVersion: number
  ) {
    const normalizedRange = range && !isFullLapRange(range) ? range : null;
    const [summaryPayload, deltaPayload] = await Promise.all([
      normalizedRange
        ? fetchLapSummary(lapId, normalizedRange.startSequence, normalizedRange.endSequence)
        : fetchLapSummary(lapId),
      normalizedRange
        ? fetchDelta(lapId, scope, normalizedRange.startSequence, normalizedRange.endSequence)
        : fetchDelta(lapId, scope)
    ]);

    if (
      disposed ||
      requestId !== summaryRequestId ||
      selectedLapId !== lapId ||
      referenceScope !== scope ||
      summaryPayload.lap_id !== lapId ||
      deltaPayload.lap_id !== lapId ||
      deltaPayload.scope !== scope
    ) {
      return;
    }

    selectedRange = normalizedRange;
    selectedLapSummary = summaryPayload.summary;
    if (!normalizedRange) {
      selectedCarInfo = summaryPayload.car ?? null;
      carCardExpanded = false;
    }
    if (requestReferenceVersion !== referenceVersion) {
      return;
    }
    selectedDeltaSummary = deltaPayload.summary;
  }

  function scheduleLapSummaryLoad(range: SequenceRange | null) {
    if (!selectedLapId) {
      selectedLapSummary = null;
      selectedRange = null;
      showReviewedLapBoundsOnCanvas = false;
      return;
    }

    const lapId = selectedLapId;
    const scope = referenceScope;
    const normalizedRange = range && !isFullLapRange(range) ? range : null;
    const requestReferenceVersion = referenceVersion;
    selectedRange = normalizedRange;
    selectedDeltaSummary = null;
    const requestId = ++summaryRequestId;
    clearSummaryDebounceTimer();
    summaryDebounceTimer = window.setTimeout(() => {
      summaryDebounceTimer = null;
      void fetchLapSummaryForSelection(lapId, scope, normalizedRange, requestId, requestReferenceVersion).catch(() => {
        if (
          disposed ||
          requestId !== summaryRequestId ||
          selectedLapId !== lapId ||
          referenceScope !== scope ||
          requestReferenceVersion !== referenceVersion
        ) {
          return;
        }
        selectedLapSummary = null;
        selectedDeltaSummary = null;
        pushToast('error', 'Unable to load section summary', false);
      });
    }, SECTION_SUMMARY_DEBOUNCE_MS);
  }

  function normalizedComparisonRange(range: SequenceRange | null) {
    return range && !isFullLapRange(range) ? range : null;
  }

  function comparisonRangeMatchesSelection(range: SequenceRange | null) {
    return sameRange(normalizedComparisonRange(selectedRange), range);
  }

  function applyComparisonPayloads(lapId: string, scope: ReferenceScope, normalizedRange: SequenceRange | null, payloads: ComparisonPayloads) {
    const { referencePayload, ghostPayload, deltaPayload } = payloads;
    if (
      selectedLapId !== lapId ||
      referenceScope !== scope ||
      referencePayload.lap_id !== lapId ||
      ghostPayload.lap_id !== lapId ||
      deltaPayload.lap_id !== lapId ||
      referencePayload.scope !== scope ||
      ghostPayload.scope !== scope ||
      deltaPayload.scope !== scope
    ) {
      return false;
    }

    referenceContextKey = referencePayload.context_key;
    referenceLap = referencePayload.reference;
    ghostSamples = ghostPayload.reference ? ghostPayload.samples : [];
    if (!comparisonRangeMatchesSelection(normalizedRange)) {
      return true;
    }

    selectedDeltaSummary = deltaPayload.summary;
    return true;
  }

  async function loadComparisonForLap(
    lapId: string,
    scope: ReferenceScope,
    range: SequenceRange | null = selectedRange,
    loadingScope: CanvasLoadingScope | null = null
  ): Promise<boolean> {
    const requestId = ++comparisonRequestId;
    const cacheGeneration = comparisonCacheGeneration;
    const normalizedRange = normalizedComparisonRange(range);
    comparisonBusy = true;
    updateCanvasLoading(loadingScope, 'Loading reference comparison…', 0.05);

    const cached = cachedComparison(lapId, scope, normalizedRange);
    if (cached) {
      if (!disposed && requestId === comparisonRequestId) {
        const applied = applyComparisonPayloads(lapId, scope, normalizedRange, cached);
        comparisonBusy = false;
        updateCanvasLoading(loadingScope, 'Restored cached reference comparison…', 0.95);
        return applied;
      }
      return false;
    }

    try {
      let loadedComparisonParts = 0;
      const markComparisonPartLoaded = (message: string) => {
        loadedComparisonParts += 1;
        updateCanvasLoading(loadingScope, message, 0.15 + loadedComparisonParts * 0.25);
      };
      const referenceLoad = fetchReference(lapId, scope).then((payload) => {
        markComparisonPartLoaded('Loaded reference lap details…');
        return payload;
      });
      const ghostLoad = fetchGhost(lapId, scope).then((payload) => {
        markComparisonPartLoaded('Loaded ghost route overlay…');
        return payload;
      });
      const deltaLoad = (normalizedRange
        ? fetchDelta(lapId, scope, normalizedRange.startSequence, normalizedRange.endSequence)
        : fetchDelta(lapId, scope)
      ).then((payload) => {
        markComparisonPartLoaded('Loaded reference delta summary…');
        return payload;
      });
      const [referencePayload, ghostPayload, deltaPayload] = await Promise.all([referenceLoad, ghostLoad, deltaLoad]);
      if (
        disposed ||
        requestId !== comparisonRequestId ||
        cacheGeneration !== comparisonCacheGeneration ||
        selectedLapId !== lapId ||
        referenceScope !== scope ||
        referencePayload.lap_id !== lapId ||
        ghostPayload.lap_id !== lapId ||
        deltaPayload.lap_id !== lapId ||
        referencePayload.scope !== scope ||
        ghostPayload.scope !== scope ||
        deltaPayload.scope !== scope
      ) {
        return false;
      }

      const payloads = { referencePayload, ghostPayload, deltaPayload };
      rememberComparison(lapId, scope, normalizedRange, payloads, cacheGeneration);
      const applied = applyComparisonPayloads(lapId, scope, normalizedRange, payloads);
      updateCanvasLoading(loadingScope, 'Reference comparison ready…', 0.95);
      return applied;
    } catch (error) {
      if (
        disposed ||
        requestId !== comparisonRequestId ||
        selectedLapId !== lapId ||
        referenceScope !== scope ||
        !comparisonRangeMatchesSelection(normalizedRange)
      ) {
        return false;
      }
      referenceContextKey = null;
      referenceLap = null;
      ghostSamples = [];
      selectedDeltaSummary = null;
      updateCanvasLoading(loadingScope, 'Unable to load reference comparison', 1);
      pushToast('error', 'Unable to load reference comparison', false);
      return false;
    } finally {
      if (!disposed && requestId === comparisonRequestId && selectedLapId === lapId && referenceScope === scope) {
        comparisonBusy = false;
      }
    }
  }

  async function loadLapContext(
    lapId: string,
    showFullRangeOnCanvas = false,
    awaitComparison = true,
    loadingScope: CanvasLoadingScope | null = null
  ) {
    const requestId = ++lapContextRequestId;
    const cacheGeneration = lapContextCacheGeneration;
    const ownsCanvasLoading = loadingScope === null;
    const lapLoadingScope = loadingScope ?? beginCanvasLoading('Preparing lap view…', 0.02);
    updateCanvasLoading(lapLoadingScope, 'Preparing lap view…', 0.04);
    const lapSessionId = laps.find((lap) => lap.id === lapId)?.session_id;
    if (lapSessionId) {
      loadedSessionId = lapSessionId;
    }
    selectedLapId = lapId;
    clearLapDrilldownState();
    closeIssuePopover();

    try {
      const cached = cachedLapContext(lapId);
      if (cached) {
        updateCanvasLoading(lapLoadingScope, 'Restoring cached lap telemetry…', 0.35);
        restoreLapContext(cached, showFullRangeOnCanvas);
        const comparisonLoad = loadComparisonForLap(lapId, referenceScope, null, childCanvasLoadingScope(lapLoadingScope, 0.58, 0.36));
        let comparisonReady = true;
        if (awaitComparison) {
          comparisonReady = await comparisonLoad;
        } else {
          void comparisonLoad;
        }
        if (comparisonReady) {
          updateCanvasLoading(lapLoadingScope, 'Route visualiser ready…', 0.98);
        }
        return;
      }

      updateCanvasLoading(lapLoadingScope, 'Loading lap summary, markers, and telemetry…', 0.08);
      const summaryLoad = fetchLapSummary(lapId).then((payload) => {
        updateCanvasLoading(lapLoadingScope, 'Loaded lap summary…', 0.22);
        return payload;
      });
      const markersLoad = fetchLapMarkers(lapId).then((payload) => {
        updateCanvasLoading(lapLoadingScope, `Loaded ${issueMarkerCountLabel(payload.markers.length)}…`, 0.34);
        return payload;
      });
      const samplesLoad = fetchLapSamples(lapId).then((samples) => {
        updateCanvasLoading(lapLoadingScope, `Loaded ${telemetrySampleCountLabel(samples.length)}…`, 0.48);
        return samples;
      });
      const [summaryPayload, markersPayload, nextLapSamples] = await Promise.all([summaryLoad, markersLoad, samplesLoad]);
      if (disposed || requestId !== lapContextRequestId || cacheGeneration !== lapContextCacheGeneration || selectedLapId !== lapId) return;

      updateCanvasLoading(lapLoadingScope, 'Preparing route display…', 0.56);
      const entry = rememberLapContext(lapId, summaryPayload, markersPayload, nextLapSamples, cacheGeneration);
      restoreLapContext(entry, showFullRangeOnCanvas);
      const comparisonLoad = loadComparisonForLap(lapId, referenceScope, null, childCanvasLoadingScope(lapLoadingScope, 0.62, 0.34));
      let comparisonReady = true;
      if (awaitComparison) {
        comparisonReady = await comparisonLoad;
      } else {
        void comparisonLoad;
      }
      if (comparisonReady) {
        updateCanvasLoading(lapLoadingScope, 'Route visualiser ready…', 0.98);
      }
    } catch (error) {
      if (disposed || requestId !== lapContextRequestId || selectedLapId !== lapId) return;
      updateCanvasLoading(lapLoadingScope, 'Unable to load lap data', 1);
      clearLapDrilldownState();
      throw error;
    } finally {
      if (ownsCanvasLoading) {
        finishCanvasLoading(lapLoadingScope);
      }
    }
  }

  async function loadTrackAssetsForProfile(profileId: string | null) {
    const requestId = ++trackAssetProfileRequestId;
    trackAssets = [];
    selectedTrackAssetId = null;
    if (!profileId) {
      return;
    }

    try {
      const nextAssets = await fetchTrackAssets(profileId);
      if (disposed || requestId !== trackAssetProfileRequestId || selectedTrackProfileId !== profileId) return;
      trackAssets = nextAssets;
    } catch (error) {
      if (disposed || requestId !== trackAssetProfileRequestId || selectedTrackProfileId !== profileId) return;
      trackAssets = [];
      selectedTrackAssetId = null;
      pushToast('error', 'Unable to load track assets', false);
    }
  }

  function ensureSelectedLap(nextLaps: LapSummary[]) {
    if (capture.recording.active) {
      return;
    }
    const nextDefaultLapId = newestSelectableCompletedLapId(nextLaps);
    if (selectedLapId && nextLaps.some((lap) => lap.id === selectedLapId)) {
      return;
    }
    if (!nextDefaultLapId) {
      selectedLapId = null;
      clearLapDrilldownState();
      return;
    }
    void loadLapContext(nextDefaultLapId, true, false).catch(() => {
      pushToast('error', 'Unable to load lap drilldown data', false);
    });
  }

  function removeLapFromLoadedHistory(lapId: string) {
    invalidateLapContextCache(lapId);
    const nextLaps = laps.filter((lap) => lap.id !== lapId);
    const lapWasLoaded = nextLaps.length !== laps.length;
    if (lapWasLoaded) {
      laps = nextLaps;
    }
    deletingLapIds = deletingLapIds.filter((candidate) => candidate !== lapId);
    if (selectedLapId === lapId) {
      clearLapContext();
      ensureSelectedLap(nextLaps);
    }
  }

  async function refreshSessionPage(filters: SessionFilters = sessionFilters) {
    sessionBrowserBusy = true;
    sessionBrowserError = null;
    const normalizedFilters = { ...filters, page: filters.page ?? 1, pageSize: filters.pageSize ?? 100 };
    try {
      const nextPage = await fetchSessionPage(normalizedFilters);
      if (disposed) return;
      sessionFilters = normalizedFilters;
      sessionPage = nextPage;
      sessions = nextPage.sessions;
    } catch (error) {
      if (disposed) return;
      sessionBrowserError = 'Unable to load sessions';
      pushToast('error', 'Unable to load sessions', false);
    } finally {
      if (!disposed) {
        sessionBrowserBusy = false;
      }
    }
  }

  async function loadStatsSummary() {
    statsLoading = true;
    statsError = null;
    try {
      const summary = await fetchStatsSummary();
      if (disposed) return;
      statsSummary = summary;
    } catch (error) {
      if (disposed) return;
      statsError = 'Unable to load stats';
      pushToast('error', 'Unable to load stats', false);
    } finally {
      if (!disposed) {
        statsLoading = false;
      }
    }
  }

  async function refreshActiveSession() {
    activeSession = await fetchActiveSession();
    if (!loadedSessionId && activeSession) {
      loadedSessionId = activeSession.id;
    }
  }

  async function loadSession(sessionId: string, loadingScope: CanvasLoadingScope | null = null) {
    const ownsCanvasLoading = loadingScope === null;
    const sessionLoadingScope = loadingScope ?? beginCanvasLoading('Loading session…', 0.04);
    try {
      updateCanvasLoading(sessionLoadingScope, 'Preparing session view…', 0.08);
      loadedSessionId = sessionId;
      clearLapContext();
      updateCanvasLoading(sessionLoadingScope, 'Loading session laps…', 0.25);
      const nextLaps = await fetchSessionLaps(sessionId);
      if (disposed || loadedSessionId !== sessionId) return;
      laps = nextLaps;
      const defaultLapId = capture.recording.active ? null : newestSelectableCompletedLapId(nextLaps);
      if (defaultLapId) {
        updateCanvasLoading(sessionLoadingScope, `Loaded ${lapCountLabel(nextLaps.length)}; loading selected lap…`, 0.86);
      } else {
        updateCanvasLoading(sessionLoadingScope, `Loaded ${lapCountLabel(nextLaps.length)}; no completed laps to display.`, 0.95);
      }
      ensureSelectedLap(nextLaps);
    } finally {
      if (ownsCanvasLoading) {
        finishCanvasLoading(sessionLoadingScope);
      }
    }
  }

  function isImportJobActive(job: RawTelemetryImportJob): boolean {
    return job.status === 'queued' || job.status === 'running' || job.status === 'cancelling';
  }

  function terminalImportJobStatus(status: string): boolean {
    return status === 'completed' || status === 'failed' || status === 'cancelled';
  }

  function upsertImportJob(job: RawTelemetryImportJob) {
    importJobs = [job, ...importJobs.filter((candidate) => candidate.id !== job.id)].sort(
      (left, right) => right.created_at_ms - left.created_at_ms
    );
  }

  function clearImportJobPollTimer() {
    if (importJobPollTimer !== null) {
      window.clearTimeout(importJobPollTimer);
      importJobPollTimer = null;
    }
  }

  function scheduleImportJobPolling(delayMs = IMPORT_JOB_POLL_DELAY_MS) {
    if (disposed || importJobPollTimer !== null) return;
    importJobPollTimer = window.setTimeout(() => {
      importJobPollTimer = null;
      void refreshImportJobs({ silent: true });
    }, delayMs);
  }

  async function refreshAfterImportJobCompletion(job: RawTelemetryImportJob) {
    if (job.session_ids.length === 0) return;
    clearLapContextCache();
    const [nextActiveSession, nextPage] = await Promise.all([
      fetchActiveSession(),
      fetchSessionPage(sessionFilters)
    ]);
    if (disposed) return;
    activeSession = nextActiveSession;
    sessionPage = nextPage;
    sessions = nextPage.sessions;
    if (loadedSessionId && job.session_ids.includes(loadedSessionId)) {
      await refreshLoadedSessionLaps();
    }
  }

  async function handleImportJobTransitions(nextJobs: RawTelemetryImportJob[]) {
    const nextStatuses: Record<string, string> = {};
    const terminalJobs: RawTelemetryImportJob[] = [];
    for (const job of nextJobs) {
      const previousStatus = importJobStatuses[job.id];
      nextStatuses[job.id] = job.status;
      if (previousStatus && !terminalImportJobStatus(previousStatus) && terminalImportJobStatus(job.status)) {
        terminalJobs.push(job);
      }
    }
    importJobStatuses = nextStatuses;

    for (const job of terminalJobs) {
      if (job.status === 'completed') {
        const packetNoun = job.packet_count === 1 ? 'packet' : 'packets';
        const errorSuffix = job.failed_files > 0 ? ` (${job.failed_files} files failed)` : '';
        pushToast('success', `Import job finished: ${job.packet_count.toLocaleString()} ${packetNoun}${errorSuffix}`);
        await refreshAfterImportJobCompletion(job);
      } else if (job.status === 'failed') {
        pushToast('error', `Import job failed: ${job.status_text}`, false);
      } else if (job.status === 'cancelled') {
        pushToast('info', job.status_text);
        await refreshAfterImportJobCompletion(job);
      }
    }
  }

  async function refreshImportJobs(options: { silent?: boolean } = {}) {
    const requestId = ++importJobsRequestId;
    if (!options.silent) importJobsLoading = true;
    try {
      const nextJobs = await fetchRawTelemetryImportJobs();
      if (disposed || requestId !== importJobsRequestId) return;
      importJobs = nextJobs;
      await handleImportJobTransitions(nextJobs);
      if (nextJobs.some(isImportJobActive) || activeUtilityModal === 'import') {
        scheduleImportJobPolling();
      }
    } catch (error) {
      if (!options.silent) {
        pushToast('error', 'Unable to refresh raw telemetry import jobs', false);
      }
    } finally {
      if (!disposed && requestId === importJobsRequestId) {
        importJobsLoading = false;
      }
    }
  }

  async function handleImportRawTelemetry(event: CustomEvent<{ files: File[]; label: string; sourceType: 'file' | 'files' | 'folder' }>) {
    importBusy = true;
    try {
      const job = await createRawTelemetryImportJob({
        files: event.detail.files,
        label: event.detail.label,
        sourceType: event.detail.sourceType
      });
      if (disposed) return;
      upsertImportJob(job);
      importJobStatuses = { ...importJobStatuses, [job.id]: job.status };
      scheduleImportJobPolling(250);
      const fileNoun = job.total_files === 1 ? 'file' : 'files';
      pushToast('info', `Started raw telemetry import job for ${job.total_files} ${fileNoun}.`);
    } catch (error) {
      if (disposed) return;
      pushToast('error', 'Unable to start raw telemetry import job', false);
    } finally {
      if (!disposed) {
        importBusy = false;
      }
    }
  }

  async function handleCancelImportJob(event: CustomEvent<{ jobId: string }>) {
    const jobId = event.detail.jobId;
    if (cancellingImportJobIds.includes(jobId)) return;
    cancellingImportJobIds = [...cancellingImportJobIds, jobId];
    try {
      const job = await cancelRawTelemetryImportJob(jobId);
      if (disposed) return;
      upsertImportJob(job);
      scheduleImportJobPolling(250);
    } catch (error) {
      if (!disposed) {
        pushToast('error', 'Unable to cancel raw telemetry import job', false);
      }
    } finally {
      cancellingImportJobIds = cancellingImportJobIds.filter((candidate) => candidate !== jobId);
    }
  }

  function isExportJobActive(job: TelemetryExportJob): boolean {
    return job.status === 'queued' || job.status === 'running' || job.status === 'cancelling';
  }

  function terminalExportJobStatus(status: string): boolean {
    return status === 'completed' || status === 'failed' || status === 'cancelled';
  }

  function upsertExportJob(job: TelemetryExportJob) {
    exportJobs = [job, ...exportJobs.filter((candidate) => candidate.id !== job.id)].sort(
      (left, right) => right.created_at_ms - left.created_at_ms
    );
  }

  function clearExportJobPollTimer() {
    if (exportJobPollTimer !== null) {
      window.clearTimeout(exportJobPollTimer);
      exportJobPollTimer = null;
    }
  }

  function scheduleExportJobPolling(delayMs = EXPORT_JOB_POLL_DELAY_MS) {
    if (disposed || exportJobPollTimer !== null) return;
    exportJobPollTimer = window.setTimeout(() => {
      exportJobPollTimer = null;
      void refreshExportJobs({ silent: true });
    }, delayMs);
  }

  function handleExportJobTransitions(nextJobs: TelemetryExportJob[]) {
    const nextStatuses: Record<string, string> = {};
    for (const job of nextJobs) {
      const previousStatus = exportJobStatuses[job.id];
      nextStatuses[job.id] = job.status;
      if (!previousStatus || terminalExportJobStatus(previousStatus) || !terminalExportJobStatus(job.status)) {
        continue;
      }
      if (job.status === 'completed') {
        pushToast('success', `${job.label} export completed: ${job.total_size_bytes.toLocaleString()} bytes.`);
      } else if (job.status === 'failed') {
        pushToast('error', `${job.label} export failed`, false);
      } else if (job.status === 'cancelled') {
        pushToast('info', `${job.label} export cancelled`);
      }
    }
    exportJobStatuses = nextStatuses;
  }

  async function loadExportDefaults() {
    const requestId = ++exportDefaultsRequestId;
    exportDefaultsLoading = true;
    try {
      const defaults = await fetchTelemetryExportDefaults();
      if (disposed || requestId !== exportDefaultsRequestId) return;
      exportDefaults = defaults;
    } catch (error) {
      if (!disposed && requestId === exportDefaultsRequestId) {
        pushToast('error', 'Unable to load telemetry export defaults', false);
      }
    } finally {
      if (!disposed && requestId === exportDefaultsRequestId) {
        exportDefaultsLoading = false;
      }
    }
  }

  async function refreshExportJobs(options: { silent?: boolean } = {}) {
    const requestId = ++exportJobsRequestId;
    if (!options.silent) exportJobsLoading = true;
    try {
      const nextJobs = await fetchTelemetryExportJobs();
      if (disposed || requestId !== exportJobsRequestId) return;
      exportJobs = nextJobs;
      handleExportJobTransitions(nextJobs);
      if (nextJobs.some(isExportJobActive) || activeUtilityModal === 'export') {
        scheduleExportJobPolling();
      }
    } catch (error) {
      if (!options.silent) {
        pushToast('error', 'Unable to refresh telemetry export jobs', false);
      }
    } finally {
      if (!disposed && requestId === exportJobsRequestId) {
        exportJobsLoading = false;
      }
    }
  }

  async function handleExportTelemetry(event: CustomEvent<{ kind: TelemetryExportKind; output_dir: string; filename_prefix: string }>) {
    exportBusy = true;
    exportJobsRequestId += 1;
    try {
      const filenamePrefix = event.detail.filename_prefix.trim();
      const job = await createTelemetryExportJob({
        kind: event.detail.kind,
        output_dir: event.detail.output_dir,
        ...(filenamePrefix ? { filename_prefix: filenamePrefix } : {})
      });
      if (disposed) return;
      upsertExportJob(job);
      exportJobStatuses = { ...exportJobStatuses, [job.id]: job.status };
      scheduleExportJobPolling(250);
      pushToast('info', `Started ${job.label} export job.`);
    } catch (error) {
      if (disposed) return;
      pushToast('error', 'Unable to start telemetry export job', false);
    } finally {
      if (!disposed) {
        exportBusy = false;
      }
    }
  }

  async function handleCancelExportJob(event: CustomEvent<{ jobId: string }>) {
    const jobId = event.detail.jobId;
    if (cancellingExportJobIds.includes(jobId)) return;
    cancellingExportJobIds = [...cancellingExportJobIds, jobId];
    exportJobsRequestId += 1;
    try {
      const job = await cancelTelemetryExportJob(jobId);
      if (disposed) return;
      upsertExportJob(job);
      scheduleExportJobPolling(250);
    } catch (error) {
      if (!disposed) {
        pushToast('error', 'Unable to cancel telemetry export job', false);
      }
    } finally {
      cancellingExportJobIds = cancellingExportJobIds.filter((candidate) => candidate !== jobId);
    }
  }

  async function refreshLoadedSessionLaps() {
    const sessionId = loadedSessionId;
    if (!sessionId) {
      laps = [];
      clearLapContext();
      return;
    }
    const nextLaps = await fetchSessionLaps(sessionId);
    if (disposed || loadedSessionId !== sessionId) return;
    laps = nextLaps;
    ensureSelectedLap(nextLaps);
  }

  async function refreshHistory() {
    const sessionId = loadedSessionId;
    const [nextActiveSession, nextPage, nextLaps] = await Promise.all([
      fetchActiveSession(),
      fetchSessionPage(sessionFilters),
      sessionId ? fetchSessionLaps(sessionId) : Promise.resolve([] as LapSummary[])
    ]);
    if (disposed) return;
    activeSession = nextActiveSession;
    sessionPage = nextPage;
    sessions = nextPage.sessions;
    if (!loadedSessionId && activeSession) {
      loadedSessionId = activeSession.id;
    }
    if (sessionId && loadedSessionId === sessionId) {
      laps = nextLaps;
      ensureSelectedLap(nextLaps);
    }
  }

  async function refreshTrackProfilesHistoryAndComparison() {
    const lapIdToReload = selectedLapId;
    const sessionId = loadedSessionId;
    clearLapContextCache();
    const [nextProfiles, nextActiveSession, nextPage, nextLaps] = await Promise.all([
      fetchTrackProfiles(),
      fetchActiveSession(),
      fetchSessionPage(sessionFilters),
      sessionId ? fetchSessionLaps(sessionId) : Promise.resolve([] as LapSummary[])
    ]);
    if (disposed) return;
    trackProfiles = nextProfiles;
    activeSession = nextActiveSession;
    sessionPage = nextPage;
    sessions = nextPage.sessions;
    if (sessionId && loadedSessionId === sessionId) {
      laps = nextLaps;
      ensureSelectedLap(nextLaps);
    }
    if (!lapIdToReload || selectedLapId !== lapIdToReload || !nextLaps.some((lap) => lap.id === lapIdToReload)) {
      return;
    }
    referenceVersion += 1;
    invalidateSectionSummaryRequests();
    clearComparisonState();
    await loadComparisonForLap(lapIdToReload, referenceScope, selectedRange);
  }

  function setLapDeleting(lapId: string, deleting: boolean) {
    deletingLapIds = deleting
      ? Array.from(new Set([...deletingLapIds, lapId]))
      : deletingLapIds.filter((candidate) => candidate !== lapId);
  }

  async function handleDeleteLap(lapId: string) {
    if (deletingLapIds.includes(lapId)) return;
    const lap = laps.find((candidate) => candidate.id === lapId);
    const lapLabel = lap ? `${lap.session_label} lap ${lap.lap_number ?? '—'}` : 'lap';
    setLapDeleting(lapId, true);
    try {
      await deleteLap(lapId);
      invalidateLapContextCache(lapId);
      pushToast('success', `Deleted ${lapLabel}`);
      await refreshHistory();
    } catch (error) {
      pushToast('error', 'Unable to delete lap', false);
    } finally {
      setLapDeleting(lapId, false);
    }
  }

  async function recoverCurrentState() {
    const recoveryWorldMapStatusVersion = worldMapStatusVersion;
    const [status, captureStatus, recent, nextActiveSession, nextSessionPage, nextProfiles, nextWorldMapStatus] = await Promise.all([
      fetchStatus(),
      fetchCaptureStatus(),
      fetchRecentLiveSamples(RECENT_LIVE_SAMPLE_LIMIT),
      fetchActiveSession(),
      fetchSessionPage({ page: 1, pageSize: 100 }),
      fetchTrackProfiles(),
      fetchWorldMapStatus().catch(() => null)
    ]);
    if (disposed) return false;
    const nextLoadedSessionId = loadedSessionId ?? nextActiveSession?.id ?? nextSessionPage.sessions[0]?.id ?? null;
    const nextLaps = nextLoadedSessionId ? await fetchSessionLaps(nextLoadedSessionId) : [];
    if (disposed) return false;
    const recoveredCapture = {
      ...status.capture,
      ...captureStatus,
      listener: status.listener,
      settings: captureStatus.settings ?? status.settings
    };
    listener = status.listener;
    latestStatus = {
      listener: status.listener,
      settings: captureStatus.settings ?? status.settings,
      capture: recoveredCapture
    };
    if (!overlayTouchedByUser) {
      selectedOverlay = overlayForCaptureContext(preferredOverlayForCapture(recoveredCapture), recoveredCapture);
    }
    applyCaptureState(recoveredCapture);
    const shouldAutoSelectLap = !capture.recording.active;
    const nextDefaultLapId = shouldAutoSelectLap ? newestSelectableCompletedLapId(nextLaps) : null;
    const preloadedDefaultLap = !selectedLapId && nextDefaultLapId !== null;
    if (preloadedDefaultLap && nextDefaultLapId) {
      await loadLapContext(nextDefaultLapId, true, false).catch(() => {
        pushToast('error', 'Unable to load lap drilldown data', false);
      });
    }
    if (disposed) return false;
    activeSession = nextActiveSession;
    loadedSessionId = nextLoadedSessionId;
    laps = nextLaps;
    sessionPage = nextSessionPage;
    sessionFilters = { page: 1, pageSize: 100 };
    sessions = nextSessionPage.sessions;
    trackProfiles = nextProfiles;
    if (recoveryWorldMapStatusVersion === worldMapStatusVersion) {
      worldMapStatus = nextWorldMapStatus;
    }
    if (!liveFollowPaused && isRecordingActive(captureStatus)) {
      liveSessionId = recent.session_id;
      resetLiveSamples(raceLiveSamplesForCurrentTrace(recent.samples));
      liveCarInfo = recent.car ?? null;
    } else if (!isRecordingActive(captureStatus)) {
      liveSessionId = null;
      resetLiveSamples();
      liveCarInfo = null;
    }
    if (shouldAutoSelectLap && !preloadedDefaultLap) {
      ensureSelectedLap(nextLaps);
    }
    return true;
  }

  async function loadDiagnostics() {
    const requestId = ++diagnosticsRequestId;
    diagnosticsLoading = true;
    try {
      const nextDiagnostics = await fetchDiagnostics();
      if (disposed || requestId !== diagnosticsRequestId || !diagnosticsOpen) return;
      diagnosticsPayload = nextDiagnostics;
    } catch (error) {
      if (disposed || requestId !== diagnosticsRequestId || !diagnosticsOpen) return;
      pushToast('error', 'Unable to load diagnostics', false);
    } finally {
      if (!disposed && requestId === diagnosticsRequestId && diagnosticsOpen) {
        diagnosticsLoading = false;
      }
    }
  }

  async function handleRestartListener() {
    if (diagnosticsRestarting) return;
    diagnosticsRestarting = true;
    try {
      const restartedListener = await restartListener();
      if (disposed) return;
      listener = { ...listener, ...restartedListener };
      latestStatus = {
        ...latestStatus,
        listener,
        capture: { ...latestStatus.capture, listener }
      };
      pushToast('success', 'Listener restarted', false);
      if (diagnosticsOpen) {
        await loadDiagnostics();
      }
    } catch (error) {
      if (!disposed) {
        pushToast('error', 'Unable to restart listener', false);
      }
    } finally {
      if (!disposed) {
        diagnosticsRestarting = false;
      }
    }
  }

  async function handleDeleteAllTelemetry() {
    if (diagnosticsDeletingTelemetry) return;
    diagnosticsDeletingTelemetry = true;
    try {
      await deleteAllTelemetry();
      if (disposed) return;
      clearLapContextCache();
      clearLapContext();
      clearComparisonState();
      invalidateSectionSummaryRequests();
      loadedSessionId = null;
      activeSession = null;
      laps = [];
      liveSessionId = null;
      liveCarInfo = null;
      resetLiveSamples();
      statsSummary = null;
      await recoverCurrentState();
      if (diagnosticsOpen) {
        await loadDiagnostics();
      }
      if (activeUtilityModal === 'stats') {
        await loadStatsSummary();
      }
      pushToast('success', 'Deleted all recorded telemetry', false);
    } catch (error) {
      if (!disposed) {
        pushToast('error', 'Unable to delete telemetry', false);
      }
    } finally {
      if (!disposed) {
        diagnosticsDeletingTelemetry = false;
      }
    }
  }

  function openDiagnostics(eventOrOpener?: Event | HTMLElement) {
    if (eventOrOpener instanceof HTMLElement) {
      diagnosticsOpener = eventOrOpener;
    } else if (eventOrOpener?.currentTarget instanceof HTMLElement) {
      diagnosticsOpener = eventOrOpener.currentTarget;
    } else if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
      diagnosticsOpener = document.activeElement;
    }
    diagnosticsOpen = true;
    void loadDiagnostics();
  }

  function closeDiagnostics() {
    const opener = diagnosticsOpener;
    diagnosticsRequestId += 1;
    diagnosticsOpen = false;
    diagnosticsLoading = false;
    diagnosticsRestarting = false;
    diagnosticsDeletingTelemetry = false;
    void tick().then(() => {
      if (opener?.isConnected) {
        opener.focus({ preventScroll: true });
      }
      if (diagnosticsOpener === opener) {
        diagnosticsOpener = null;
      }
    });
  }

  function openShortcutHelp(eventOrOpener?: Event | HTMLElement) {
    if (eventOrOpener instanceof HTMLElement) {
      shortcutHelpOpener = eventOrOpener;
    } else if (eventOrOpener?.currentTarget instanceof HTMLElement) {
      shortcutHelpOpener = eventOrOpener.currentTarget;
    } else if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
      shortcutHelpOpener = document.activeElement;
    }
    shortcutHelpOpen = true;
  }

  function closeShortcutHelp() {
    const opener = shortcutHelpOpener;
    shortcutHelpOpen = false;
    void tick().then(() => {
      if (opener?.isConnected) {
        opener.focus({ preventScroll: true });
      }
      if (shortcutHelpOpener === opener) {
        shortcutHelpOpener = null;
      }
    });
  }

  function handleOverlayChange(overlay: OverlayId) {
    if (!overlayAllowedForCurrentContext(overlay)) return;
    overlayTouchedByUser = true;
    selectedOverlay = overlay;
  }

  function cycleOverlay() {
    handleOverlayChange(nextAvailableOverlayFrom(selectedOverlay));
  }

  function clearSelectionAndPopover() {
    if (shortcutHelpOpen) {
      closeShortcutHelp();
      return;
    }
    if (issuePopoverOpen) {
      closeIssuePopover();
    }
    if (selectedRange) {
      showReviewedLapBoundsOnCanvas = false;
      scheduleLapSummaryLoad(null);
    }
  }

  function toggleLiveFollow() {
    liveFollowPaused = !liveFollowPaused;
    if (!liveFollowPaused && isRecordingActive(capture) && liveSamples.length > 0) {
      showLiveRouteView();
    }
  }

  function handleMenuToggle(event: CustomEvent<{ expanded: boolean }>) {
    menuExpanded = event.detail.expanded;
  }

  function closeUtilityModal() {
    const closingModal = activeUtilityModal;
    activeUtilityModal = null;
    if (closingModal === 'export' && !exportJobs.some(isExportJobActive)) {
      clearExportJobPollTimer();
    }
  }

  function openUtilityModal(modal: UtilityModal) {
    activeUtilityModal = modal;
    if (modal === 'import') {
      void refreshImportJobs();
    } else if (modal === 'export') {
      void loadExportDefaults();
      void refreshExportJobs();
    }
  }

  async function focusFloatingCaptureControls() {
    await tick();
    const target = floatingCaptureControlsElement?.querySelector<HTMLElement>('button:not([disabled])');
    target?.focus({ preventScroll: true });
  }

  async function focusSummaryToggleButton() {
    await tick();
    summaryToggleContainerElement?.querySelector<HTMLElement>('[aria-label="Show section summary"], [aria-label="Hide section summary"]')?.focus({ preventScroll: true });
  }

  async function focusCarToggleButton() {
    await tick();
    summaryToggleContainerElement?.querySelector<HTMLElement>('[aria-label="Show car info"], [aria-label="Hide car info"]')?.focus({ preventScroll: true });
  }

  async function hideSummaryCard({ restoreFocus = false } = {}) {
    summaryCardVisible = false;
    if (restoreFocus) {
      await focusSummaryToggleButton();
    }
  }

  function toggleSummaryCard() {
    if (summaryCardVisible) {
      void hideSummaryCard({ restoreFocus: true });
      return;
    }
    summaryCardVisible = true;
  }

  async function hideCarCard({ restoreFocus = false } = {}) {
    carCardVisible = false;
    if (restoreFocus) {
      await focusCarToggleButton();
    }
  }

  function toggleCarCard() {
    if (!displayedCarInfo) return;
    if (carCardVisible) {
      void hideCarCard({ restoreFocus: true });
      return;
    }
    carCardVisible = true;
  }

  function handleCarCardMove(x: number, y: number) {
    const clamped = clampCarCardPosition(x, y);
    carCardX = clamped.x;
    carCardY = clamped.y;
  }

  async function toggleMapOverlay() {
    if (mapToggleBusy) return;
    if (!hasReadyWorldMapCache || !worldMapStatus) {
      mapSetupPanelOpen = true;
      return;
    }

    mapToggleBusy = true;
    try {
      const nextStatus = await updateWorldMapSettings({
        fh6_media_root: worldMapStatus.settings.fh6_media_root,
        world_map_enabled: !mapOverlayEnabled,
        world_map_season: worldMapStatus.settings.world_map_season
      });
      worldMapStatusVersion += 1;
      worldMapStatus = nextStatus;
      pushToast('success', nextStatus.settings.world_map_enabled ? 'Map overlay enabled' : 'Map overlay disabled');
    } catch (error) {
      pushToast('error', 'Unable to update map overlay setting', false);
    } finally {
      mapToggleBusy = false;
    }
  }

  function handleMapSetupReady(event: CustomEvent<{ status: WorldMapStatus }>) {
    worldMapStatusVersion += 1;
    worldMapStatus = event.detail.status;
    mapSetupPanelOpen = false;
  }

  function handleSummaryCardMove(x: number, y: number) {
    const clamped = clampSummaryCardPosition(x, y);
    summaryCardX = clamped.x;
    summaryCardY = clamped.y;
  }

  function clearFitToScreenResumeTimer() {
    if (fitToScreenResumeTimer === null) return;
    window.clearTimeout(fitToScreenResumeTimer);
    fitToScreenResumeTimer = null;
  }

  function resumeFitToScreenAfterInactivity() {
    fitToScreenResumeTimer = null;
    if (!fitToScreenEnabled) return;
    fitToScreenSuspended = false;
    sendZoomCommand('fit');
  }

  function suspendFitToScreenTemporarily() {
    if (!fitToScreenEnabled) return;
    fitToScreenSuspended = true;
    clearFitToScreenResumeTimer();
    fitToScreenResumeTimer = window.setTimeout(resumeFitToScreenAfterInactivity, FIT_TO_SCREEN_RESUME_DELAY_MS);
  }

  function toggleFitToScreen() {
    if (fitToScreenEnabled) {
      fitToScreenEnabled = false;
      fitToScreenSuspended = false;
      clearFitToScreenResumeTimer();
      return;
    }

    fitToScreenEnabled = true;
    fitToScreenSuspended = false;
    clearFitToScreenResumeTimer();
    sendZoomCommand('fit');
  }

  function sendZoomCommand(command: ZoomCommand) {
    if (command !== 'fit') {
      suspendFitToScreenTemporarily();
    }
    zoomCommand = command;
    zoomCommandId += 1;
  }

  function resetFloatingPanelsAndLayout() {
    activeUtilityModal = null;
    historyDrawerOpen = true;
    summaryCardVisible = true;
    summaryCardX = 0;
    summaryCardY = 0;
    carCardVisible = true;
    carCardExpanded = false;
    carCardX = 0;
    carCardY = 0;
    issuePopoverX = 16;
    issuePopoverY = 16;
    issuePopoverDragged = false;
    sendZoomCommand('fit');
    pushToast('success', 'Layout reset');
  }

  function applyVisualiserSettings(
    settings: VisualiserSettings,
    options: { applyPreferredOverlay?: boolean } = {}
  ) {
    const normalizedSettings: VisualiserSettings = {
      ...latestStatus.settings,
      ...settings,
      unit_system: normaliseUnitSystem(settings.unit_system ?? latestStatus.settings.unit_system),
      preferred_overlay: normaliseOverlay(settings.preferred_overlay ?? latestStatus.settings.preferred_overlay)
    };
    capture = { ...capture, settings: normalizedSettings };
    latestStatus = {
      ...latestStatus,
      settings: normalizedSettings,
      capture: { ...latestStatus.capture, ...capture, settings: normalizedSettings }
    };
    if (options.applyPreferredOverlay) {
      selectedOverlay = overlayForCaptureContext(normaliseOverlay(normalizedSettings.preferred_overlay));
      overlayTouchedByUser = true;
    } else if (!overlayTouchedByUser) {
      selectedOverlay = overlayForCaptureContext(normaliseOverlay(normalizedSettings.preferred_overlay));
    }
  }

  function handleSettingsChange(event: CustomEvent<{ settings: VisualiserSettings; applyPreferredOverlay?: boolean }>) {
    applyVisualiserSettings(event.detail.settings, { applyPreferredOverlay: event.detail.applyPreferredOverlay === true });
    pushToast('success', 'Settings saved');
  }

  function handleSettingsError(event: CustomEvent<{ message: string }>) {
    pushToast('error', event.detail.message, false);
  }

  function handleWorldMapChange(event: CustomEvent<{ status: WorldMapStatus; message: string }>) {
    worldMapStatusVersion += 1;
    worldMapStatus = event.detail.status;
    if (event.detail.message) {
      const level = event.detail.status.status === 'ready' || event.detail.message.endsWith('saved') ? 'success' : 'warning';
      pushToast(level, event.detail.message, false);
    }
  }

  function handleWorldMapError(event: CustomEvent<{ message: string }>) {
    pushToast('error', event.detail.message, false);
  }

  function openHistoryDrawer() {
    historyDrawerOpen = true;
    pushToast('info', 'Session laps drawer opened.');
  }

  function focusHistoryMenuButton() {
    document
      .querySelector<HTMLElement>('.slide-out-menu [aria-label="Session browser"]')
      ?.focus({ preventScroll: true });
  }

  async function closeHistoryDrawer() {
    historyDrawerOpen = false;
    await tick();
    focusHistoryMenuButton();
  }

  async function handleStartSession() {
    const session = await startSession();
    activeSession = session;
    loadedSessionId = session.id;
    laps = [];
    clearLapContext();
    await refreshSessionPage({ page: 1, pageSize: 100 });
    pushToast('success', `${session.label} started`);
  }

  async function handleOpenSessionFromBrowser(event: CustomEvent<{ sessionId: string }>) {
    const loadingScope = beginCanvasLoading('Activating session…', 0.08);
    try {
      const session = await activateSession(event.detail.sessionId);
      activeSession = session;
      closeUtilityModal();
      updateCanvasLoading(loadingScope, 'Loading session laps…', 0.22);
      await loadSession(session.id, loadingScope);
      updateCanvasLoading(loadingScope, 'Refreshing session list…', 0.92);
      await refreshSessionPage(sessionFilters);
    } finally {
      finishCanvasLoading(loadingScope);
    }
  }

  async function handleSessionBrowserFilterChange(event: CustomEvent<{ filters: SessionFilters }>) {
    await refreshSessionPage(event.detail.filters);
  }

  async function handleSessionBrowserPageChange(event: CustomEvent<{ page: number }>) {
    await refreshSessionPage({ ...sessionFilters, page: event.detail.page, pageSize: 100 });
  }

  async function handleRenameSession(event: CustomEvent<{ sessionId: string; label: string }>) {
    try {
      const session = await renameSession(event.detail.sessionId, event.detail.label);
      sessionPage = {
        ...sessionPage,
        sessions: sessionPage.sessions.map((candidate) => (candidate.id === session.id ? session : candidate))
      };
      sessions = sessions.map((candidate) => (candidate.id === session.id ? session : candidate));
      if (activeSession?.id === session.id) {
        activeSession = session;
      }
      pushToast('success', 'Session renamed');
    } catch (error) {
      pushToast('error', 'Unable to rename session', false);
    }
  }

  async function handleDeleteSession(event: CustomEvent<{ sessionId: string }>) {
    const sessionId = event.detail.sessionId;
    try {
      await deleteSession(sessionId);
      invalidateSessionLapContextCache(sessionId);
      if (loadedSessionId === sessionId) {
        loadedSessionId = null;
        laps = [];
        clearLapContext();
      }
      if (activeSession?.id === sessionId) {
        activeSession = await fetchActiveSession();
      }
      await refreshSessionPage(sessionFilters);
      pushToast('success', 'Session deleted');
    } catch (error) {
      pushToast('error', 'Unable to delete session', false);
    }
  }

  function handleMenuAction(event: CustomEvent<{ action: MenuAction; opener: HTMLElement }>) {
    menuExpanded = false;

    switch (event.detail.action) {
      case 'new-session':
        handleStartSession().catch(() => pushToast('error', 'Unable to start session', false));
        break;
      case 'import-telemetry':
        openUtilityModal('import');
        break;
      case 'export-telemetry':
        openUtilityModal('export');
        break;
      case 'session-browser':
        openUtilityModal('session-browser');
        void refreshSessionPage({ page: 1, pageSize: 100 });
        break;
      case 'stats':
        openUtilityModal('stats');
        void loadStatsSummary();
        break;
      case 'diagnostics':
        openDiagnostics(event.detail.opener);
        break;
      case 'shortcuts':
        openShortcutHelp(event.detail.opener);
        break;
      case 'settings':
        openUtilityModal('settings');
        break;
      case 'about':
        openUtilityModal('about');
        break;
    }
  }

  function handleWindowKeydown(event: KeyboardEvent) {
    const action = actionForKey(event);
    if (!action) return;
    const modalOpen = activeUtilityModal !== null || diagnosticsOpen || shortcutHelpOpen;
    if (modalOpen && !(shortcutHelpOpen && action === 'clearSelection')) return;
    if (action === 'toggleLiveFollow' && event.target instanceof HTMLButtonElement) return;

    event.preventDefault();
    switch (action) {
      case 'cycleOverlay':
        cycleOverlay();
        break;
      case 'clearSelection':
        clearSelectionAndPopover();
        break;
      case 'toggleLiveFollow':
        toggleLiveFollow();
        break;
    }
  }

  async function recoverAndConnect(initial = false) {
    try {
      const recovered = await recoverCurrentState();
      if (!recovered || disposed) return;
      if (initial) {
        pushToast('info', 'Tracker ready');
      } else {
        clearDisconnectedToast();
      }
      connectEvents();
    } catch (error) {
      if (disposed) return;
      if (initial) {
        pushToast('error', 'Unable to load tracker status', true);
      } else {
        showDisconnectedToast();
        scheduleReconnect();
      }
    }
  }

  function scheduleReconnect() {
    if (disposed || reconnectTimer !== null) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      if (disposed) return;
      void recoverAndConnect(false);
    }, RECONNECT_DELAY_MS);
  }

  async function handleCaptureModeChange(mode: CaptureMode) {
    captureBusy = true;
    try {
      applyCaptureState(await setCaptureMode(mode));
      await refreshHistory();
    } catch (error) {
      pushToast('error', 'Unable to update capture mode', false);
    } finally {
      captureBusy = false;
    }
  }

  async function handleStartCapture() {
    if (capture.mode !== 'manual' || capture.recording.active) return;
    captureBusy = true;
    try {
      applyCaptureState(await startCapture());
    } catch (error) {
      pushToast('error', 'Unable to start manual capture', false);
    } finally {
      captureBusy = false;
    }
  }

  async function handleStopCapture() {
    if (capture.mode !== 'manual' || !capture.recording.active) return;
    captureBusy = true;
    try {
      applyCaptureState(await stopCapture());
      await refreshHistory();
    } catch (error) {
      pushToast('error', 'Unable to stop manual capture', false);
    } finally {
      captureBusy = false;
    }
  }

  function handleTimelineRangeChange(range: SequenceRange) {
    showReviewedLapBoundsOnCanvas = false;
    scheduleLapSummaryLoad(range);
  }

  async function openTrackAssignmentPicker(lapId: string) {
    trackAssignmentLapId = lapId;
    trackAssignmentCandidates = [];
    trackAssignmentError = null;
    trackAssignmentBusy = true;
    const requestId = ++trackAssignmentRequestId;
    try {
      const [response, nextProfiles] = await Promise.all([matchLapTrack(lapId), fetchTrackProfiles()]);
      if (disposed || requestId !== trackAssignmentRequestId || trackAssignmentLapId !== lapId) return;
      trackProfiles = nextProfiles;
      if (trackMatchResponseAssigned(response)) {
        invalidateLapContextCache(lapId);
        closeTrackAssignmentPicker();
        await refreshTrackProfilesHistoryAndComparison();
        return;
      }
      trackAssignmentCandidates = response.candidates ?? [];
    } catch (error) {
      if (disposed || requestId !== trackAssignmentRequestId || trackAssignmentLapId !== lapId) return;
      trackAssignmentError = 'Unable to load suggested tracks';
      pushToast('error', 'Unable to load suggested tracks', false);
    } finally {
      if (!disposed && requestId === trackAssignmentRequestId && trackAssignmentLapId === lapId) {
        trackAssignmentBusy = false;
      }
    }
  }

  function closeTrackAssignmentPicker() {
    trackAssignmentRequestId += 1;
    trackAssignmentLapId = null;
    trackAssignmentCandidates = [];
    trackAssignmentError = null;
    trackAssignmentBusy = false;
  }

  async function handleAssignTrackProfile(event: CustomEvent<{ profileId: string; sessionId: string; lapId: string }>) {
    trackProfileBusy = true;
    try {
      await assignTrackProfile(event.detail.profileId, {
        sessionId: event.detail.sessionId,
        lapId: event.detail.lapId
      });
      invalidateLapContextCache(event.detail.lapId);
      pushToast('success', 'Track profile assigned');
      await refreshTrackProfilesHistoryAndComparison();
      if (trackAssignmentLapId === event.detail.lapId) {
        closeTrackAssignmentPicker();
      }
    } catch (error) {
      pushToast('error', 'Unable to assign track profile', false);
    } finally {
      trackProfileBusy = false;
    }
  }

  function moveIssuePopoverNearSelection(canvasX: number | null | undefined, canvasY: number | null | undefined) {
    if (issuePopoverDragged || canvasX === null || canvasX === undefined || canvasY === null || canvasY === undefined) return;
    issuePopoverX = Math.round(canvasX + 14);
    issuePopoverY = Math.round(canvasY + 14);
    void tick().then(() => {
      if (!issuePopoverOpen || issuePopoverDragged) return;
      const clamped = clampIssuePopoverPosition(issuePopoverX, issuePopoverY);
      issuePopoverX = clamped.x;
      issuePopoverY = clamped.y;
    });
  }

  function handleIssuePopoverMove(x: number, y: number) {
    issuePopoverDragged = true;
    const clamped = clampIssuePopoverPosition(x, y);
    issuePopoverX = clamped.x;
    issuePopoverY = clamped.y;
  }

  function issuePopoverItemsFromInteraction(detail: IssueInteractionDetail): IssuePopoverItem[] {
    return detail.markers.map((marker) => {
      const anchorSequence = marker.anchor_sequence ?? marker.start_sequence;
      const sample = displayedSamples.find((candidate) => candidate.sequence === anchorSequence) ?? detail.sample ?? null;
      return {
        marker,
        sample,
        elapsedMs: sample ? dashboardTimeline.points.find((point) => point.sample.sequence === sample.sequence)?.elapsedMs ?? null : null
      };
    });
  }

  function openIssuePopoverFromInteraction(detail: IssueInteractionDetail, pinned: boolean) {
    if (issuePopoverPinned && !pinned) return;
    issuePopoverDragged = pinned ? false : issuePopoverDragged;
    issuePopoverPinned = pinned;
    issuePopoverItems = issuePopoverItemsFromInteraction(detail);
    issuePopoverOpen = issuePopoverItems.length > 0;
    moveIssuePopoverNearSelection(detail.canvasX, detail.canvasY);
  }

  function handleIssueHover(event: CustomEvent<IssueInteractionDetail>) {
    openIssuePopoverFromInteraction(event.detail, false);
  }

  function handleIssueHoverClear() {
    if (issuePopoverPinned) return;
    closeIssuePopover();
  }

  function handleIssueSelect(event: CustomEvent<IssueInteractionDetail>) {
    openIssuePopoverFromInteraction(event.detail, true);
  }

  function handlePointSelect(event: CustomEvent<{ sample: LiveSample; canvasX?: number; canvasY?: number }>) {
    if (
      !selectedLapId ||
      !selectedLap ||
      !isSelectableCompletedLap(selectedLap) ||
      dashboardSource !== 'lap' ||
      dashboardTimeline.points.length === 0
    ) return;
    const point = dashboardTimeline.points.find((candidate) => candidate.sample.sequence === event.detail.sample.sequence);
    if (!point) {
      pushToast('error', 'Unable to open dashboard at that point');
      return;
    }

    closeIssuePopover();
    dashboardPlaybackPlaying = false;
    dashboardPlaybackLastFrameMs = null;
    dashboardPlaybackTimeMs = point.timeMs;
    canvasMode = 'dashboard';
  }

  function connectEvents() {
    closeEvents();
    if (disposed) return;
    const source = new EventSource('/events');
    eventSource = source;
    malformedEventToastShown = false;
    source.addEventListener('status', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data) return;
      const nextListener = listenerStatusFromEvent(data);
      if (isInitialSsePlaceholderStatus(nextListener)) return;
      listener = { ...listener, ...nextListener };
      latestStatus = { ...latestStatus, listener, capture: { ...latestStatus.capture, listener } };
    });
    source.addEventListener('capture', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data) return;
      applyCaptureState(data as unknown as CaptureStatus);
    });
    source.addEventListener('live_sample', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data || !('sample' in data)) return;
      if (liveFollowPaused) return;
      if (!isRecordingActive(capture)) return;
      const sample = data.sample as LiveSample;
      if (!isRaceLiveSample(sample)) return;
      showLiveRouteView();
      appendLiveSample(sample);
      if ('car' in data) {
        liveCarInfo = data.car ? (data.car as CarInfo) : null;
      }
    });
    source.addEventListener('live_reset', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data) return;
      resetLiveSamples();
      liveCarInfo = null;
      if (typeof data.session_id === 'string') {
        liveSessionId = data.session_id;
      }
      if (!selectedLapId) {
        closeIssuePopover();
      }
    });
    source.addEventListener('lap_finalized', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data) return;
      if (data.boundary_confidence === 'uncertain') {
        pushToast('warning', `Lap boundary uncertain: ${String(data.uncertainty ?? 'unknown')}`);
      }
      if (typeof data.lap_id === 'string') {
        invalidateLapContextCache(data.lap_id);
      }
      resetLiveSamplesForLapBoundary();
      const sessionId = eventSessionId(data);
      invalidateSessionComparisonCache(sessionId);
      refreshSelectedComparisonForReferenceEvent(sessionId);
      if (eventTrackMatchAssigned(data)) {
        void refreshTrackProfilesList();
      }
      refreshHistoryForSessionEvent(sessionId);
    });
    source.addEventListener('lap_track_matched', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data) return;
      handleAutomaticTrackAssignmentEvent(data);
    });
    source.addEventListener('auto_lap_discarded', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      const lapId = typeof data?.lap_id === 'string' ? data.lap_id : null;
      if (!lapId) return;
      invalidateLapContextCache(lapId);
      const sessionId = typeof data?.session_id === 'string' ? data.session_id : null;
      invalidateSessionComparisonCache(sessionId);
      refreshSelectedComparisonForReferenceEvent(sessionId);
      if (!sessionId || loadedSessionId === sessionId || laps.some((lap) => lap.id === lapId)) {
        removeLapFromLoadedHistory(lapId);
      }
      if (!sessionId || activeSession?.id === sessionId) {
        void refreshActiveSession();
      }
      void refreshSessionPage(sessionFilters);
    });
    source.addEventListener('session_started', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      const eventSession = isRecord(data?.session) ? (data.session as unknown as SessionSummary) : null;
      if (eventSession) {
        activeSession = eventSession;
      }
      void refreshActiveSession().then(() => {
        const sessionToLoad = activeSession?.id ?? eventSession?.id ?? null;
        if (sessionToLoad && (!loadedSessionId || !liveFollowPaused)) {
          void loadSession(sessionToLoad);
        }
      });
      void refreshSessionPage(sessionFilters);
    });
    source.addEventListener('session_updated', () => {
      if (eventSource !== source) return;
      void refreshSessionPage(sessionFilters);
    });
    source.addEventListener('session_deleted', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      const sessionId = typeof data?.session_id === 'string' ? data.session_id : null;
      if (sessionId && loadedSessionId === sessionId) {
        invalidateSessionLapContextCache(sessionId);
        loadedSessionId = null;
        laps = [];
        clearLapContext();
      }
      void refreshActiveSession();
      void refreshSessionPage(sessionFilters);
    });
    source.addEventListener('session_finalized', () => {
      if (eventSource !== source) return;
      void refreshActiveSession();
      void refreshSessionPage(sessionFilters);
    });
    source.addEventListener('toast', (event) => {
      if (eventSource !== source) return;
      const data = parseSseJson(event as MessageEvent);
      if (!data || typeof data.message !== 'string' || typeof data.level !== 'string') return;
      pushToast(data.level as ToastMessage['level'], data.message, Boolean(data.sticky));
    });
    source.onerror = () => {
      if (eventSource !== source) return;
      showDisconnectedToast();
      closeEvents();
      scheduleReconnect();
    };
  }

  $: selectedLap = laps.find((lap) => lap.id === selectedLapId) ?? null;
  $: selectedSession = selectedLap
    ? sessions.find((session) => session.id === selectedLap?.session_id) ?? null
    : loadedSessionId
      ? sessions.find((session) => session.id === loadedSessionId) ?? (activeSession?.id === loadedSessionId ? activeSession : null)
      : null;
  $: displayedSamples = selectedLapId ? lapSamples : isRecordingActive(capture) ? liveSamples : [];
  $: issuesUnavailable = selectedLapId
    ? !selectedLap || !isSelectableCompletedLap(selectedLap)
    : isRecordingActive(capture);
  $: disabledOverlays = issuesUnavailable ? ['issues'] : [];
  $: disabledOverlayReasons = issuesUnavailable
    ? { issues: ISSUES_UNAVAILABLE_DURING_RECORDING_MESSAGE }
    : {};
  $: displayedCarInfo = selectedLapId ? selectedCarInfo : isRecordingActive(capture) ? liveCarInfo : null;
  $: dashboardSource = selectedLapId ? 'lap' : 'live';
  $: canvasLoadingProgressPercent = canvasLoading?.progress === null || canvasLoading?.progress === undefined ? null : Math.round(canvasLoading.progress * 100);
  $: shouldBuildDashboardTimeline = selectedLapId !== null || canvasMode === 'dashboard';
  $: dashboardTimeline = shouldBuildDashboardTimeline ? buildPlaybackTimeline(displayedSamples) : EMPTY_DASHBOARD_TIMELINE;
  $: dashboardDurationMs = dashboardTimeline.durationMs;
  $: dashboardTotalElapsedMs = dashboardTimeline.points[dashboardTimeline.points.length - 1]?.elapsedMs ?? dashboardDurationMs;
  $: if (dashboardPlaybackTimeMs > dashboardDurationMs) {
    dashboardPlaybackTimeMs = dashboardDurationMs;
  }
  $: dashboardPlaybackPoint = selectedLapId ? playbackPointInTimelineAtTime(dashboardTimeline, dashboardPlaybackTimeMs) : null;
  $: dashboardCurrentSample = selectedLapId ? dashboardPlaybackPoint?.sample ?? displayedSamples[0] ?? null : displayedSamples[displayedSamples.length - 1] ?? null;
  $: dashboardCurrentIndex = selectedLapId ? dashboardPlaybackPoint?.index ?? (displayedSamples.length > 0 ? 0 : -1) : displayedSamples.length - 1;
  $: dashboardElapsedMs = selectedLapId ? dashboardPlaybackPoint?.elapsedMs ?? 0 : 0;
  $: dashboardProgress = dashboardDurationMs > 0 ? dashboardPlaybackTimeMs / dashboardDurationMs : 0;
  $: if (selectedLapId !== previousDashboardLapId) {
    previousDashboardLapId = selectedLapId;
    dashboardPlaybackPlaying = false;
    dashboardPlaybackTimeMs = 0;
    stopDashboardPlaybackLoop();
  }
  $: if (canvasMode !== 'dashboard' && dashboardPlaybackPlaying) {
    dashboardPlaybackPlaying = false;
  }
  $: {
    dashboardPlaybackPlaying;
    canvasMode;
    selectedLapId;
    syncDashboardPlaybackLoop();
  }
  $: carCardShown = carCardVisible && displayedCarInfo !== null;
  $: canvasSelectedRange = selectedRange ?? (showReviewedLapBoundsOnCanvas ? fullLapBounds : null);
  $: selectedLapTrackUnknown = !!selectedLap && !hasKnownTrack(selectedLap);
  $: trackAssignmentLap = trackAssignmentLapId ? laps.find((lap) => lap.id === trackAssignmentLapId) ?? null : null;
  $: selectedTrackProfileId = selectedLap?.track_profile_id ?? null;
  $: profileTrackAssets = selectedTrackProfileId ? trackAssets.filter((asset) => asset.track_profile_id === selectedTrackProfileId) : [];
  $: if (selectedTrackProfileId !== currentTrackAssetProfileId) {
    currentTrackAssetProfileId = selectedTrackProfileId;
    void loadTrackAssetsForProfile(selectedTrackProfileId);
  }
  $: if (profileTrackAssets.length === 0) {
    selectedTrackAssetId = null;
  } else if (!selectedTrackAssetId || !profileTrackAssets.some((asset) => asset.id === selectedTrackAssetId)) {
    selectedTrackAssetId = profileTrackAssets[0].id;
  }
  $: selectedTrackAsset = profileTrackAssets.find((asset) => asset.id === selectedTrackAssetId) ?? null;
  $: fitToScreenActive = fitToScreenEnabled && !fitToScreenSuspended;
  $: fitToScreenButtonLabel = fitToScreenEnabled ? 'Disable fit to screen' : 'Enable fit to screen';
  $: fitToScreenButtonTitle = fitToScreenSuspended
    ? 'Fit to screen paused; resumes after 10 seconds of no pan or zoom'
    : fitToScreenEnabled
      ? 'Fit to screen is on'
      : 'Keep telemetry tracing framed and visible';

  onMount(() => {
    disposed = false;
    window.addEventListener('keydown', handleWindowKeydown);
    void recoverAndConnect(true);

    return () => {
      disposed = true;
      window.removeEventListener('keydown', handleWindowKeydown);
      diagnosticsRequestId += 1;
      clearReconnectTimer();
      clearSummaryDebounceTimer();
      clearImportJobPollTimer();
      clearExportJobPollTimer();
      clearFitToScreenResumeTimer();
      stopDashboardPlaybackLoop();
      closeEvents();
    };
  });
</script>

<main class="dashboard-shell" data-testid="dashboard-shell">
  <ToastStack {toasts} dismiss={dismissToast} />
  <SlideOutMenu expanded={menuExpanded} on:toggle={handleMenuToggle} on:action={handleMenuAction} />
  <section class="dashboard-main">
    <section
      bind:this={visualisationStageElement}
      class="visualisation-stage"
      data-testid="visualisation-stage"
      data-menu-overlay={menuExpanded ? 'true' : 'false'}
      aria-label="Telemetry visualisation stage"
    >
      <h1 class="floating-stage-title">Forza Telemetry Tracker</h1>
      <div class="floating-overlays floating-top-center">
        <CanvasModeToggle mode={canvasMode} on:change={(event) => handleCanvasModeChange(event.detail.mode)} />
        {#if canvasMode === 'dashboard'}
          <DashboardWidgetVisibilityPopover
            enabledWidgets={dashboardWidgetVisibility}
            on:toggle={(event) => toggleDashboardWidget(event.detail.widgetId)}
            on:showall={showAllDashboardWidgets}
          />
        {/if}
      </div>
      {#if canvasMode === 'route'}
        <div class="floating-overlays floating-top-left">
          <OverlayToolbar
            selected={selectedOverlay}
            {disabledOverlays}
            disabledReasons={disabledOverlayReasons}
            on:change={(event) => handleOverlayChange(event.detail.overlay)}
          />
        </div>
      {/if}
      <div class="floating-overlays floating-top-right">
        <LiveFollowButton paused={liveFollowPaused} on:toggle={toggleLiveFollow} />
        <FloatingCaptureControls
          {capture}
          disabled={captureBusy}
          bind:controlsElement={floatingCaptureControlsElement}
          on:modechange={(event) => handleCaptureModeChange(event.detail.mode)}
          on:start={handleStartCapture}
          on:stop={handleStopCapture}
        />
      </div>
      {#if canvasMode === 'route'}
        {#if mapSetupPanelOpen}
          <WorldMapSetupPanel
            status={worldMapStatus}
            on:close={() => (mapSetupPanelOpen = false)}
            on:ready={handleMapSetupReady}
            on:worldmapchange={handleWorldMapChange}
            on:worldmaperror={handleWorldMapError}
          />
        {/if}
        <div bind:this={summaryToggleContainerElement} class="floating-overlays floating-bottom-right">
          <IconButton
            icon="map"
            label={mapToggleLabel}
            title={mapToggleTitle}
            pressed={mapOverlayEnabled}
            disabled={mapToggleBusy}
            onClick={toggleMapOverlay}
          />
          <IconButton
            icon="summary"
            label={summaryCardVisible ? 'Hide section summary' : 'Show section summary'}
            title={summaryCardVisible ? 'Hide section summary' : 'Show section summary'}
            pressed={summaryCardVisible}
            onClick={toggleSummaryCard}
          />
          <IconButton
            icon="car"
            label={carCardShown ? 'Hide car info' : 'Show car info'}
            title={carCardShown ? 'Hide car info' : 'Show car info'}
            pressed={carCardShown}
            disabled={!displayedCarInfo}
            onClick={toggleCarCard}
          />
          <IconButton icon="zoomIn" label="Zoom in" title="Zoom in" onClick={() => sendZoomCommand('in')} />
          <IconButton icon="zoomOut" label="Zoom out" title="Zoom out" onClick={() => sendZoomCommand('out')} />
          <IconButton
            icon="fit"
            label={fitToScreenButtonLabel}
            title={fitToScreenButtonTitle}
            pressed={fitToScreenEnabled}
            onClick={toggleFitToScreen}
          />
        </div>
      {/if}
      {#if canvasMode === 'route' && summaryCardVisible}
        <FloatingSectionSummary
          summary={selectedLapSummary}
          deltaSummary={selectedDeltaSummary}
          {selectedLap}
          {selectedRange}
          unitSystem={summaryUnitSystem}
          {referenceLap}
          x={summaryCardX}
          y={summaryCardY}
          bind:cardElement={summaryCardElement}
          on:close={() => hideSummaryCard({ restoreFocus: true })}
          on:move={(event) => handleSummaryCardMove(event.detail.x, event.detail.y)}
          on:trackchange={(event) => openTrackAssignmentPicker(event.detail.lapId)}
        />
      {/if}
      {#if canvasMode === 'route' && carCardShown && displayedCarInfo}
        <FloatingCarInfo
          car={displayedCarInfo}
          x={carCardX}
          y={carCardY}
          expanded={carCardExpanded}
          bind:cardElement={carCardElement}
          on:close={() => hideCarCard({ restoreFocus: true })}
          on:move={(event) => handleCarCardMove(event.detail.x, event.detail.y)}
          on:expandedchange={(event) => (carCardExpanded = event.detail.expanded)}
        />
      {/if}
      <div class="floating-overlays floating-review-timeline">
        {#if canvasMode === 'route'}
          <ReviewTimeline
            bounds={selectedLapId ? fullLapBounds : null}
            {selectedRange}
            disabled={!selectedLapId}
            message={capture.recording.active && !selectedLapId ? 'Recording… select a saved lap to review its timeline.' : 'Timeline available after a saved lap or session is selected.'}
            on:rangechange={(event) => handleTimelineRangeChange(event.detail.range)}
          />
        {:else}
          <DashboardPlaybackBar
            source={dashboardSource}
            samples={displayedSamples}
            currentSample={dashboardCurrentSample}
            currentIndex={dashboardCurrentIndex}
            currentTimeMs={dashboardPlaybackTimeMs}
            durationMs={dashboardDurationMs}
            currentElapsedMs={dashboardElapsedMs}
            durationElapsedMs={dashboardTotalElapsedMs}
            progress={dashboardProgress}
            playing={dashboardPlaybackPlaying}
            on:play={handleDashboardPlay}
            on:pause={handleDashboardPause}
            on:scrub={(event) => handleDashboardScrub(event.detail.timeMs)}
          />
        {/if}
      </div>
      <div bind:this={canvasWrapElement} class="canvas-wrap">
        {#if canvasMode === 'dashboard'}
          <TelemetryDashboard
            samples={displayedSamples}
            currentSample={dashboardCurrentSample}
            carInfo={displayedCarInfo}
            unitSystem={summaryUnitSystem}
            enabledWidgets={dashboardWidgetVisibility}
            on:showall={showAllDashboardWidgets}
          />
        {:else}
          <TelemetryCanvas
            samples={displayedSamples}
            ghostSamples={selectedLapId ? ghostSamples : []}
            overlay={selectedOverlay}
            {markers}
            selectedRange={canvasSelectedRange}
            trackAsset={selectedLapId ? selectedTrackAsset : null}
            worldMapTileSet={activeWorldMapTileSet}
            autoFit={fitToScreenActive}
            {zoomCommand}
            {zoomCommandId}
            incremental={isRecordingActive(capture) && !selectedLapId}
            sampleVersion={selectedLapId ? 0 : liveSampleVersion}
            lapBoundaryConfidence={selectedLap?.boundary_confidence ?? null}
            on:pointselect={handlePointSelect}
            on:issuehover={handleIssueHover}
            on:issuehoverclear={handleIssueHoverClear}
            on:issueselect={handleIssueSelect}
            on:viewportinteraction={suspendFitToScreenTemporarily}
          />
          {#if canvasLoading}
            <div class="canvas-loading-overlay" role="status" aria-live="polite" aria-label="Route visualiser loading">
              <div class="canvas-loading-panel">
                {#if canvasLoadingProgressPercent !== null}
                  <div
                    class="canvas-loading-progress"
                    role="progressbar"
                    aria-label="Route visualiser loading progress"
                    aria-valuemin="0"
                    aria-valuemax="100"
                    aria-valuenow={canvasLoadingProgressPercent}
                  >
                    <span style={`width: ${canvasLoadingProgressPercent}%`}></span>
                  </div>
                {:else}
                  <span class="canvas-loading-spinner" aria-hidden="true"></span>
                {/if}
                <p>{canvasLoading.message}</p>
              </div>
            </div>
          {/if}
          {#if issuePopoverOpen && issuePopoverItems.length > 0}
            <IssuePopover
              items={issuePopoverItems}
              pinned={issuePopoverPinned}
              x={issuePopoverX}
              y={issuePopoverY}
              bind:card={issuePopoverElement}
              on:move={(event) => handleIssuePopoverMove(event.detail.x, event.detail.y)}
              on:close={closeIssuePopover}
            />
          {/if}
        {/if}
      </div>
    </section>
    <RightHistoryDrawer
      open={historyDrawerOpen}
      {laps}
      session={selectedSession}
      view={historyView}
      {selectedLapId}
      {deletingLapIds}
      on:open={openHistoryDrawer}
      on:close={closeHistoryDrawer}
      on:viewchange={(event) => (historyView = event.detail.view)}
      on:selectlap={(event) => loadLapContext(event.detail.lapId, false, false).catch(() => pushToast('error', 'Unable to load lap drilldown data', false))}
      on:deletelap={(event) => handleDeleteLap(event.detail.lapId)}
    />
  </section>
  <footer class="dashboard-footer" data-testid="dashboard-footer">
    <StatusStrip {listener} {capture} lastEvent={lastStatusEvent} />
  </footer>
  {#if activeUtilityModal === 'settings'}
    <SettingsModal
      status={latestStatus}
      {listener}
      {capture}
      {worldMapStatus}
      on:close={closeUtilityModal}
      on:resetlayout={resetFloatingPanelsAndLayout}
      on:settingschange={handleSettingsChange}
      on:settingserror={handleSettingsError}
      on:worldmapchange={handleWorldMapChange}
      on:worldmaperror={handleWorldMapError}
    />
  {/if}
  {#if activeUtilityModal === 'import'}
    <ImportTelemetryModal
      importing={importBusy}
      jobs={importJobs}
      jobsLoading={importJobsLoading}
      cancellingJobIds={cancellingImportJobIds}
      on:close={closeUtilityModal}
      on:import={handleImportRawTelemetry}
      on:refreshjobs={() => refreshImportJobs()}
      on:canceljob={handleCancelImportJob}
    />
  {/if}
  {#if activeUtilityModal === 'export'}
    <ExportTelemetryModal
      defaults={exportDefaults}
      jobs={exportJobs}
      defaultsLoading={exportDefaultsLoading}
      jobsLoading={exportJobsLoading}
      exporting={exportBusy}
      cancellingJobIds={cancellingExportJobIds}
      on:close={closeUtilityModal}
      on:export={handleExportTelemetry}
      on:refreshjobs={() => refreshExportJobs()}
      on:canceljob={handleCancelExportJob}
    />
  {/if}
  {#if trackAssignmentLap}
    <TrackAssignmentPicker
      lap={trackAssignmentLap}
      profiles={trackProfiles}
      candidates={trackAssignmentCandidates}
      busy={trackAssignmentBusy || trackProfileBusy}
      error={trackAssignmentError}
      on:close={closeTrackAssignmentPicker}
      on:assign={handleAssignTrackProfile}
    />
  {/if}
  {#if activeUtilityModal === 'session-browser'}
    <SessionBrowserModal
      page={sessionPage}
      filters={sessionFilters}
      busy={sessionBrowserBusy}
      error={sessionBrowserError}
      on:close={closeUtilityModal}
      on:filterchange={(event) => handleSessionBrowserFilterChange(event).catch(() => pushToast('error', 'Unable to load sessions', false))}
      on:pagechange={(event) => handleSessionBrowserPageChange(event).catch(() => pushToast('error', 'Unable to load sessions', false))}
      on:open={(event) => handleOpenSessionFromBrowser(event).catch(() => pushToast('error', 'Unable to load session laps', false))}
      on:rename={handleRenameSession}
      on:delete={handleDeleteSession}
    />
  {/if}
  {#if activeUtilityModal === 'stats'}
    <StatsModal
      stats={statsSummary}
      unitSystem={summaryUnitSystem}
      loading={statsLoading}
      error={statsError}
      on:close={closeUtilityModal}
    />
  {/if}
  {#if activeUtilityModal === 'about'}
    <AboutModal
      {capture}
      on:close={closeUtilityModal}
      on:toast={(event) => pushToast(event.detail.level, event.detail.message, event.detail.sticky ?? false)}
    />
  {/if}
  {#if diagnosticsOpen}
    <DiagnosticsPanel
      payload={diagnosticsPayload}
      loading={diagnosticsLoading}
      restarting={diagnosticsRestarting}
      deletingTelemetry={diagnosticsDeletingTelemetry}
      on:close={closeDiagnostics}
      on:refresh={loadDiagnostics}
      on:restart={handleRestartListener}
      on:deleteAllTelemetry={handleDeleteAllTelemetry}
    />
  {/if}
  {#if shortcutHelpOpen}
    <ShortcutHelp on:close={closeShortcutHelp} />
  {/if}
</main>

<style>
  .visualisation-stage {
    display: grid;
    grid-template-rows: minmax(0, 1fr);
    min-height: 0;
    min-width: 0;
    overflow: hidden;
    position: relative;
  }

  .canvas-wrap {
    min-height: 0;
    overflow: hidden;
    position: relative;
  }

  .canvas-wrap :global(canvas) {
    display: block;
    height: 100%;
    width: 100%;
  }

  .canvas-loading-overlay {
    align-items: center;
    background: rgb(9 9 11 / 42%);
    display: flex;
    inset: 0;
    justify-content: center;
    padding: 1.5rem;
    pointer-events: auto;
    position: absolute;
    z-index: 8;
  }

  .canvas-loading-panel {
    align-items: center;
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid rgb(244 244 245 / 14%);
    border-radius: 1rem;
    box-shadow: 0 18px 50px rgb(0 0 0 / 35%);
    color: #fafafa;
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    max-width: min(24rem, 100%);
    min-width: min(22rem, 100%);
    padding: 1.25rem 1.35rem;
    text-align: center;
  }

  .canvas-loading-panel p {
    color: #e4e4e7;
    font-size: 0.92rem;
    line-height: 1.35;
    margin: 0;
  }

  .canvas-loading-progress {
    background: rgb(244 244 245 / 14%);
    border-radius: 999px;
    height: 0.55rem;
    overflow: hidden;
    width: 100%;
  }

  .canvas-loading-progress span {
    background: linear-gradient(90deg, #38bdf8, #a78bfa);
    border-radius: inherit;
    display: block;
    height: 100%;
    min-width: 0.35rem;
    transition: width 160ms ease;
  }

  .canvas-loading-spinner {
    animation: canvas-loading-spin 900ms linear infinite;
    border: 3px solid rgb(244 244 245 / 22%);
    border-radius: 999px;
    border-top-color: #38bdf8;
    height: 2.4rem;
    width: 2.4rem;
  }

  @keyframes canvas-loading-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .canvas-loading-progress span {
      transition: none;
    }

    .canvas-loading-spinner {
      animation: none;
    }
  }

  .visualisation-stage {
    --canvas-top-control-stack-gap: 0.65rem;
    --canvas-top-control-stack-height: 2.85rem;
  }

  .floating-bottom-right {
    align-items: center;
    display: flex;
    gap: 0.5rem;
  }

  .floating-top-center {
    align-items: center;
    display: flex;
    gap: var(--canvas-top-control-stack-gap);
    left: 50%;
    top: var(--canvas-top-control-center-y);
    transform: translate(-50%, -50%);
    z-index: 9;
  }

  @media (max-width: 1549px) {
    .floating-top-center {
      left: auto;
      right: var(--canvas-floating-margin);
      top: var(--canvas-floating-margin);
      transform: none;
    }

    .floating-top-right {
      align-items: flex-end;
      flex-direction: column-reverse;
      gap: var(--canvas-top-control-stack-gap);
      top: calc(var(--canvas-floating-margin) + var(--canvas-top-control-stack-height) + var(--canvas-top-control-stack-gap));
      transform: none;
    }
  }
</style>
