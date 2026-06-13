import { describe, expect, it } from 'vitest';
import {
  buildPlaybackTimeline,
  displayElapsedMs,
  nextPlaybackTime,
  playbackPointInTimelineAtTime,
  playbackPointAtProgress,
  playbackPointAtTime
} from './dashboardPlayback';
import type { LiveSample } from './types';

function sample(overrides: Partial<LiveSample>): LiveSample {
  return {
    sequence: 1,
    received_at_ms: 1000,
    game_timestamp_ms: 2000,
    lap_number: 1,
    current_lap: 0,
    current_race_time: 0,
    x: 0,
    y: 0,
    z: 0,
    speed_mps: 0,
    throttle: 0,
    brake: 0,
    steer: 0,
    gear: 1,
    ...overrides
  };
}

describe('dashboardPlayback', () => {
  it('prefers monotonic game timestamps for recorded-speed playback', () => {
    const timeline = buildPlaybackTimeline([
      sample({ sequence: 1, game_timestamp_ms: 1000, received_at_ms: 5000 }),
      sample({ sequence: 2, game_timestamp_ms: 1250, received_at_ms: 9000 }),
      sample({ sequence: 3, game_timestamp_ms: 1750, received_at_ms: 15000 })
    ]);

    expect(timeline.source).toBe('game_timestamp_ms');
    expect(timeline.durationMs).toBe(750);
    expect(timeline.points.map((point) => point.timeMs)).toEqual([0, 250, 750]);
  });

  it('uses increasing current lap seconds as display elapsed time', () => {
    const timeline = buildPlaybackTimeline([
      sample({ sequence: 1, game_timestamp_ms: 1000, current_lap: 10 }),
      sample({ sequence: 2, game_timestamp_ms: 1500, current_lap: 10.5 }),
      sample({ sequence: 3, game_timestamp_ms: 2000, current_lap: 11.25 })
    ]);

    expect(timeline.points.map((point) => point.elapsedMs)).toEqual([10000, 10500, 11250]);
  });

  it('falls back to playback clock for non-increasing lap-time displays', () => {
    const timeline = buildPlaybackTimeline([
      sample({ sequence: 1, game_timestamp_ms: 1000, current_lap: 2 }),
      sample({ sequence: 2, game_timestamp_ms: 1500, current_lap: 2 }),
      sample({ sequence: 3, game_timestamp_ms: 2000, current_lap: 2 })
    ]);

    expect(timeline.points.map((point) => point.elapsedMs)).toEqual([0, 500, 1000]);
  });

  it('falls back to received timestamps when game timestamps jump too far', () => {
    const timeline = buildPlaybackTimeline([
      sample({ sequence: 1, game_timestamp_ms: 1000, received_at_ms: 10 }),
      sample({ sequence: 2, game_timestamp_ms: 25_000, received_at_ms: 26 }),
      sample({ sequence: 3, game_timestamp_ms: 25_016, received_at_ms: 42 })
    ]);

    expect(timeline.source).toBe('received_at_ms');
    expect(timeline.durationMs).toBe(32);
    expect(timeline.points.map((point) => point.timeMs)).toEqual([0, 16, 32]);
  });

  it('uses synthetic 16ms frames when recorded timestamps are unusable', () => {
    const timeline = buildPlaybackTimeline([
      sample({ sequence: 1, game_timestamp_ms: 100, received_at_ms: 20 }),
      sample({ sequence: 2, game_timestamp_ms: 90, received_at_ms: 10 }),
      sample({ sequence: 3, game_timestamp_ms: 80, received_at_ms: 0 })
    ]);

    expect(timeline.source).toBe('synthetic');
    expect(timeline.durationMs).toBe(32);
    expect(timeline.points.map((point) => point.timeMs)).toEqual([0, 16, 32]);
  });

  it('selects samples by scrub progress and playback clock', () => {
    const samples = [
      sample({ sequence: 1, game_timestamp_ms: 1000 }),
      sample({ sequence: 2, game_timestamp_ms: 1500 }),
      sample({ sequence: 3, game_timestamp_ms: 2000 })
    ];

    expect(playbackPointAtProgress(samples, 0.75)?.sample.sequence).toBe(2);
    expect(playbackPointAtTime(samples, 1000)?.sample.sequence).toBe(3);
  });

  it('selects playback samples from a precomputed timeline without rebuilding it', () => {
    const samples = [
      sample({ sequence: 1, game_timestamp_ms: 1000 }),
      sample({ sequence: 2, game_timestamp_ms: 1500 }),
      sample({ sequence: 3, game_timestamp_ms: 2000 })
    ];
    const timeline = buildPlaybackTimeline(samples);

    expect(playbackPointInTimelineAtTime(timeline, 750)?.sample.sequence).toBe(2);
    expect(playbackPointInTimelineAtTime(timeline, 1000)?.sample.sequence).toBe(3);
  });

  it('advances playback at recorded speed and reports completion', () => {
    expect(nextPlaybackTime(500, 250, 1000)).toEqual({ timeMs: 750, ended: false });
    expect(nextPlaybackTime(900, 250, 1000)).toEqual({ timeMs: 1000, ended: true });
  });

  it('uses current lap seconds for display elapsed time when available', () => {
    expect(displayElapsedMs(sample({ current_lap: 12.345 }), 1000)).toBe(12345);
    expect(displayElapsedMs(sample({ current_lap: -1 }), 1000)).toBe(1000);
  });
});
