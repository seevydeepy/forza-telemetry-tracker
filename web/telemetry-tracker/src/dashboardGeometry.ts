import type { LiveSample } from './types';

const STANDARD_GRAVITY = 9.80665;
const RPM_GREEN = '#22c55e';
const RPM_YELLOW = '#facc15';
const RPM_RED = '#ef4444';

export type WheelId = 'front_left' | 'front_right' | 'rear_left' | 'rear_right';

export interface WheelTelemetry {
  id: WheelId;
  label: string;
  tireTemp: number | null;
  slipRatio: number | null;
  slipAngle: number | null;
  combinedSlip: number | null;
  rotationSpeed: number | null;
  onRumbleStrip: number | null;
  puddleDepth: number | null;
  surfaceRumble: number | null;
  suspensionTravel: number | null;
  suspensionTravelMeters: number | null;
}

export interface MiniRouteBounds {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  width: number;
  height: number;
}

function finiteOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function colorChannelFromHex(color: string, offset: number): number {
  return Number.parseInt(color.slice(offset, offset + 2), 16);
}

function interpolateHexColor(start: string, end: string, amount: number): string {
  const clamped = clamp01(amount);
  const channels = [1, 3, 5].map((offset) => {
    const startChannel = colorChannelFromHex(start, offset);
    const endChannel = colorChannelFromHex(end, offset);
    return Math.round(startChannel + (endChannel - startChannel) * clamped)
      .toString(16)
      .padStart(2, '0');
  });
  return `#${channels.join('')}`;
}

function radiansToDegrees(value: number | null | undefined): number | null {
  const finite = finiteOrNull(value);
  return finite === null ? null : Math.round((finite * 180) / Math.PI);
}

export function wheelTelemetry(sample: LiveSample | null | undefined): WheelTelemetry[] {
  return [
    {
      id: 'front_left',
      label: 'Front left',
      tireTemp: finiteOrNull(sample?.tire_temp_front_left),
      slipRatio: finiteOrNull(sample?.tire_slip_ratio_front_left),
      slipAngle: finiteOrNull(sample?.tire_slip_angle_front_left),
      combinedSlip: finiteOrNull(sample?.tire_combined_slip_front_left),
      rotationSpeed: finiteOrNull(sample?.wheel_rotation_speed_front_left),
      onRumbleStrip: finiteOrNull(sample?.wheel_on_rumble_strip_front_left),
      puddleDepth: finiteOrNull(sample?.wheel_in_puddle_depth_front_left),
      surfaceRumble: finiteOrNull(sample?.surface_rumble_front_left),
      suspensionTravel: finiteOrNull(sample?.suspension_travel_front_left),
      suspensionTravelMeters: finiteOrNull(sample?.suspension_travel_meters_front_left)
    },
    {
      id: 'front_right',
      label: 'Front right',
      tireTemp: finiteOrNull(sample?.tire_temp_front_right),
      slipRatio: finiteOrNull(sample?.tire_slip_ratio_front_right),
      slipAngle: finiteOrNull(sample?.tire_slip_angle_front_right),
      combinedSlip: finiteOrNull(sample?.tire_combined_slip_front_right),
      rotationSpeed: finiteOrNull(sample?.wheel_rotation_speed_front_right),
      onRumbleStrip: finiteOrNull(sample?.wheel_on_rumble_strip_front_right),
      puddleDepth: finiteOrNull(sample?.wheel_in_puddle_depth_front_right),
      surfaceRumble: finiteOrNull(sample?.surface_rumble_front_right),
      suspensionTravel: finiteOrNull(sample?.suspension_travel_front_right),
      suspensionTravelMeters: finiteOrNull(sample?.suspension_travel_meters_front_right)
    },
    {
      id: 'rear_left',
      label: 'Rear left',
      tireTemp: finiteOrNull(sample?.tire_temp_rear_left),
      slipRatio: finiteOrNull(sample?.tire_slip_ratio_rear_left),
      slipAngle: finiteOrNull(sample?.tire_slip_angle_rear_left),
      combinedSlip: finiteOrNull(sample?.tire_combined_slip_rear_left),
      rotationSpeed: finiteOrNull(sample?.wheel_rotation_speed_rear_left),
      onRumbleStrip: finiteOrNull(sample?.wheel_on_rumble_strip_rear_left),
      puddleDepth: finiteOrNull(sample?.wheel_in_puddle_depth_rear_left),
      surfaceRumble: finiteOrNull(sample?.surface_rumble_rear_left),
      suspensionTravel: finiteOrNull(sample?.suspension_travel_rear_left),
      suspensionTravelMeters: finiteOrNull(sample?.suspension_travel_meters_rear_left)
    },
    {
      id: 'rear_right',
      label: 'Rear right',
      tireTemp: finiteOrNull(sample?.tire_temp_rear_right),
      slipRatio: finiteOrNull(sample?.tire_slip_ratio_rear_right),
      slipAngle: finiteOrNull(sample?.tire_slip_angle_rear_right),
      combinedSlip: finiteOrNull(sample?.tire_combined_slip_rear_right),
      rotationSpeed: finiteOrNull(sample?.wheel_rotation_speed_rear_right),
      onRumbleStrip: finiteOrNull(sample?.wheel_on_rumble_strip_rear_right),
      puddleDepth: finiteOrNull(sample?.wheel_in_puddle_depth_rear_right),
      surfaceRumble: finiteOrNull(sample?.surface_rumble_rear_right),
      suspensionTravel: finiteOrNull(sample?.suspension_travel_rear_right),
      suspensionTravelMeters: finiteOrNull(sample?.suspension_travel_meters_rear_right)
    }
  ];
}

export function gForceMagnitude(sample: LiveSample | null | undefined): number | null {
  const x = finiteOrNull(sample?.acceleration_x);
  const y = finiteOrNull(sample?.acceleration_y);
  const z = finiteOrNull(sample?.acceleration_z);
  if (x === null || y === null || z === null) return null;
  return Math.sqrt(x * x + y * y + z * z) / STANDARD_GRAVITY;
}

export function attitudeDegrees(sample: LiveSample | null | undefined): { yaw: number | null; pitch: number | null; roll: number | null } {
  return {
    yaw: radiansToDegrees(sample?.yaw),
    pitch: radiansToDegrees(sample?.pitch),
    roll: radiansToDegrees(sample?.roll)
  };
}

export function miniRouteBounds(samples: LiveSample[]): MiniRouteBounds | null {
  const points = samples.filter((sample) => Number.isFinite(sample.x) && Number.isFinite(sample.z));
  if (points.length === 0) return null;
  const xs = points.map((sample) => sample.x);
  const zs = points.map((sample) => sample.z);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);
  return {
    minX,
    maxX,
    minZ,
    maxZ,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxZ - minZ)
  };
}

export function projectMiniRoutePoint(
  sample: LiveSample,
  bounds: MiniRouteBounds | null,
  width: number,
  height: number
): { x: number; y: number } | null {
  if (!bounds || !Number.isFinite(sample.x) || !Number.isFinite(sample.z)) return null;
  return {
    x: ((sample.x - bounds.minX) / bounds.width) * width,
    y: ((bounds.maxZ - sample.z) / bounds.height) * height
  };
}

export function normalizeGauge(value: number | null | undefined, min: number, max: number): number {
  const finite = finiteOrNull(value);
  if (finite === null || max <= min) return 0;
  return Math.max(0, Math.min(1, (finite - min) / (max - min)));
}

export function rpmGaugeColor(percent: number | null | undefined): string {
  const finite = finiteOrNull(percent);
  const value = clamp01(finite ?? 0);
  if (value <= 0.55) return RPM_GREEN;
  if (value <= 0.82) return interpolateHexColor(RPM_GREEN, RPM_YELLOW, (value - 0.55) / 0.27);
  return interpolateHexColor(RPM_YELLOW, RPM_RED, (value - 0.82) / 0.18);
}
