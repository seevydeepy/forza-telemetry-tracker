<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import { iconPaths, type IconName } from './Icon.svelte';
  import { issueIconForMarker, issueIconToneColor, issueIconToneForMarker } from './issueMetadata';
  import type { IssueMarker, IssueSeverity, LiveSample, OverlayId, SequenceRange, TrackAsset, WorldMapTileSet } from './types';
  import { visibleWorldMapTiles, type WorldMapCalibration } from './worldMap';

  export let samples: LiveSample[] = [];
  export let ghostSamples: LiveSample[] = [];
  export let overlay: OverlayId = 'issues';
  export let markers: IssueMarker[] = [];
  export let selectedRange: SequenceRange | null = null;
  export let trackAsset: TrackAsset | null = null;
  export let worldMapTileSet: WorldMapTileSet | null = null;
  export let autoFit = false;
  export let zoomCommand: 'in' | 'out' | 'fit' | null = null;
  export let zoomCommandId = 0;
  export let incremental = false;
  export let sampleVersion = 0;
  export let lapBoundaryConfidence: string | null = null;

  const dispatch = createEventDispatcher<{
    pointselect: { sample: LiveSample; canvasX: number; canvasY: number };
    issuehover: IssueInteractionDetail;
    issuehoverclear: void;
    issueselect: IssueInteractionDetail;
    viewportinteraction: { kind: 'pan' | 'zoom' };
  }>();

  let canvas: HTMLCanvasElement;
  let hasRenderedPath = false;
  let projectedPoints: Array<{ sample: LiveSample; x: number; y: number }> = [];
  let issueTargets: IssueTarget[] = [];
  let markerSeverityBySequence = new Map<number, IssueSeverity>();
  let assetImage: HTMLImageElement | null = null;
  let assetImageSrc = '';
  const worldMapImages = new Map<string, HTMLImageElement>();
  let lastWorldMapTileSetId = '';
  let resizeObserver: ResizeObserver | null = null;
  let projection: Projection | null = null;
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let targetZoom = 1;
  let targetPanX = 0;
  let targetPanY = 0;
  let lastZoomCommandId = 0;
  let isPanning = false;
  let panStartClientX = 0;
  let panStartClientY = 0;
  let lastPanClientX = 0;
  let lastPanClientY = 0;
  let hasDraggedSinceMouseDown = false;
  let hoverSequence: number | null = null;
  let hoverIssueKey = '';
  let wasAutoFit = false;
  let renderedSampleCount = 0;
  let renderedGhostSampleCount = 0;
  let lastRenderStateKey = '';
  let currentSpeedStats: ValueStats | null = null;
  let currentTemperatureStats: ValueStats | null = null;
  let renderModel: RenderModel | null = null;
  let scheduledDrawHandle: number | null = null;
  let scheduledDrawKind: 'animationFrame' | 'timeout' | null = null;
  let viewportAnimationHandle: number | null = null;
  let viewportAnimationKind: 'animationFrame' | 'timeout' | null = null;
  let nextSampleArrayId = 1;
  const sampleArrayIds = new WeakMap<LiveSample[], number>();

  type Point = {
    x: number;
    y: number;
  };

  type Rgb = [number, number, number];
  type ZoomCommand = 'in' | 'out' | 'fit';
  type ProjectedPoint = { sample: LiveSample; x: number; y: number };
  type IssueTarget = { marker: IssueMarker; point: ProjectedPoint };
  type IssueInteractionDetail = { marker: IssueMarker; markers: IssueMarker[]; sample: LiveSample; canvasX: number; canvasY: number };
  type CarIndicatorSnapshot = { x: number; y: number; width: number; height: number; imageData: ImageData };
  type ValueStats = { min: number; median: number; max: number };
  type RouteBucket = {
    color: string;
    path: Path2D | null;
    segments: Array<{ start: ProjectedPoint; end: ProjectedPoint }>;
  };
  type RoutePathCache = {
    key: string;
    buckets: RouteBucket[];
    simplifiedPointCount: number;
  };
  type IconViewBox = {
    minX: number;
    minY: number;
    width: number;
    height: number;
  };
  type IssueIconPathEntry = {
    paths: Path2D[];
    viewBox: IconViewBox;
  };
  type RenderModel = {
    key: string;
    projection: Projection | null;
    points: ProjectedPoint[];
    ghostPoints: ProjectedPoint[];
    speedStats: ValueStats | null;
    temperatureStats: ValueStats | null;
    issueTargets: IssueTarget[];
    routePathCache: RoutePathCache | null;
  };
  type Projection = {
    signature: string;
    minX: number;
    maxX: number;
    minZ: number;
    maxZ: number;
    scale: number;
    offsetX: number;
    offsetY: number;
  };

  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = 1;
  const MAX_FIT_SCALE = MAX_ZOOM;
  const MIN_FIT_SCALE = 0.001;
  const ZOOM_STEP = 1.2;
  const VIEWPORT_ANIMATION_EASE = 0.28;
  const VIEWPORT_ZOOM_EPSILON = 0.0005;
  const VIEWPORT_PAN_EPSILON = 0.05;
  const DRAG_CLICK_THRESHOLD_PX = 3;
  const TELEMETRY_LINE_WIDTH = 3;
  const GHOST_LINE_WIDTH = 2;
  const SELECTED_RANGE_LINE_WIDTH = 5;
  const PATH_PADDING_PX = 48;
  const FIT_SAFE_AREA_RATIO = 0.8;
  const CAR_FOLLOW_DEAD_ZONE_HALF_RATIO = 0.1;
  const PROJECTION_OVERSCAN_RATIO = 0.2;
  const HOVER_PIP_RADIUS_PX = 5;
  const ISSUE_ICON_RADIUS_PX = 10;
  const ISSUE_ICON_SIZE_PX = 16;
  const ROUTE_SIMPLIFICATION_BASE_THRESHOLD_PX = 1.5;
  const ROUTE_SIMPLIFICATION_MIN_THRESHOLD_PX = 0.35;
  const START_FINISH_LAP_ACTIONS = new Set(['start', 'finalize_and_start']);
  const TRUSTED_BOUNDARY_CONFIDENCES = new Set(['game_field']);
  const ISSUE_CLUSTER_RADIUS_PX = 36;
  const ISSUE_ROUTE_COLOR = '#d4d4d8';
  const CAR_INDICATOR_SIZE_PX = 24;
  const CAR_INDICATOR_SNAPSHOT_PADDING_PX = 4;
  const CAR_INDICATOR_SNAPSHOT_RADIUS_PX = Math.ceil((CAR_INDICATOR_SIZE_PX * Math.SQRT2) / 2) + CAR_INDICATOR_SNAPSHOT_PADDING_PX;
  const CAR_INDICATOR_VIEWBOX_WIDTH = 960;
  const CAR_INDICATOR_VIEWBOX_CENTER_X = 480;
  const CAR_INDICATOR_VIEWBOX_CENTER_Y = -480;

  let carIndicatorPaths: Path2D[] | null = null;
  const issueIconPathCache = new Map<IconName, IssueIconPathEntry>();
  let carIndicatorSnapshot: CarIndicatorSnapshot | null = null;
  let hasRenderedCarIndicator = false;

  $: nextWorldMapTileSetId = worldMapTileSet?.id ?? '';
  $: if (nextWorldMapTileSetId !== lastWorldMapTileSetId) {
    lastWorldMapTileSetId = nextWorldMapTileSetId;
    worldMapImages.clear();
    scheduleDraw();
  }

  const severityPriority: Record<IssueSeverity, number> = {
    info: 1,
    warning: 2,
    critical: 3
  };

  function severityColor(severity: IssueSeverity | null | undefined): string {
    switch (severity) {
      case 'critical':
        return '#ef4444';
      case 'warning':
        return '#f59e0b';
      case 'info':
      default:
        return '#22c55e';
    }
  }

  function toPoint(sample: LiveSample, nextProjection: Projection): Point {
    return {
      x: nextProjection.offsetX + (sample.x - nextProjection.minX) * nextProjection.scale,
      y: nextProjection.offsetY + (nextProjection.maxZ - sample.z) * nextProjection.scale
    };
  }

  function buildMarkerSeverityLookup(nextMarkers: IssueMarker[]): Map<number, IssueSeverity> {
    const lookup = new Map<number, IssueSeverity>();
    for (const marker of nextMarkers) {
      const start = Math.min(marker.start_sequence, marker.end_sequence);
      const end = Math.max(marker.start_sequence, marker.end_sequence);
      for (let sequence = start; sequence <= end; sequence += 1) {
        const existing = lookup.get(sequence);
        if (!existing || severityPriority[marker.severity] > severityPriority[existing]) {
          lookup.set(sequence, marker.severity);
        }
      }
    }
    return lookup;
  }

  function markerSeverityForSequence(sequence: number): IssueSeverity | null {
    return markerSeverityBySequence.get(sequence) ?? null;
  }

  function compareIssueTargets(left: IssueTarget, right: IssueTarget): number {
    const severityDelta = severityPriority[right.marker.severity] - severityPriority[left.marker.severity];
    if (severityDelta !== 0) return severityDelta;
    const confidenceDelta = (right.marker.confidence ?? 0) - (left.marker.confidence ?? 0);
    if (confidenceDelta !== 0) return confidenceDelta;
    const startDelta = left.marker.start_sequence - right.marker.start_sequence;
    if (startDelta !== 0) return startDelta;
    return left.marker.id.localeCompare(right.marker.id);
  }

  function projectedPointForMarkerInPoints(marker: IssueMarker, points: ProjectedPoint[]): ProjectedPoint | null {
    const anchorSequence = marker.anchor_sequence ?? marker.start_sequence;
    const anchored = points.find((candidate) => candidate.sample.sequence === anchorSequence);
    if (anchored) return anchored;

    const start = Math.min(marker.start_sequence, marker.end_sequence);
    const end = Math.max(marker.start_sequence, marker.end_sequence);
    return (
      points.find(
        (candidate) => candidate.sample.sequence >= start && candidate.sample.sequence <= end
      ) ?? null
    );
  }

  function buildIssueTargetsForPoints(points: ProjectedPoint[]): IssueTarget[] {
    if (overlay !== 'issues' || markers.length === 0 || points.length === 0) return [];
    return markers
      .map((marker) => {
        const point = projectedPointForMarkerInPoints(marker, points);
        return point ? { marker, point } : null;
      })
      .filter((target): target is IssueTarget => target !== null)
      .sort(compareIssueTargets);
  }

  function clamp01(value: number): number {
    return Math.max(0, Math.min(1, value));
  }

  function clampZoom(value: number): number {
    return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value));
  }

  function formatViewportNumber(value: number): string {
    const rounded = Math.round(value * 1000) / 1000;
    return Object.is(rounded, -0) ? '0' : String(rounded);
  }

  function finiteNumber(value: number | null | undefined): number | null {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }

  function normalizedText(value: string | null | undefined): string {
    return String(value ?? '').trim().toLowerCase();
  }

  function isTrustedBoundaryConfidence(value: string | null | undefined): boolean {
    return TRUSTED_BOUNDARY_CONFIDENCES.has(normalizedText(value));
  }

  function hasTrustedBoundaryConfidence(sample: LiveSample | null | undefined): boolean {
    return isTrustedBoundaryConfidence(sample?.boundary_confidence) || isTrustedBoundaryConfidence(lapBoundaryConfidence);
  }

  function maxPresent(values: Array<number | null | undefined>): number | null {
    let max: number | null = null;
    for (const value of values) {
      const numeric = finiteNumber(value);
      if (numeric === null) continue;
      max = max === null ? numeric : Math.max(max, numeric);
    }
    return max;
  }

  function maxPositive(values: Array<number | null | undefined>): number {
    let max = 0;
    for (const value of values) {
      const numeric = finiteNumber(value);
      if (numeric === null) continue;
      max = Math.max(max, numeric);
    }
    return max;
  }

  function finiteValues(values: Array<number | null | undefined>): number[] {
    return values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  }

  function median(values: number[]): number {
    if (values.length === 0) return 0;
    const sorted = [...values].sort((left, right) => left - right);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  }

  function valueStats(values: Array<number | null | undefined>): ValueStats | null {
    const finite = finiteValues(values);
    if (finite.length === 0) return null;
    return {
      min: Math.min(...finite),
      median: median(finite),
      max: Math.max(...finite)
    };
  }

  function interpolateRgb(start: Rgb, end: Rgb, normalized: number): Rgb {
    const t = clamp01(normalized);
    return [
      Math.round(start[0] + (end[0] - start[0]) * t),
      Math.round(start[1] + (end[1] - start[1]) * t),
      Math.round(start[2] + (end[2] - start[2]) * t)
    ];
  }

  function threeStopColor(low: Rgb, mid: Rgb, high: Rgb, normalized: number): string {
    const t = clamp01(normalized);
    const [red, green, blue] = t <= 0.5 ? interpolateRgb(low, mid, t / 0.5) : interpolateRgb(mid, high, (t - 0.5) / 0.5);
    return `rgb(${red}, ${green}, ${blue})`;
  }

  function threeStopValueColor(value: number | null | undefined, stats: ValueStats | null, low: Rgb, mid: Rgb, high: Rgb): string {
    const numeric = finiteNumber(value);
    if (numeric === null || !stats || stats.max === stats.min) {
      const [red, green, blue] = mid;
      return `rgb(${red}, ${green}, ${blue})`;
    }

    if (numeric <= stats.median) {
      const range = Math.max(0.000001, stats.median - stats.min);
      const [red, green, blue] = interpolateRgb(low, mid, (numeric - stats.min) / range);
      return `rgb(${red}, ${green}, ${blue})`;
    }

    const range = Math.max(0.000001, stats.max - stats.median);
    const [red, green, blue] = interpolateRgb(mid, high, (numeric - stats.median) / range);
    return `rgb(${red}, ${green}, ${blue})`;
  }

  function speedColor(sample: LiveSample, stats: ValueStats | null): string {
    return threeStopValueColor(sample.speed_mps, stats, [255, 0, 0], [255, 255, 0], [0, 255, 0]);
  }

  function inputColor(sample: LiveSample): string {
    const throttle = Math.max(0, Math.min(1, (sample.throttle ?? 0) / 255));
    const brake = Math.max(0, Math.min(1, (sample.brake ?? 0) / 255));

    if (brake >= throttle) {
      const intensity = 0.35 + brake * 0.65;
      return `rgba(239, 68, 68, ${intensity.toFixed(3)})`;
    }

    const intensity = 0.35 + throttle * 0.65;
    return `rgba(34, 197, 94, ${intensity.toFixed(3)})`;
  }

  function gripColor(sample: LiveSample): string {
    const slip = Math.abs(finiteNumber(sample.combined_slip) ?? 0);
    return threeStopColor([132, 204, 22], [234, 179, 8], [220, 38, 38], slip / 1.2);
  }

  function tireTemperatureValue(sample: LiveSample): number | null {
    return maxPresent([
      sample.tire_temp_front_left,
      sample.tire_temp_front_right,
      sample.tire_temp_rear_left,
      sample.tire_temp_rear_right
    ]);
  }

  function suspensionTravelValue(sample: LiveSample): number {
    return clamp01(
      maxPositive([
        sample.suspension_travel_front_left,
        sample.suspension_travel_front_right,
        sample.suspension_travel_rear_left,
        sample.suspension_travel_rear_right
      ])
    );
  }

  function rpmRatioValue(sample: LiveSample): number | null {
    const currentRpm = finiteNumber(sample.current_rpm);
    const engineMaxRpm = finiteNumber(sample.engine_max_rpm);
    return currentRpm === null || engineMaxRpm === null || engineMaxRpm === 0 ? null : clamp01(currentRpm / engineMaxRpm);
  }

  function heatColor(value: number | null | undefined, stats: ValueStats | null): string {
    return threeStopValueColor(value, stats, [0, 255, 0], [255, 255, 0], [255, 0, 0]);
  }

  function fixedHeatColor(value: number | null | undefined): string {
    return heatColor(value, { min: 0, median: 0.5, max: 1 });
  }

  function segmentColor(sample: LiveSample, speedStats: ValueStats | null, temperatureStats: ValueStats | null): string {
    switch (overlay) {
      case 'speed':
        return speedColor(sample, speedStats);
      case 'inputs':
        return inputColor(sample);
      case 'grip':
        return gripColor(sample);
      case 'temperature':
        return heatColor(tireTemperatureValue(sample), temperatureStats);
      case 'suspension':
        return fixedHeatColor(suspensionTravelValue(sample));
      case 'rpm':
        return fixedHeatColor(rpmRatioValue(sample));
      case 'issues':
      default:
        return ISSUE_ROUTE_COLOR;
    }
  }

  function safeContext(): CanvasRenderingContext2D | null {
    if (!canvas) return null;
    try {
      return canvas.getContext('2d');
    } catch {
      return null;
    }
  }

  function cancelScheduledDraw() {
    if (scheduledDrawHandle === null) return;
    if (scheduledDrawKind === 'animationFrame' && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(scheduledDrawHandle);
    } else if (typeof window !== 'undefined' && typeof window.clearTimeout === 'function') {
      window.clearTimeout(scheduledDrawHandle);
    }
    scheduledDrawHandle = null;
    scheduledDrawKind = null;
  }

  function cancelViewportAnimation() {
    if (viewportAnimationHandle === null) return;
    if (viewportAnimationKind === 'animationFrame' && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(viewportAnimationHandle);
    } else if (typeof window !== 'undefined' && typeof window.clearTimeout === 'function') {
      window.clearTimeout(viewportAnimationHandle);
    }
    viewportAnimationHandle = null;
    viewportAnimationKind = null;
  }

  function scheduleDraw() {
    if (!canvas || scheduledDrawHandle !== null) return;

    const run = () => {
      scheduledDrawHandle = null;
      scheduledDrawKind = null;
      drawNow(samples, ghostSamples);
    };

    if (typeof requestAnimationFrame === 'function') {
      scheduledDrawKind = 'animationFrame';
      scheduledDrawHandle = requestAnimationFrame(run);
      return;
    }

    scheduledDrawKind = 'timeout';
    scheduledDrawHandle = window.setTimeout(run, 0);
  }

  function viewportTargetsSettled(): boolean {
    return (
      Math.abs(targetZoom - zoom) <= VIEWPORT_ZOOM_EPSILON &&
      Math.abs(targetPanX - panX) <= VIEWPORT_PAN_EPSILON &&
      Math.abs(targetPanY - panY) <= VIEWPORT_PAN_EPSILON
    );
  }

  function syncViewportToTarget(): boolean {
    const changed = zoom !== targetZoom || panX !== targetPanX || panY !== targetPanY;
    zoom = targetZoom;
    panX = targetPanX;
    panY = targetPanY;
    return changed;
  }

  function stepViewportTowardTarget(): boolean {
    if (viewportTargetsSettled()) {
      return syncViewportToTarget();
    }

    zoom += (targetZoom - zoom) * VIEWPORT_ANIMATION_EASE;
    panX += (targetPanX - panX) * VIEWPORT_ANIMATION_EASE;
    panY += (targetPanY - panY) * VIEWPORT_ANIMATION_EASE;

    if (viewportTargetsSettled()) {
      syncViewportToTarget();
    }

    return true;
  }

  function animateViewportFrame() {
    viewportAnimationHandle = null;
    viewportAnimationKind = null;

    if (stepViewportTowardTarget()) {
      drawNow(samples, ghostSamples);
    }

    if (!viewportTargetsSettled()) {
      scheduleViewportAnimation();
    }
  }

  function scheduleViewportAnimation() {
    if (!canvas || viewportAnimationHandle !== null) return;
    if (viewportTargetsSettled()) {
      if (syncViewportToTarget()) {
        scheduleDraw();
      }
      return;
    }

    if (typeof requestAnimationFrame === 'function') {
      viewportAnimationKind = 'animationFrame';
      viewportAnimationHandle = requestAnimationFrame(() => animateViewportFrame());
      return;
    }

    viewportAnimationKind = 'timeout';
    viewportAnimationHandle = window.setTimeout(() => animateViewportFrame(), 16);
  }

  function flushScheduledDrawForInteraction() {
    if (scheduledDrawHandle !== null || projectedPoints.length === 0) {
      cancelScheduledDraw();
      drawNow(samples, ghostSamples);
    }
  }

  function canvasScaleFromRect() {
    const rect = canvas.getBoundingClientRect();
    return {
      x: canvas.width / (rect.width || canvas.width || 1),
      y: canvas.height / (rect.height || canvas.height || 1)
    };
  }

  function eventCanvasPoint(event: MouseEvent | WheelEvent): Point {
    const rect = canvas.getBoundingClientRect();
    const width = rect.width || canvas.width || 1;
    const height = rect.height || canvas.height || 1;
    const left = rect.left || 0;
    const top = rect.top || 0;
    return {
      x: ((event.clientX - left) / width) * canvas.width,
      y: ((event.clientY - top) / height) * canvas.height
    };
  }

  function inverseViewportPoint(point: Point): Point {
    return {
      x: (point.x - panX) / zoom,
      y: (point.y - panY) / zoom
    };
  }

  function inverseTargetViewportPoint(point: Point): Point {
    return {
      x: (point.x - targetPanX) / targetZoom,
      y: (point.y - targetPanY) / targetZoom
    };
  }

  function applyViewportTransform(ctx: CanvasRenderingContext2D) {
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);
  }

  function setViewport(nextZoom: number, nextPanX: number, nextPanY: number) {
    targetZoom = clampZoom(nextZoom);
    targetPanX = nextPanX;
    targetPanY = nextPanY;
    scheduleViewportAnimation();
  }

  function setViewportImmediate(nextZoom: number, nextPanX: number, nextPanY: number) {
    cancelViewportAnimation();
    targetZoom = clampZoom(nextZoom);
    targetPanX = nextPanX;
    targetPanY = nextPanY;
    syncViewportToTarget();
    scheduleDraw();
  }

  function zoomAroundPoint(nextZoom: number, anchor: Point) {
    const clampedZoom = clampZoom(nextZoom);
    if (clampedZoom === targetZoom) return;

    const worldPoint = inverseTargetViewportPoint(anchor);
    setViewport(clampedZoom, anchor.x - worldPoint.x * clampedZoom, anchor.y - worldPoint.y * clampedZoom);
  }

  function resetViewport() {
    setViewport(1, 0, 0);
  }

  function resetViewportImmediate() {
    setViewportImmediate(1, 0, 0);
  }

  function fitViewportToScreen() {
    projection = null;
    renderModel = null;
    resetViewportImmediate();
  }

  function followZoneBounds(width: number, height: number) {
    const centerX = width / 2;
    const centerY = height / 2;
    const halfWidth = width * CAR_FOLLOW_DEAD_ZONE_HALF_RATIO;
    const halfHeight = height * CAR_FOLLOW_DEAD_ZONE_HALF_RATIO;
    return {
      left: centerX - halfWidth,
      right: centerX + halfWidth,
      top: centerY - halfHeight,
      bottom: centerY + halfHeight
    };
  }

  function panDeltaToKeepPointInFollowZone(point: Point, width: number, height: number): Point {
    const bounds = followZoneBounds(width, height);
    const viewportPoint = targetViewportPointFromWorld(point);
    let deltaX = 0;
    let deltaY = 0;

    if (viewportPoint.x < bounds.left) {
      deltaX = bounds.left - viewportPoint.x;
    } else if (viewportPoint.x > bounds.right) {
      deltaX = bounds.right - viewportPoint.x;
    }

    if (viewportPoint.y < bounds.top) {
      deltaY = bounds.top - viewportPoint.y;
    } else if (viewportPoint.y > bounds.bottom) {
      deltaY = bounds.bottom - viewportPoint.y;
    }

    return { x: deltaX, y: deltaY };
  }

  function adjustAutoFitViewportForPoint(point: Point | null | undefined, width: number, height: number): boolean {
    if (!autoFit || !point) return false;
    const delta = panDeltaToKeepPointInFollowZone(point, width, height);
    if (delta.x === 0 && delta.y === 0) return false;

    setViewport(targetZoom, targetPanX + delta.x, targetPanY + delta.y);
    return true;
  }

  function wouldAutoFitViewportNeedFollowPan(point: Point | null | undefined, width: number, height: number): boolean {
    if (!autoFit || !point) return false;
    const delta = panDeltaToKeepPointInFollowZone(point, width, height);
    return delta.x !== 0 || delta.y !== 0;
  }

  function canvasCenterPoint(): Point {
    return {
      x: canvas?.width ? canvas.width / 2 : 0,
      y: canvas?.height ? canvas.height / 2 : 0
    };
  }

  function applyZoomCommand(command: ZoomCommand) {
    if (command === 'fit') {
      fitViewportToScreen();
      return;
    }

    const factor = command === 'in' ? ZOOM_STEP : 1 / ZOOM_STEP;
    zoomAroundPoint(targetZoom * factor, canvasCenterPoint());
  }

  function drawSelectedRange(ctx: CanvasRenderingContext2D) {
    if (!selectedRange || projectedPoints.length < 2) return;
    const selectedPoints = projectedPoints.filter(
      ({ sample }) => sample.sequence >= selectedRange.startSequence && sample.sequence <= selectedRange.endSequence
    );
    if (selectedPoints.length < 2) return;

    const previousStrokeStyle = ctx.strokeStyle;
    const previousLineWidth = ctx.lineWidth;
    ctx.strokeStyle = '#f4f4f5';
    ctx.lineWidth = SELECTED_RANGE_LINE_WIDTH;
    ctx.beginPath();
    ctx.moveTo(selectedPoints[0].x, selectedPoints[0].y);
    for (let index = 1; index < selectedPoints.length; index += 1) {
      ctx.lineTo(selectedPoints[index].x, selectedPoints[index].y);
    }
    ctx.stroke();
    ctx.strokeStyle = previousStrokeStyle;
    ctx.lineWidth = previousLineWidth;
  }

  function projectionSignature(projectionSamples: LiveSample[]): string {
    if (projectionSamples.length === 0) return '';
    const xs = projectionSamples.map((sample) => sample.x);
    const zs = projectionSamples.map((sample) => sample.z);
    const first = projectionSamples[0];
    const last = projectionSamples[projectionSamples.length - 1];
    return [
      projectionSamples.length,
      first.sequence,
      last.sequence,
      Math.min(...xs).toFixed(3),
      Math.max(...xs).toFixed(3),
      Math.min(...zs).toFixed(3),
      Math.max(...zs).toFixed(3)
    ].join(':');
  }

  function rangeAroundCenter(min: number, max: number, minimumSpan: number) {
    const center = (min + max) / 2;
    const span = Math.max(max - min, minimumSpan);
    const halfSpan = span / 2;
    return {
      min: center - halfSpan,
      max: center + halfSpan,
      span
    };
  }

  function buildProjection(projectionSamples: LiveSample[], width: number, height: number, signature: string): Projection {
    const xs = projectionSamples.map((sample) => sample.x);
    const zs = projectionSamples.map((sample) => sample.z);
    const rawMinX = Math.min(...xs);
    const rawMaxX = Math.max(...xs);
    const rawMinZ = Math.min(...zs);
    const rawMaxZ = Math.max(...zs);
    const rawRangeX = Math.max(0, rawMaxX - rawMinX);
    const rawRangeZ = Math.max(0, rawMaxZ - rawMinZ);
    const overscanRatio = incremental ? PROJECTION_OVERSCAN_RATIO : 0;
    const overscanX = Math.max(rawRangeX, 1) * overscanRatio;
    const overscanZ = Math.max(rawRangeZ, 1) * overscanRatio;
    const horizontalPadding = Math.max(PATH_PADDING_PX, (width * (1 - FIT_SAFE_AREA_RATIO)) / 2);
    const verticalPadding = Math.max(PATH_PADDING_PX, (height * (1 - FIT_SAFE_AREA_RATIO)) / 2);
    const usableWidth = Math.max(1, width - horizontalPadding * 2);
    const usableHeight = Math.max(1, height - verticalPadding * 2);
    const xRange = rangeAroundCenter(rawMinX - overscanX, rawMaxX + overscanX, usableWidth / MAX_FIT_SCALE);
    const zRange = rangeAroundCenter(rawMinZ - overscanZ, rawMaxZ + overscanZ, usableHeight / MAX_FIT_SCALE);
    const minX = xRange.min;
    const maxX = xRange.max;
    const minZ = zRange.min;
    const maxZ = zRange.max;
    const rangeX = xRange.span;
    const rangeZ = zRange.span;
    const scale = Math.max(MIN_FIT_SCALE, Math.min(MAX_FIT_SCALE, usableWidth / rangeX, usableHeight / rangeZ));
    return {
      signature,
      minX,
      maxX,
      minZ,
      maxZ,
      scale,
      offsetX: (width - rangeX * scale) / 2,
      offsetY: (height - rangeZ * scale) / 2
    };
  }

  function ensureProjection(projectionSamples: LiveSample[], width: number, height: number, force = false): Projection | null {
    if (projectionSamples.length === 0) {
      projection = null;
      return null;
    }
    const signature = projectionSignature(projectionSamples);
    if (force || !projection || projection.signature !== signature) {
      projection = buildProjection(projectionSamples, width, height, signature);
    }
    return projection;
  }

  function projectSamples(nextSamples: LiveSample[], nextProjection: Projection) {
    return nextSamples.map((sample) => ({
      sample,
      ...toPoint(sample, nextProjection)
    }));
  }

  function selectedRangeKey() {
    return selectedRange ? `${selectedRange.startSequence}-${selectedRange.endSequence}` : '';
  }

  function markerKey() {
    return markers
      .map((marker) => `${marker.id}:${marker.start_sequence}:${marker.end_sequence}:${marker.anchor_sequence ?? ''}:${marker.severity}:${marker.confidence}`)
      .join(',');
  }

  function trackAssetKey() {
    if (!trackAsset) return '';
    const transform = trackAsset.transform;
    return [trackAsset.id, trackAsset.file_url, transform.scale, transform.rotate_deg, transform.translate_x, transform.translate_y].join(':');
  }

  function worldMapKey() {
    if (!worldMapTileSet || worldMapTileSet.status !== 'ready') return '';
    return [
      worldMapTileSet.id,
      worldMapTileSet.manifest.tileUrlTemplate ?? worldMapTileSet.tile_url_template,
      worldMapTileSet.manifest.tiles.length,
      worldMapTileSet.manifest.maxZoom
    ].join(':');
  }

  function sampleArrayKey(nextSamples: LiveSample[], version: number | null = null) {
    let id = sampleArrayIds.get(nextSamples);
    if (!id) {
      id = nextSampleArrayId;
      nextSampleArrayId += 1;
      sampleArrayIds.set(nextSamples, id);
    }
    const first = nextSamples[0];
    const last = nextSamples[nextSamples.length - 1];
    return [
      id,
      nextSamples.length,
      first?.sequence ?? '',
      last?.sequence ?? '',
      version ?? ''
    ].join(':');
  }

  function renderModelKey(width: number, height: number, nextSamples: LiveSample[], nextGhostSamples: LiveSample[]) {
    return [
      width,
      height,
      sampleArrayKey(nextSamples, sampleVersion),
      sampleArrayKey(nextGhostSamples),
      overlay,
      markerKey(),
      incremental ? 'incremental' : 'static'
    ].join('|');
  }

  function renderStateKey(width: number, height: number, nextGhostSamples: LiveSample[]) {
    return [
      width,
      height,
      overlay,
      selectedRangeKey(),
      markerKey(),
      trackAssetKey(),
      worldMapKey(),
      normalizedText(lapBoundaryConfidence),
      nextGhostSamples.length,
      autoFit ? 'auto' : 'manual',
      zoom.toFixed(4),
      panX.toFixed(2),
      panY.toFixed(2)
    ].join('|');
  }

  function rememberRenderState(nextSamples: LiveSample[], nextGhostSamples: LiveSample[], key: string) {
    renderedSampleCount = nextSamples.length;
    renderedGhostSampleCount = nextGhostSamples.length;
    lastRenderStateKey = key;
  }

  function projectionContainsSamples(nextSamples: LiveSample[], nextProjection: Projection, startIndex: number) {
    for (let index = startIndex; index < nextSamples.length; index += 1) {
      const sample = nextSamples[index];
      if (sample.x < nextProjection.minX || sample.x > nextProjection.maxX || sample.z < nextProjection.minZ || sample.z > nextProjection.maxZ) {
        return false;
      }
    }
    return true;
  }

  function simplificationThresholdPxForZoom(nextZoom: number) {
    return Math.max(
      ROUTE_SIMPLIFICATION_MIN_THRESHOLD_PX,
      ROUTE_SIMPLIFICATION_BASE_THRESHOLD_PX / Math.sqrt(Math.max(nextZoom, 1))
    );
  }

  function simplificationWorldThresholdForZoom(nextZoom: number) {
    return simplificationThresholdPxForZoom(nextZoom) / Math.max(nextZoom, 0.001);
  }

  function routePathKey(model: RenderModel) {
    return [
      model.key,
      simplificationWorldThresholdForZoom(targetZoom).toFixed(3),
      typeof Path2D === 'function' ? 'path2d' : 'fallback'
    ].join('|');
  }

  function simplifyRoutePoints(
    points: ProjectedPoint[],
    speedStats: ValueStats | null,
    temperatureStats: ValueStats | null
  ): ProjectedPoint[] {
    if (points.length <= 2) return points;
    const threshold = simplificationWorldThresholdForZoom(targetZoom);
    const thresholdSquared = threshold * threshold;
    const simplified: ProjectedPoint[] = [points[0]];
    let lastKept = points[0];

    for (let index = 1; index < points.length - 1; index += 1) {
      const point = points[index];
      const previousSegmentColor = segmentColor(point.sample, speedStats, temperatureStats);
      const nextSegmentColor = segmentColor(points[index + 1].sample, speedStats, temperatureStats);
      const preservesColorBoundary = previousSegmentColor !== nextSegmentColor;
      const dx = point.x - lastKept.x;
      const dy = point.y - lastKept.y;
      if (preservesColorBoundary || dx * dx + dy * dy >= thresholdSquared) {
        simplified.push(point);
        lastKept = point;
      }
    }

    const last = points[points.length - 1];
    if (simplified[simplified.length - 1] !== last) {
      simplified.push(last);
    }
    return simplified;
  }

  function createRouteBucket(color: string): RouteBucket {
    return {
      color,
      path: typeof Path2D === 'function' ? new Path2D() : null,
      segments: []
    };
  }

  function addRouteSegment(bucket: RouteBucket, start: ProjectedPoint, end: ProjectedPoint) {
    if (bucket.path) {
      bucket.path.moveTo(start.x, start.y);
      bucket.path.lineTo(end.x, end.y);
      return;
    }
    bucket.segments.push({ start, end });
  }

  function buildRoutePathCache(model: RenderModel): RoutePathCache {
    const simplified = simplifyRoutePoints(model.points, model.speedStats, model.temperatureStats);
    const bucketsByColor = new Map<string, RouteBucket>();

    for (let index = 1; index < simplified.length; index += 1) {
      const start = simplified[index - 1];
      const end = simplified[index];
      const color = segmentColor(end.sample, model.speedStats, model.temperatureStats);
      let bucket = bucketsByColor.get(color);
      if (!bucket) {
        bucket = createRouteBucket(color);
        bucketsByColor.set(color, bucket);
      }
      addRouteSegment(bucket, start, end);
    }

    return {
      key: routePathKey(model),
      buckets: [...bucketsByColor.values()],
      simplifiedPointCount: simplified.length
    };
  }

  function routePathCacheForModel(model: RenderModel): RoutePathCache {
    const key = routePathKey(model);
    if (!model.routePathCache || model.routePathCache.key !== key) {
      model.routePathCache = buildRoutePathCache(model);
    }
    return model.routePathCache;
  }

  function drawRouteBuckets(ctx: CanvasRenderingContext2D, buckets: RouteBucket[]) {
    if (buckets.length === 0) return;
    ctx.lineWidth = TELEMETRY_LINE_WIDTH;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    for (const bucket of buckets) {
      ctx.strokeStyle = bucket.color;
      if (bucket.path) {
        ctx.stroke(bucket.path);
        continue;
      }
      if (bucket.segments.length === 0) continue;
      ctx.beginPath();
      for (const segment of bucket.segments) {
        ctx.moveTo(segment.start.x, segment.start.y);
        ctx.lineTo(segment.end.x, segment.end.y);
      }
      ctx.stroke();
    }
  }

  function drawSegment(
    ctx: CanvasRenderingContext2D,
    start: ProjectedPoint,
    end: ProjectedPoint,
    speedStats: ValueStats | null,
    temperatureStats: ValueStats | null
  ) {
    ctx.strokeStyle = segmentColor(end.sample, speedStats, temperatureStats);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }

  function canAppendSamples(nextSamples: LiveSample[], nextGhostSamples: LiveSample[], key: string) {
    return (
      incremental &&
      hasRenderedPath &&
      hoverSequence === null &&
      selectedRange === null &&
      nextGhostSamples.length === 0 &&
      renderedGhostSampleCount === 0 &&
      nextSamples.length > renderedSampleCount &&
      renderedSampleCount >= 2 &&
      scheduledDrawHandle === null &&
      projectedPoints.length === renderedSampleCount &&
      lastRenderStateKey === key &&
      projection !== null &&
      projectionContainsSamples(nextSamples, projection, renderedSampleCount)
    );
  }

  function appendSamples(nextSamples: LiveSample[] = samples, nextGhostSamples: LiveSample[] = ghostSamples) {
    if (!canvas) return false;
    const ctx = safeContext();
    if (!ctx) return false;
    const key = renderStateKey(canvas.width, canvas.height, nextGhostSamples);
    if (!canAppendSamples(nextSamples, nextGhostSamples, key) || !projection) return false;

    const appendedPoints: ProjectedPoint[] = [];
    for (let index = renderedSampleCount; index < nextSamples.length; index += 1) {
      appendedPoints.push({ sample: nextSamples[index], ...toPoint(nextSamples[index], projection) });
    }
    const latestAppendedPoint = appendedPoints[appendedPoints.length - 1];
    if (wouldAutoFitViewportNeedFollowPan(latestAppendedPoint, canvas.width, canvas.height)) {
      resetCarIndicatorSnapshot();
      return false;
    }

    if (!restoreCarIndicatorSnapshot(ctx)) return false;

    ctx.save();
    try {
      applyViewportTransform(ctx);
      ctx.lineWidth = TELEMETRY_LINE_WIDTH;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';

      for (let index = 0; index < appendedPoints.length; index += 1) {
        const start = projectedPoints[projectedPoints.length - 1];
        const end = appendedPoints[index];
        drawSegment(ctx, start, end, currentSpeedStats, currentTemperatureStats);
        projectedPoints.push(end);
      }
    } finally {
      ctx.restore();
    }

    drawCarIndicator(ctx, projectedPoints);
    rememberRenderState(nextSamples, nextGhostSamples, key);
    return true;
  }

  function drawGhostPath(ctx: CanvasRenderingContext2D, ghostPoints: Array<{ sample: LiveSample; x: number; y: number }>) {
    if (ghostPoints.length < 2) return;
    const previousStrokeStyle = ctx.strokeStyle;
    const previousLineWidth = ctx.lineWidth;
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.55)';
    ctx.lineWidth = GHOST_LINE_WIDTH;
    ctx.beginPath();
    ctx.moveTo(ghostPoints[0].x, ghostPoints[0].y);
    for (let index = 1; index < ghostPoints.length; index += 1) {
      ctx.lineTo(ghostPoints[index].x, ghostPoints[index].y);
    }
    ctx.stroke();
    ctx.strokeStyle = previousStrokeStyle;
    ctx.lineWidth = previousLineWidth;
  }

  function drawHoverPip(ctx: CanvasRenderingContext2D) {
    if (hoverSequence === null || projectedPoints.length === 0 || isPanning) return;
    if (typeof ctx.arc !== 'function') return;
    const point = projectedPoints.find((candidate) => candidate.sample.sequence === hoverSequence);
    if (!point) return;

    const previousFillStyle = ctx.fillStyle;
    const previousStrokeStyle = ctx.strokeStyle;
    const previousLineWidth = ctx.lineWidth;
    ctx.fillStyle = '#fafafa';
    ctx.strokeStyle = '#18181b';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(point.x, point.y, HOVER_PIP_RADIUS_PX, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(point.x, point.y, HOVER_PIP_RADIUS_PX + 3, 0, Math.PI * 2);
    ctx.strokeStyle = '#a1a1aa';
    ctx.stroke();
    ctx.fillStyle = previousFillStyle;
    ctx.strokeStyle = previousStrokeStyle;
    ctx.lineWidth = previousLineWidth;
  }

  function startFinishBoundaryPoint(): ProjectedPoint | null {
    if (projectedPoints.length < 2) return null;
    const explicitBoundary = projectedPoints.find((point) => {
      const action = normalizedText(point.sample.lap_action);
      return START_FINISH_LAP_ACTIONS.has(action) && hasTrustedBoundaryConfidence(point.sample);
    });
    if (explicitBoundary) return explicitBoundary;
    return isTrustedBoundaryConfidence(lapBoundaryConfidence) ? projectedPoints[0] : null;
  }

  function drawLapBoundaryMarker(ctx: CanvasRenderingContext2D) {
    const boundary = startFinishBoundaryPoint();
    if (!boundary) return;
    if (typeof ctx.arc !== 'function' || typeof ctx.fillText !== 'function' || typeof ctx.strokeText !== 'function') return;

    const previousFillStyle = ctx.fillStyle;
    const previousStrokeStyle = ctx.strokeStyle;
    const previousLineWidth = ctx.lineWidth;
    const previousFont = ctx.font;
    const previousTextAlign = ctx.textAlign;
    const previousTextBaseline = ctx.textBaseline;

    ctx.fillStyle = 'rgba(24, 24, 27, 0.9)';
    ctx.strokeStyle = '#f4f4f5';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(boundary.x, boundary.y, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = 'rgb(0, 0, 0)';
    ctx.lineWidth = 2;
    ctx.font = '700 8px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.strokeText('S/F', boundary.x, boundary.y);
    ctx.fillText('S/F', boundary.x, boundary.y);

    ctx.fillStyle = previousFillStyle;
    ctx.strokeStyle = previousStrokeStyle;
    ctx.lineWidth = previousLineWidth;
    ctx.font = previousFont;
    ctx.textAlign = previousTextAlign;
    ctx.textBaseline = previousTextBaseline;
  }

  function parseIconViewBox(viewBox: string): IconViewBox | null {
    const parts = viewBox.trim().split(/\s+/).map((part) => Number(part));
    if (parts.length !== 4 || parts.some((part) => !Number.isFinite(part))) return null;
    const [minX, minY, width, height] = parts;
    if (width <= 0 || height <= 0) return null;
    return { minX, minY, width, height };
  }

  function issueMarkerIconPaths(marker: IssueMarker): IssueIconPathEntry | null {
    if (typeof Path2D !== 'function') return null;
    const iconName = issueIconForMarker(marker);
    const cached = issueIconPathCache.get(iconName);
    if (cached) return cached;
    const definition = iconPaths[iconName];
    if (!definition) return null;
    const viewBox = parseIconViewBox(definition.viewBox);
    if (!viewBox || definition.paths.length === 0) return null;
    const paths = definition.paths.map((path) => new Path2D(path));
    const entry = { paths, viewBox };
    issueIconPathCache.set(iconName, entry);
    return entry;
  }

  function drawIssueMarkerGlyph(ctx: CanvasRenderingContext2D, target: IssueTarget): boolean {
    const icon = issueMarkerIconPaths(target.marker);
    if (!icon || icon.paths.length === 0 || typeof ctx.fill !== 'function') return false;

    ctx.save();
    try {
      ctx.translate(target.point.x, target.point.y);
      const iconScale = ISSUE_ICON_SIZE_PX / Math.max(icon.viewBox.width, icon.viewBox.height);
      ctx.scale(iconScale, iconScale);
      ctx.translate(-(icon.viewBox.minX + icon.viewBox.width / 2), -(icon.viewBox.minY + icon.viewBox.height / 2));
      for (const path of icon.paths) {
        ctx.fill(path);
      }
      return true;
    } finally {
      ctx.restore();
    }
  }

  function drawIssueMarkerFallback(ctx: CanvasRenderingContext2D, target: IssueTarget) {
    if (typeof ctx.fillText !== 'function' || typeof ctx.strokeText !== 'function') return;
    ctx.strokeStyle = 'rgb(0, 0, 0)';
    ctx.lineWidth = 3;
    ctx.strokeText('\u00d7', target.point.x, target.point.y);
    ctx.fillText('\u00d7', target.point.x, target.point.y);
  }

  function drawIssueIcons(ctx: CanvasRenderingContext2D, targets: IssueTarget[] = issueTargets) {
    issueTargets = targets;
    if (targets.length === 0 || typeof ctx.arc !== 'function' || typeof ctx.fill !== 'function') return;

    const previousFillStyle = ctx.fillStyle;
    const previousStrokeStyle = ctx.strokeStyle;
    const previousLineWidth = ctx.lineWidth;
    const previousFont = ctx.font;
    const previousTextAlign = ctx.textAlign;
    const previousTextBaseline = ctx.textBaseline;

    ctx.font = '800 18px Inter, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let index = targets.length - 1; index >= 0; index -= 1) {
      const target = targets[index];
      if (!target) continue;
      ctx.fillStyle = 'rgba(24, 24, 27, 0.92)';
      ctx.beginPath();
      ctx.arc(target.point.x, target.point.y, ISSUE_ICON_RADIUS_PX, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = issueIconToneColor(issueIconToneForMarker(target.marker));
      if (!drawIssueMarkerGlyph(ctx, target)) {
        drawIssueMarkerFallback(ctx, target);
      }
    }

    ctx.fillStyle = previousFillStyle;
    ctx.strokeStyle = previousStrokeStyle;
    ctx.lineWidth = previousLineWidth;
    ctx.font = previousFont;
    ctx.textAlign = previousTextAlign;
    ctx.textBaseline = previousTextBaseline;
  }

  function navigationIconPaths(): Path2D[] | null {
    if (typeof Path2D !== 'function') return null;
    if (!carIndicatorPaths) {
      carIndicatorPaths = iconPaths.navigation.paths.map((path) => new Path2D(path));
    }
    return carIndicatorPaths;
  }

  function latestRouteHeading(points: ProjectedPoint[]): number | null {
    if (points.length < 2) return null;
    const latest = points[points.length - 1];
    for (let index = points.length - 2; index >= 0; index -= 1) {
      const candidate = points[index];
      const dx = latest.x - candidate.x;
      const dy = latest.y - candidate.y;
      if (dx * dx + dy * dy > 0.0001) {
        return Math.atan2(dx, -dy);
      }
    }
    return null;
  }

  function carIndicatorRotation(points: ProjectedPoint[]): number {
    const latest = points[points.length - 1];
    const yaw = finiteNumber(latest?.sample.yaw);
    if (yaw !== null) return yaw;
    return latestRouteHeading(points) ?? 0;
  }

  function carIndicatorViewportPoint(point: ProjectedPoint): Point {
    return viewportPointFromWorld(point);
  }

  function carIndicatorSnapshotBounds(point: Point) {
    const radius = CAR_INDICATOR_SNAPSHOT_RADIUS_PX;
    const left = Math.max(0, Math.floor(point.x - radius));
    const top = Math.max(0, Math.floor(point.y - radius));
    const right = Math.min(canvas.width, Math.ceil(point.x + radius));
    const bottom = Math.min(canvas.height, Math.ceil(point.y + radius));
    return {
      x: left,
      y: top,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top)
    };
  }

  function captureCarIndicatorBackground(ctx: CanvasRenderingContext2D, point: Point): CarIndicatorSnapshot | null {
    if (typeof ctx.getImageData !== 'function') return null;
    const bounds = carIndicatorSnapshotBounds(point);
    if (bounds.width <= 0 || bounds.height <= 0) return null;
    try {
      return {
        ...bounds,
        imageData: ctx.getImageData(bounds.x, bounds.y, bounds.width, bounds.height)
      };
    } catch {
      return null;
    }
  }

  function restoreCarIndicatorSnapshot(ctx: CanvasRenderingContext2D): boolean {
    if (!hasRenderedCarIndicator) return true;
    if (!carIndicatorSnapshot || typeof ctx.putImageData !== 'function') return false;
    try {
      ctx.putImageData(carIndicatorSnapshot.imageData, carIndicatorSnapshot.x, carIndicatorSnapshot.y);
      carIndicatorSnapshot = null;
      hasRenderedCarIndicator = false;
      return true;
    } catch {
      return false;
    }
  }

  function resetCarIndicatorSnapshot() {
    carIndicatorSnapshot = null;
    hasRenderedCarIndicator = false;
  }

  function drawCarIndicator(ctx: CanvasRenderingContext2D, points: ProjectedPoint[]) {
    resetCarIndicatorSnapshot();
    if (points.length === 0) return;
    if (typeof ctx.fill !== 'function') return;
    const paths = navigationIconPaths();
    if (!paths || paths.length === 0) return;

    const latest = points[points.length - 1];
    const viewportPoint = carIndicatorViewportPoint(latest);
    if (!Number.isFinite(viewportPoint.x) || !Number.isFinite(viewportPoint.y)) return;

    carIndicatorSnapshot = captureCarIndicatorBackground(ctx, viewportPoint);
    const previousFillStyle = ctx.fillStyle;

    ctx.save();
    try {
      ctx.translate(viewportPoint.x, viewportPoint.y);
      ctx.rotate(carIndicatorRotation(points));

      const iconScale = CAR_INDICATOR_SIZE_PX / CAR_INDICATOR_VIEWBOX_WIDTH;
      ctx.scale(iconScale, iconScale);
      ctx.translate(-CAR_INDICATOR_VIEWBOX_CENTER_X, -CAR_INDICATOR_VIEWBOX_CENTER_Y);
      ctx.fillStyle = '#e3e3e3';
      for (const path of paths) {
        ctx.fill(path);
      }
      hasRenderedCarIndicator = true;
    } finally {
      ctx.restore();
      ctx.fillStyle = previousFillStyle;
    }
  }

  function loadTrackAssetImage(nextAsset: TrackAsset | null) {
    const nextSrc = nextAsset?.file_url ?? '';
    if (nextSrc === assetImageSrc) return;
    assetImageSrc = nextSrc;
    assetImage = null;
    if (!nextSrc || typeof Image === 'undefined') return;

    const image = new Image();
    image.onload = () => scheduleDraw();
    image.src = nextSrc;
    assetImage = image;
  }

  function drawTrackAsset(ctx: CanvasRenderingContext2D, width: number, height: number) {
    if (!trackAsset || !assetImage || !assetImage.complete || assetImage.naturalWidth <= 0) return;

    const transform = trackAsset.transform;
    const previousAlpha = ctx.globalAlpha;
    ctx.save();
    try {
      ctx.globalAlpha = 0.62;
      ctx.translate(width / 2 + transform.translate_x, height / 2 + transform.translate_y);
      ctx.rotate((transform.rotate_deg * Math.PI) / 180);
      ctx.scale(transform.scale, transform.scale);
      ctx.drawImage(assetImage, -width / 2, -height / 2, width, height);
    } finally {
      ctx.restore();
      ctx.globalAlpha = previousAlpha;
    }
  }

  function worldMapCalibration(): WorldMapCalibration | null {
    if (!worldMapTileSet || worldMapTileSet.status !== 'ready') return null;
    return {
      worldOriginX: worldMapTileSet.manifest.worldOriginX ?? worldMapTileSet.world_origin_x,
      worldOriginZ: worldMapTileSet.manifest.worldOriginZ ?? worldMapTileSet.world_origin_z,
      worldSize: worldMapTileSet.manifest.worldSize ?? worldMapTileSet.world_size,
      tileSize: worldMapTileSet.manifest.tileSize ?? worldMapTileSet.tile_size,
      maxZoom: worldMapTileSet.manifest.maxZoom ?? worldMapTileSet.max_zoom
    };
  }

  function worldMapTileUrl(tile: { z: number; x: number; y: number; path: string }) {
    if (!worldMapTileSet) return '';
    const template = worldMapTileSet.manifest.tileUrlTemplate ?? worldMapTileSet.tile_url_template;
    return template
      .replace('{z}', String(tile.z))
      .replace('{x}', String(tile.x))
      .replace('{y}', String(tile.y));
  }

  function requestWorldMapImage(url: string): HTMLImageElement | null {
    if (!url || typeof Image === 'undefined') return null;
    const cached = worldMapImages.get(url);
    if (cached) return cached;
    const image = new Image();
    image.onload = () => scheduleDraw();
    image.src = url;
    worldMapImages.set(url, image);
    return image;
  }

  function imageReady(image: HTMLImageElement | null): image is HTMLImageElement {
    return Boolean(image && image.complete && image.naturalWidth > 0);
  }

  function visibleViewportRect(width: number, height: number) {
    const safeZoom = zoom || 1;
    return {
      left: -panX / safeZoom,
      top: -panY / safeZoom,
      right: (width - panX) / safeZoom,
      bottom: (height - panY) / safeZoom
    };
  }

  function drawWorldMapTiles(ctx: CanvasRenderingContext2D, nextProjection: Projection, width: number, height: number) {
    if (!worldMapTileSet || worldMapTileSet.status !== 'ready') return;
    const calibration = worldMapCalibration();
    const tiles = worldMapTileSet.manifest.tiles ?? [];
    if (!calibration || tiles.length === 0) return;

    const visibleTiles = visibleWorldMapTiles(tiles, calibration, nextProjection, visibleViewportRect(width, height));
    if (visibleTiles.length === 0) return;

    const previousAlpha = ctx.globalAlpha;
    ctx.save();
    try {
      ctx.globalAlpha = 0.9;
      for (const tile of visibleTiles) {
        const image = requestWorldMapImage(worldMapTileUrl(tile));
        if (!imageReady(image)) continue;
        ctx.drawImage(image, tile.dest.x, tile.dest.y, tile.dest.width, tile.dest.height);
      }
    } finally {
      ctx.restore();
      ctx.globalAlpha = previousAlpha;
    }
  }

  function getRenderModel(nextSamples: LiveSample[], nextGhostSamples: LiveSample[], width: number, height: number): RenderModel {
    const key = renderModelKey(width, height, nextSamples, nextGhostSamples);
    if (renderModel && renderModel.key === key) {
      projection = renderModel.projection;
      projectedPoints = renderModel.points;
      issueTargets = renderModel.issueTargets;
      currentSpeedStats = renderModel.speedStats;
      currentTemperatureStats = renderModel.temperatureStats;
      return renderModel;
    }

    const projectionSamples = [...nextSamples, ...nextGhostSamples];
    const nextProjection = projectionSamples.length > 0 ? ensureProjection(projectionSamples, width, height) : null;
    const speedSamples = nextSamples.length > 0 ? nextSamples : nextGhostSamples;
    const speedStats = valueStats(speedSamples.map((sample) => sample.speed_mps ?? null));
    const temperatureStats = valueStats(speedSamples.map((sample) => tireTemperatureValue(sample)));
    const points = nextProjection ? projectSamples(nextSamples, nextProjection) : [];
    const ghostPoints = nextProjection ? projectSamples(nextGhostSamples, nextProjection) : [];
    const targets = buildIssueTargetsForPoints(points);

    renderModel = {
      key,
      projection: nextProjection,
      points,
      ghostPoints,
      speedStats,
      temperatureStats,
      issueTargets: targets,
      routePathCache: null
    };
    projection = nextProjection;
    projectedPoints = points;
    issueTargets = targets;
    currentSpeedStats = speedStats;
    currentTemperatureStats = temperatureStats;
    return renderModel;
  }

  function drawNow(nextSamples: LiveSample[] = samples, nextGhostSamples: LiveSample[] = ghostSamples) {
    if (!canvas) return;

    const ctx = safeContext();
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const model = getRenderModel(nextSamples, nextGhostSamples, width, height);
    const latestPoint = model.points.length > 0 ? model.points[model.points.length - 1] : null;
    adjustAutoFitViewportForPoint(latestPoint, width, height);
    const key = renderStateKey(width, height, nextGhostSamples);
    resetCarIndicatorSnapshot();
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#09090b';
    ctx.fillRect(0, 0, width, height);
    ctx.save();
    try {
      applyViewportTransform(ctx);
      const nextProjection = model.projection;
      if (nextProjection) {
        drawWorldMapTiles(ctx, nextProjection, width, height);
      }
      drawTrackAsset(ctx, width, height);
      if (nextSamples.length < 2 && nextGhostSamples.length < 2) {
        hasRenderedPath = false;
        rememberRenderState(nextSamples, nextGhostSamples, key);
        return;
      }

      if (!nextProjection) {
        hasRenderedPath = false;
        rememberRenderState(nextSamples, nextGhostSamples, key);
        return;
      }
      drawGhostPath(ctx, model.ghostPoints);
      drawRouteBuckets(ctx, routePathCacheForModel(model).buckets);

      drawSelectedRange(ctx);
      drawLapBoundaryMarker(ctx);
      drawHoverPip(ctx);
      drawIssueIcons(ctx, model.issueTargets);
      hasRenderedPath = true;
      rememberRenderState(nextSamples, nextGhostSamples, key);
    } finally {
      ctx.restore();
    }
    drawCarIndicator(ctx, model.points);
  }

  function nearestProjectedPoint(relativePoint: Point): ProjectedPoint | null {
    if (projectedPoints.length === 0) return null;
    let nearest = projectedPoints[0];
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (const point of projectedPoints) {
      const dx = point.x - relativePoint.x;
      const dy = point.y - relativePoint.y;
      const distance = dx * dx + dy * dy;
      if (distance < nearestDistance) {
        nearest = point;
        nearestDistance = distance;
      }
    }
    return nearest;
  }

  function viewportPointFromWorld(point: Point): Point {
    return {
      x: point.x * zoom + panX,
      y: point.y * zoom + panY
    };
  }

  function targetViewportPointFromWorld(point: Point): Point {
    return {
      x: point.x * targetZoom + targetPanX,
      y: point.y * targetZoom + targetPanY
    };
  }

  function canvasCssPoint(point: Point): Point {
    if (!canvas) return point;
    const rect = canvas.getBoundingClientRect();
    return {
      x: point.x * ((rect.width || canvas.width || 1) / (canvas.width || 1)),
      y: point.y * ((rect.height || canvas.height || 1) / (canvas.height || 1))
    };
  }

  function issueTargetsNear(relativePoint: Point, radiusPx = ISSUE_CLUSTER_RADIUS_PX): IssueTarget[] {
    if (overlay !== 'issues' || issueTargets.length === 0) return [];
    const radiusSquared = radiusPx * radiusPx;
    return issueTargets
      .map((target) => {
        const dx = target.point.x - relativePoint.x;
        const dy = target.point.y - relativePoint.y;
        return { target, distanceSquared: dx * dx + dy * dy };
      })
      .filter((candidate) => candidate.distanceSquared <= radiusSquared)
      .sort((left, right) => {
        const priority = compareIssueTargets(left.target, right.target);
        return priority !== 0 ? priority : left.distanceSquared - right.distanceSquared;
      })
      .map((candidate) => candidate.target);
  }

  function issueTargetsKey(targets: IssueTarget[]): string {
    return targets.map((target) => target.marker.id).join('|');
  }

  function issueInteractionDetail(targets: IssueTarget[]): IssueInteractionDetail | null {
    const primary = targets[0];
    if (!primary) return null;
    const cssPoint = canvasCssPoint(viewportPointFromWorld(primary.point));
    return { marker: primary.marker, markers: targets.map((target) => target.marker), sample: primary.point.sample, canvasX: cssPoint.x, canvasY: cssPoint.y };
  }

  function dispatchIssueHover(targets: IssueTarget[]) {
    const nextKey = issueTargetsKey(targets);
    if (nextKey === hoverIssueKey) return;
    hoverIssueKey = nextKey;
    const detail = issueInteractionDetail(targets);
    if (detail) dispatch('issuehover', detail);
    else dispatch('issuehoverclear');
  }

  function handleClick(event: MouseEvent) {
    flushScheduledDrawForInteraction();
    if (!canvas || projectedPoints.length === 0) return;
    if (hasDraggedSinceMouseDown) {
      hasDraggedSinceMouseDown = false;
      return;
    }

    const relativePoint = inverseViewportPoint(eventCanvasPoint(event));
    const issueDetail = issueInteractionDetail(issueTargetsNear(relativePoint));
    if (issueDetail) {
      dispatch('issueselect', issueDetail);
      return;
    }

    const nearest = nearestProjectedPoint(relativePoint);
    if (!nearest) return;
    const cssPoint = canvasCssPoint(viewportPointFromWorld(nearest));

    dispatch('pointselect', { sample: nearest.sample, canvasX: cssPoint.x, canvasY: cssPoint.y });
  }

  function handleMouseMove(event: MouseEvent) {
    flushScheduledDrawForInteraction();
    if (!canvas || isPanning || projectedPoints.length === 0) return;
    const relativePoint = inverseViewportPoint(eventCanvasPoint(event));
    dispatchIssueHover(issueTargetsNear(relativePoint));
    const nearest = nearestProjectedPoint(relativePoint);
    const nextHoverSequence = nearest?.sample.sequence ?? null;
    if (nextHoverSequence === hoverSequence) return;
    hoverSequence = nextHoverSequence;
    scheduleDraw();
  }

  function handleMouseLeave() {
    if (hoverIssueKey !== '') {
      hoverIssueKey = '';
      dispatch('issuehoverclear');
    }
    if (hoverSequence === null) return;
    hoverSequence = null;
    scheduleDraw();
  }

  function handleWheel(event: WheelEvent) {
    if (!canvas) return;
    event.preventDefault();
    if (event.deltaY === 0) return;
    dispatch('viewportinteraction', { kind: 'zoom' });
    const factor = Math.exp(-event.deltaY * 0.0015);
    zoomAroundPoint(targetZoom * factor, eventCanvasPoint(event));
  }

  function handleMouseDown(event: MouseEvent) {
    if (event.button !== 0) return;
    isPanning = true;
    hasDraggedSinceMouseDown = false;
    hoverSequence = null;
    if (hoverIssueKey !== '') {
      hoverIssueKey = '';
      dispatch('issuehoverclear');
    }
    panStartClientX = event.clientX;
    panStartClientY = event.clientY;
    lastPanClientX = event.clientX;
    lastPanClientY = event.clientY;
    window.addEventListener('mousemove', handleWindowMouseMove);
    window.addEventListener('mouseup', handleWindowMouseUp);
  }

  function handleWindowMouseMove(event: MouseEvent) {
    if (!isPanning || !canvas) return;

    const deltaClientX = event.clientX - lastPanClientX;
    const deltaClientY = event.clientY - lastPanClientY;
    const dragDistance = Math.hypot(event.clientX - panStartClientX, event.clientY - panStartClientY);
    if (dragDistance >= DRAG_CLICK_THRESHOLD_PX) {
      hasDraggedSinceMouseDown = true;
    }

    lastPanClientX = event.clientX;
    lastPanClientY = event.clientY;
    const scale = canvasScaleFromRect();
    setViewport(targetZoom, targetPanX + deltaClientX * scale.x, targetPanY + deltaClientY * scale.y);
    dispatch('viewportinteraction', { kind: 'pan' });
    event.preventDefault();
  }

  function stopPanning() {
    isPanning = false;
    window.removeEventListener('mousemove', handleWindowMouseMove);
    window.removeEventListener('mouseup', handleWindowMouseUp);
  }

  function handleWindowMouseUp() {
    stopPanning();
  }

  function resizeCanvasToDisplaySize() {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const nextWidth = Math.max(1, Math.round(rect.width || canvas.width || 900));
    const nextHeight = Math.max(1, Math.round(rect.height || canvas.height || 560));
    if (canvas.width === nextWidth && canvas.height === nextHeight) return;
    canvas.width = nextWidth;
    canvas.height = nextHeight;
    projection = null;
    renderModel = null;
    setViewportImmediate(targetZoom, targetPanX, targetPanY);
  }

  $: markerSeverityBySequence = buildMarkerSeverityLookup(markers);
  $: loadTrackAssetImage(trackAsset);
  $: if (autoFit !== wasAutoFit) {
    wasAutoFit = autoFit;
    if (autoFit) {
      fitViewportToScreen();
    }
  }
  $: if (zoomCommand && zoomCommandId !== lastZoomCommandId) {
    lastZoomCommandId = zoomCommandId;
    applyZoomCommand(zoomCommand);
  }

  $: {
    samples;
    sampleVersion;
    incremental;
    overlay;
    markerSeverityBySequence;
    selectedRange;
    ghostSamples;
    trackAsset;
    worldMapTileSet;
    if (!appendSamples(samples, ghostSamples)) {
      cancelScheduledDraw();
      drawNow(samples, ghostSamples);
    }
  }

  onMount(() => {
    resizeCanvasToDisplaySize();
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => resizeCanvasToDisplaySize());
      resizeObserver.observe(canvas);
    }
    cancelScheduledDraw();
    drawNow(samples, ghostSamples);
  });

  onDestroy(() => {
    cancelScheduledDraw();
    cancelViewportAnimation();
    stopPanning();
    resizeObserver?.disconnect();
  });
</script>

<canvas
  bind:this={canvas}
  width="900"
  height="560"
  aria-label="Live telemetry path"
  data-sample-count={samples.length}
  data-first-sequence={samples[0]?.sequence ?? ''}
  data-last-sequence={samples[samples.length - 1]?.sequence ?? ''}
  data-overlay={overlay}
  data-marker-count={markers.length}
  data-issue-target-count={issueTargets.length}
  data-ghost-sample-count={ghostSamples.length}
  data-asset-id={trackAsset?.id ?? ''}
  data-world-map-tile-set-id={worldMapTileSet?.status === 'ready' ? worldMapTileSet.id : ''}
  data-selected-start={selectedRange?.startSequence ?? ''}
  data-selected-end={selectedRange?.endSequence ?? ''}
  data-auto-fit={autoFit ? 'true' : 'false'}
  data-zoom={formatViewportNumber(zoom)}
  data-pan-x={formatViewportNumber(panX)}
  data-pan-y={formatViewportNumber(panY)}
  data-target-zoom={formatViewportNumber(targetZoom)}
  data-target-pan-x={formatViewportNumber(targetPanX)}
  data-target-pan-y={formatViewportNumber(targetPanY)}
  style:cursor={isPanning ? 'grabbing' : 'grab'}
  on:click={handleClick}
  on:mousedown={handleMouseDown}
  on:mousemove={handleMouseMove}
  on:mouseleave={handleMouseLeave}
  on:wheel={handleWheel}
></canvas>
