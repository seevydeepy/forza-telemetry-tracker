import { describe, expect, it } from 'vitest';
import {
  attitudeDegrees,
  gForceMagnitude,
  miniRouteBounds,
  normalizeGauge,
  projectMiniRoutePoint,
  rpmGaugeColor,
  wheelTelemetry
} from './dashboardGeometry';
import type { LiveSample } from './types';

const sample: LiveSample = {
  sequence: 1,
  received_at_ms: 1,
  game_timestamp_ms: 1,
  lap_number: 1,
  current_lap: 0,
  current_race_time: 0,
  x: 10,
  y: 0,
  z: 20,
  speed_mps: 0,
  throttle: 0,
  brake: 0,
  steer: 0,
  gear: 1,
  acceleration_x: 9.80665,
  acceleration_y: 0,
  acceleration_z: 9.80665,
  yaw: Math.PI,
  pitch: Math.PI / 2,
  roll: -Math.PI / 2,
  tire_temp_front_left: 80,
  tire_slip_ratio_front_left: 0.2,
  wheel_on_rumble_strip_front_left: 1
};

describe('dashboardGeometry', () => {
  it('derives wheel telemetry in dashboard order', () => {
    const wheels = wheelTelemetry(sample);

    expect(wheels.map((wheel) => wheel.id)).toEqual(['front_left', 'front_right', 'rear_left', 'rear_right']);
    expect(wheels[0].tireTemp).toBe(80);
    expect(wheels[0].slipRatio).toBe(0.2);
    expect(wheels[0].onRumbleStrip).toBe(1);
  });

  it('computes g-force magnitude and attitude degrees', () => {
    expect(gForceMagnitude(sample)).toBeCloseTo(Math.SQRT2, 5);
    expect(attitudeDegrees(sample)).toEqual({ yaw: 180, pitch: 90, roll: -90 });
  });

  it('builds mini-route bounds and projects a point', () => {
    const bounds = miniRouteBounds([
      { ...sample, x: 0, z: 0 },
      { ...sample, x: 10, z: 20 }
    ]);

    expect(bounds).toEqual({ minX: 0, maxX: 10, minZ: 0, maxZ: 20, width: 10, height: 20 });
    expect(projectMiniRoutePoint({ ...sample, x: 5, z: 10 }, bounds, 100, 100)).toEqual({ x: 50, y: 50 });
    expect(projectMiniRoutePoint({ ...sample, x: 0, z: 20 }, bounds, 100, 100)).toEqual({ x: 0, y: 0 });
    expect(projectMiniRoutePoint({ ...sample, x: 10, z: 0 }, bounds, 100, 100)).toEqual({ x: 100, y: 100 });
  });

  it('normalizes gauge values and clamps out-of-range inputs', () => {
    expect(normalizeGauge(50, 0, 100)).toBe(0.5);
    expect(normalizeGauge(-10, 0, 100)).toBe(0);
    expect(normalizeGauge(150, 0, 100)).toBe(1);
    expect(normalizeGauge(null, 0, 100)).toBe(0);
  });

  it('uses a single rpm gauge color that changes as revs rise', () => {
    expect(rpmGaugeColor(null)).toBe('#22c55e');
    expect(rpmGaugeColor(0.4)).toBe('#22c55e');
    expect(rpmGaugeColor(0.82)).toBe('#facc15');
    expect(rpmGaugeColor(1)).toBe('#ef4444');
  });
});
