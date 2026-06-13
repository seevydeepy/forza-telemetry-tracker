import { describe, expect, it } from 'vitest';
import { iconPaths } from './Icon.svelte';
import { issueDefinitions, issueDefinitionForMarker, issueIconForMarker, issueIconToneColor, issueIconToneColors, issueValueLine, thresholdSummaryForDefinition } from './issueMetadata';
import type { IssueMarker } from './types';

function makeMarker(overrides: Partial<IssueMarker> = {}): IssueMarker {
  return {
    id: 'marker-1', session_id: 'session-a', lap_id: 'lap-a', start_sequence: 10, end_sequence: 10,
    metric: 'engine_rpm_and_throttle', severity: 'warning', reason: 'Old reason copy must not be used by UI metadata.',
    ruleset_version: 3, confidence: 0.82, anchor_sequence: 10, issue_kind: 'Low RPM bogging',
    actual_value: 0.36, threshold_value: 0.4, threshold_operator: 'lte', value_label: 'RPM ratio', value_unit: null,
    ...overrides
  };
}

describe('issueMetadata', () => {
  it('defines every currently detected issue type in display order', () => {
    expect(issueDefinitions.map((definition) => definition.metric)).toEqual([
      'rear_combined_slip', 'brake_pressure_and_slip', 'throttle_and_rear_slip', 'suspension_travel',
      'engine_rpm', 'engine_rpm_and_throttle', 'tire_temperature',
      'collision_smashable_time_loss', 'collision_solid_inferred_time_loss', 'race.rewind', 'race.reset'
    ]);
  });

  it('maps issue types to icons and requested icon tones', () => {
    expect(issueDefinitions.map((definition) => [definition.issueKind, definition.icon, definition.iconTone])).toEqual([
      ['Rear combined slip', 'grip', 'yellow'], ['Braking instability', 'grip', 'red'], ['Traction-limited exit', 'grip', 'green'],
      ['Suspension bottoming', 'suspensionBottoming', 'purple'], ['Rev limiter', 'rpm', 'red'], ['Low RPM bogging', 'rpm', 'blue'],
      ['Hot tire temperature', 'temperature', 'orange'], ['Smashable collision', 'collision', 'yellow'], ['Solid impact (inferred)', 'collision', 'red'],
      ['Rewind', 'fast_rewind', 'blue'], ['Reset', 'history', 'neutral']
    ]);
  });

  it('defines the shared issue icon tone colors used by panels and canvas markers', () => {
    expect(issueIconToneColors).toEqual({
      green: '#22c55e',
      yellow: '#eab308',
      red: '#ef4444',
      blue: '#38bdf8',
      orange: '#f97316',
      purple: '#a78bfa',
      neutral: '#e4e4e7'
    });
    expect(issueIconToneColor('red')).toBe('#ef4444');
    expect(issueIconToneColor('neutral')).toBe('#e4e4e7');
    expect(issueIconToneColor('unknown' as never)).toBe('#e4e4e7');
  });

  it('uses icon names backed by Icon.svelte path data', () => {
    for (const definition of issueDefinitions) {
      expect(iconPaths[definition.icon]?.paths.length, definition.icon).toBeGreaterThan(0);
      expect(iconPaths[definition.icon]?.viewBox, definition.icon).toBeTruthy();
    }
    expect(iconPaths.overlayIssues.paths.length).toBeGreaterThan(0);
  });

  it('formats marker value details and falls back to threshold summaries', () => {
    expect(issueValueLine(makeMarker())).toBe('RPM ratio: 0.36 ≤ 0.40');
    expect(issueValueLine(makeMarker({ metric: 'collision_smashable_time_loss', issue_kind: 'Smashable collision', actual_value: 0.42, threshold_value: 0.2, threshold_operator: 'gte', value_label: 'Estimated time loss', value_unit: 's' }))).toBe('Estimated time loss: 0.42 ≥ 0.20 s');
    expect(issueValueLine(makeMarker({ metric: 'throttle_and_rear_slip', issue_kind: 'Traction-limited exit', actual_value: null, threshold_value: null, threshold_operator: null, value_label: null }))).toBe('Throttle ≥ 90, Rear slip ≥ 0.30');
    expect(issueValueLine(makeMarker({ metric: 'race.rewind', issue_kind: 'Rewind', actual_value: null, threshold_value: null, threshold_operator: null, value_label: null }))).toBe('Lap kept; route segment after the rewind point was trimmed.');
  });

  it('finds definitions by metric first and issue kind second', () => {
    expect(issueDefinitionForMarker(makeMarker({ metric: 'engine_rpm_and_throttle' })).issueKind).toBe('Low RPM bogging');
    expect(issueDefinitionForMarker(makeMarker({ metric: 'legacy_metric', issue_kind: 'Rev limiter' })).metric).toBe('engine_rpm');
    expect(issueIconForMarker(makeMarker({ metric: 'race.reset', issue_kind: 'Reset' }))).toBe('history');
  });

  it('uses the issues icon for unknown marker types', () => {
    const marker = makeMarker({ metric: 'custom_unknown', issue_kind: 'Custom unknown issue' });
    expect(issueIconForMarker(marker)).toBe('overlayIssues');
    expect(issueDefinitionForMarker(marker).issueKind).toBe('Custom unknown issue');
    expect(thresholdSummaryForDefinition(issueDefinitionForMarker(marker))).toBe('Threshold details unavailable');
  });
});
