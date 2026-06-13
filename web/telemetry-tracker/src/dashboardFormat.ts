import type { UnitSystem } from './types';

const MPS_TO_MPH = 2.2369362920544;
const MPS_TO_KMH = 3.6;
const WATTS_TO_HP = 0.00134102209;
const NM_TO_LB_FT = 0.737562149;

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function missing(value: number | null | undefined): value is null | undefined {
  return !isFiniteNumber(value);
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (missing(value)) return '—';
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  });
}

export function formatSpeed(valueMps: number | null | undefined, unitSystem: UnitSystem): string {
  if (missing(valueMps)) return '—';
  const converted = unitSystem === 'metric' ? valueMps * MPS_TO_KMH : valueMps * MPS_TO_MPH;
  return `${Math.round(converted).toLocaleString()} ${unitSystem === 'metric' ? 'km/h' : 'mph'}`;
}

export function formatRpm(value: number | null | undefined): string {
  if (missing(value)) return '—';
  return `${Math.round(value).toLocaleString()} rpm`;
}

export function formatInputPercent(value: number | null | undefined, max = 255): string {
  if (missing(value) || max <= 0) return '—';
  return `${Math.round((value / max) * 100)}%`;
}

export function formatDegrees(valueRadians: number | null | undefined): string {
  if (missing(valueRadians)) return '—';
  return `${Math.round((valueRadians * 180) / Math.PI).toLocaleString()}°`;
}

export function formatBoost(valueBar: number | null | undefined): string {
  if (missing(valueBar)) return '—';
  return `${valueBar.toFixed(2)} bar`;
}

export function formatTemperature(valueCelsius: number | null | undefined): string {
  if (missing(valueCelsius)) return '—';
  return `${Math.round(valueCelsius).toLocaleString()}°C`;
}

export function formatTime(seconds: number | null | undefined): string {
  if (missing(seconds)) return '—';
  const safeSeconds = Math.max(0, seconds);
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds - minutes * 60;
  return `${minutes}:${remainingSeconds.toFixed(3).padStart(6, '0')}`;
}

export function formatFuel(value: number | null | undefined): string {
  if (missing(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

export function formatPower(valueWatts: number | null | undefined): string {
  if (missing(valueWatts)) return '—';
  return `${Math.round(valueWatts * WATTS_TO_HP).toLocaleString()} hp`;
}

export function formatTorque(valueNm: number | null | undefined): string {
  if (missing(valueNm)) return '—';
  return `${Math.round(valueNm * NM_TO_LB_FT).toLocaleString()} lb-ft`;
}
