import type { IconName } from './Icon.svelte';
import type { IssueMarker } from './types';

export type IssueFamily = 'grip' | 'temperature' | 'rpm' | 'suspension' | 'collision' | 'raceControl' | 'unknown';
export type IssueIconTone = 'green' | 'yellow' | 'red' | 'blue' | 'orange' | 'purple' | 'neutral';
export type IssueThresholdCondition = { label: string; operator: 'gte' | 'lte'; value: number; unit?: string; decimals?: number };
export type IssueDefinition = { metric: string; issueKind: string; family: IssueFamily; icon: IconName; iconTone: IssueIconTone; valueLabel: string; thresholdConditions: IssueThresholdCondition[]; note?: string };

export const issueIconToneColors: Record<IssueIconTone, string> = {
  green: '#22c55e',
  yellow: '#eab308',
  red: '#ef4444',
  blue: '#38bdf8',
  orange: '#f97316',
  purple: '#a78bfa',
  neutral: '#e4e4e7'
};

export const issueDefinitions: IssueDefinition[] = [
  { metric: 'rear_combined_slip', issueKind: 'Rear combined slip', family: 'grip', icon: 'grip', iconTone: 'yellow', valueLabel: 'Rear combined slip', thresholdConditions: [{ label: 'Rear combined slip', operator: 'gte', value: 1.15, decimals: 2 }] },
  { metric: 'brake_pressure_and_slip', issueKind: 'Braking instability', family: 'grip', icon: 'grip', iconTone: 'red', valueLabel: 'Combined slip', thresholdConditions: [{ label: 'Brake', operator: 'gte', value: 80, decimals: 0 }, { label: 'Combined slip', operator: 'gte', value: 0.35, decimals: 2 }] },
  { metric: 'throttle_and_rear_slip', issueKind: 'Traction-limited exit', family: 'grip', icon: 'grip', iconTone: 'green', valueLabel: 'Rear slip', thresholdConditions: [{ label: 'Throttle', operator: 'gte', value: 90, decimals: 0 }, { label: 'Rear slip', operator: 'gte', value: 0.3, decimals: 2 }] },
  { metric: 'suspension_travel', issueKind: 'Suspension bottoming', family: 'suspension', icon: 'suspensionBottoming', iconTone: 'purple', valueLabel: 'Suspension compression', thresholdConditions: [{ label: 'Compression', operator: 'gte', value: 0.98, decimals: 2 }] },
  { metric: 'engine_rpm', issueKind: 'Rev limiter', family: 'rpm', icon: 'rpm', iconTone: 'red', valueLabel: 'RPM ratio', thresholdConditions: [{ label: 'RPM ratio', operator: 'gte', value: 0.99, decimals: 2 }], note: '3 contiguous samples' },
  { metric: 'engine_rpm_and_throttle', issueKind: 'Low RPM bogging', family: 'rpm', icon: 'rpm', iconTone: 'blue', valueLabel: 'RPM ratio', thresholdConditions: [{ label: 'Throttle', operator: 'gte', value: 70, decimals: 0 }, { label: 'RPM ratio', operator: 'lte', value: 0.4, decimals: 2 }] },
  { metric: 'tire_temperature', issueKind: 'Hot tire temperature', family: 'temperature', icon: 'temperature', iconTone: 'orange', valueLabel: 'Tire temperature', thresholdConditions: [{ label: 'Tire temperature', operator: 'gte', value: 105, unit: '°C', decimals: 0 }] },
  { metric: 'collision_smashable_time_loss', issueKind: 'Smashable collision', family: 'collision', icon: 'collision', iconTone: 'yellow', valueLabel: 'Estimated time loss', thresholdConditions: [{ label: 'Estimated time loss', operator: 'gte', value: 0.2, unit: 's', decimals: 2 }] },
  { metric: 'collision_solid_inferred_time_loss', issueKind: 'Solid impact (inferred)', family: 'collision', icon: 'collision', iconTone: 'red', valueLabel: 'Estimated time loss', thresholdConditions: [{ label: 'Estimated time loss', operator: 'gte', value: 0.25, unit: 's', decimals: 2 }] },
  { metric: 'race.rewind', issueKind: 'Rewind', family: 'raceControl', icon: 'fast_rewind', iconTone: 'blue', valueLabel: 'Race-control event', thresholdConditions: [], note: 'Lap kept; route segment after the rewind point was trimmed.' },
  { metric: 'race.reset', issueKind: 'Reset', family: 'raceControl', icon: 'history', iconTone: 'neutral', valueLabel: 'Race-control event', thresholdConditions: [], note: 'Lap kept; route segment after the reset point was trimmed.' }
];

const byMetric = new Map(issueDefinitions.map((definition) => [definition.metric, definition]));
const byKind = new Map(issueDefinitions.map((definition) => [definition.issueKind, definition]));
const glyph = (operator: 'gte' | 'lte' | null | undefined) => (operator === 'gte' ? '≥' : operator === 'lte' ? '≤' : '');

export function formatIssueNumber(value: number, decimals?: number): string {
  if (typeof decimals === 'number') return value.toFixed(decimals);
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function thresholdSummaryForDefinition(definition: IssueDefinition): string {
  if (definition.thresholdConditions.length === 0) return definition.note ?? 'Threshold details unavailable';
  const text = definition.thresholdConditions.map((condition) => `${condition.label} ${glyph(condition.operator)} ${formatIssueNumber(condition.value, condition.decimals)}${condition.unit ? ` ${condition.unit}` : ''}`).join(', ');
  return definition.note ? `${text}; ${definition.note}` : text;
}

export function issueDefinitionForMarker(marker: IssueMarker): IssueDefinition {
  const known = byMetric.get(marker.metric) ?? byKind.get(marker.issue_kind ?? '');
  if (known) return known;
  const issueKind = marker.issue_kind || marker.metric || 'Issue';
  return { metric: marker.metric, issueKind, family: 'unknown', icon: 'overlayIssues', iconTone: 'neutral', valueLabel: marker.value_label || issueKind, thresholdConditions: [] };
}

export const issueIconForMarker = (marker: IssueMarker): IconName => issueDefinitionForMarker(marker).icon;
export const issueIconToneForMarker = (marker: IssueMarker): IssueIconTone => issueDefinitionForMarker(marker).iconTone;
export const issueIconToneColor = (tone: IssueIconTone): string => issueIconToneColors[tone] ?? issueIconToneColors.neutral;

export function issueValueLine(marker: IssueMarker): string {
  const operator = glyph(marker.threshold_operator);
  if (typeof marker.actual_value === 'number' && Number.isFinite(marker.actual_value) && typeof marker.threshold_value === 'number' && Number.isFinite(marker.threshold_value) && operator && marker.value_label) {
    return `${marker.value_label}: ${formatIssueNumber(marker.actual_value)} ${operator} ${formatIssueNumber(marker.threshold_value)}${marker.value_unit ? ` ${marker.value_unit}` : ''}`;
  }
  return thresholdSummaryForDefinition(issueDefinitionForMarker(marker));
}
