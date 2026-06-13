import type { LiveSample } from './types';

export type DashboardPlaybackTimeSource = 'game_timestamp_ms' | 'received_at_ms' | 'synthetic';

export interface DashboardPlaybackPoint {
  sample: LiveSample;
  index: number;
  timeMs: number;
  elapsedMs: number;
  progress: number;
}

export interface DashboardPlaybackTimeline {
  source: DashboardPlaybackTimeSource;
  durationMs: number;
  points: DashboardPlaybackPoint[];
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function fieldTimes(samples: LiveSample[], field: 'game_timestamp_ms' | 'received_at_ms'): number[] | null {
  if (samples.length === 0) return [];
  const raw = samples.map((sample) => sample[field]);
  if (!raw.every(isFiniteNumber)) return null;
  for (let index = 1; index < raw.length; index += 1) {
    const delta = raw[index] - raw[index - 1];
    if (delta < 0 || delta > 10_000) return null;
  }
  const first = raw[0] ?? 0;
  return raw.map((value) => value - first);
}

function syntheticTimes(samples: LiveSample[]): number[] {
  return samples.map((_sample, index) => index * 16);
}

function currentLapElapsedTimes(samples: LiveSample[]): number[] | null {
  if (samples.length === 0) return [];
  const raw = samples.map((sample) => sample.current_lap);
  if (!raw.every((value) => isFiniteNumber(value) && value >= 0)) return null;
  let hasIncrease = false;
  for (let index = 1; index < raw.length; index += 1) {
    const delta = raw[index] - raw[index - 1];
    if (delta < 0) return null;
    if (delta > 0) hasIncrease = true;
  }
  if (!hasIncrease) return null;
  return raw.map((value) => Math.round(value * 1000));
}

function chooseTimes(samples: LiveSample[]): { source: DashboardPlaybackTimeSource; times: number[] } {
  const gameTimes = fieldTimes(samples, 'game_timestamp_ms');
  if (gameTimes) return { source: 'game_timestamp_ms', times: gameTimes };
  const receivedTimes = fieldTimes(samples, 'received_at_ms');
  if (receivedTimes) return { source: 'received_at_ms', times: receivedTimes };
  return { source: 'synthetic', times: syntheticTimes(samples) };
}

export function displayElapsedMs(sample: LiveSample | null | undefined, fallbackTimeMs: number): number {
  const lapSeconds = sample?.current_lap;
  if (isFiniteNumber(lapSeconds) && lapSeconds >= 0) {
    return Math.round(lapSeconds * 1000);
  }
  return Math.max(0, Math.round(fallbackTimeMs));
}

export function buildPlaybackTimeline(samples: LiveSample[]): DashboardPlaybackTimeline {
  const { source, times } = chooseTimes(samples);
  const elapsedTimes = currentLapElapsedTimes(samples);
  const durationMs = times.length > 0 ? Math.max(0, times[times.length - 1]) : 0;
  const points = samples.map((sample, index) => {
    const timeMs = times[index] ?? index * 16;
    return {
      sample,
      index,
      timeMs,
      elapsedMs: elapsedTimes?.[index] ?? Math.max(0, Math.round(timeMs)),
      progress: durationMs > 0 ? clamp(timeMs / durationMs, 0, 1) : 0
    };
  });
  return { source, durationMs, points };
}

export function playbackPointInTimelineAtTime(timeline: DashboardPlaybackTimeline, timeMs: number): DashboardPlaybackPoint | null {
  if (timeline.points.length === 0) return null;
  const clampedTime = clamp(timeMs, 0, timeline.durationMs);
  let selected = timeline.points[0];
  for (const point of timeline.points) {
    if (point.timeMs <= clampedTime) {
      selected = point;
    } else {
      break;
    }
  }
  return selected;
}

export function playbackPointAtTime(samples: LiveSample[], timeMs: number): DashboardPlaybackPoint | null {
  return playbackPointInTimelineAtTime(buildPlaybackTimeline(samples), timeMs);
}

export function playbackPointAtProgress(samples: LiveSample[], progress: number): DashboardPlaybackPoint | null {
  const timeline = buildPlaybackTimeline(samples);
  return playbackPointInTimelineAtTime(timeline, clamp(progress, 0, 1) * timeline.durationMs);
}

export function progressForTime(durationMs: number, timeMs: number): number {
  if (durationMs <= 0) return 0;
  return clamp(timeMs / durationMs, 0, 1);
}

export function nextPlaybackTime(
  currentTimeMs: number,
  deltaMs: number,
  durationMs: number
): { timeMs: number; ended: boolean } {
  const nextTime = clamp(currentTimeMs + Math.max(0, deltaMs), 0, Math.max(0, durationMs));
  return { timeMs: nextTime, ended: nextTime >= durationMs };
}
