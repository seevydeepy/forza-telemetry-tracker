import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import IssuePopover from './IssuePopover.svelte';
import type { IssuePopoverItem } from './IssuePopover.svelte';
import type { IssueMarker, LiveSample } from './types';

function makeMarker(overrides: Partial<IssueMarker> = {}): IssueMarker {
  return {
    id: 'issue-1',
    session_id: 'session-a',
    lap_id: 'lap-a',
    start_sequence: 11,
    end_sequence: 12,
    metric: 'engine_rpm_and_throttle',
    severity: 'warning',
    reason: 'The engine is on throttle but not pulling strongly, suggesting bogging.',
    ruleset_version: 2,
    confidence: 0.82,
    anchor_sequence: 11,
    issue_kind: 'Low RPM bogging',
    actual_value: 0.36,
    threshold_value: 0.4,
    threshold_operator: 'lte',
    value_label: 'RPM ratio',
    value_unit: null,
    ...overrides
  };
}

function makeSample(overrides: Partial<LiveSample> = {}): LiveSample {
  return {
    sequence: 11,
    received_at_ms: 11,
    game_timestamp_ms: 11,
    lap_number: 2,
    current_lap: 68.104,
    current_race_time: 120,
    x: 5,
    y: 0,
    z: 5,
    speed_mps: 32.25,
    throttle: 150,
    brake: 0,
    steer: 0,
    gear: 3,
    ...overrides
  };
}

function makeItem(overrides: Partial<IssueMarker> = {}, elapsedMs = 68104): IssuePopoverItem {
  return { marker: makeMarker(overrides), sample: makeSample({ sequence: overrides.anchor_sequence ?? 11 }), elapsedMs };
}

describe('IssuePopover', () => {
  it('renders one icon-led issue row without opinionated reason copy', () => {
    render(IssuePopover, { items: [makeItem()], pinned: false });

    expect(screen.getByRole('dialog', { name: 'Issue details' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Low RPM bogging at 1:08.104' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Drag issue popover' })).toBeInTheDocument();
    expect(screen.getByText('Hover issue details · click an issue marker to pin')).toBeInTheDocument();
    expect(screen.getByText('RPM ratio: 0.36 ≤ 0.40')).toBeInTheDocument();
    expect(screen.getByLabelText('Low RPM bogging issue icon')).toBeInTheDocument();
    expect(screen.queryByText('The engine is on throttle but not pulling strongly, suggesting bogging.')).not.toBeInTheDocument();
    expect(document.querySelector('.popover-backdrop')).not.toBeInTheDocument();
  });

  it('falls back when value details are unavailable', () => {
    render(IssuePopover, {
      items: [makeItem({ actual_value: null, threshold_value: null, threshold_operator: null, value_label: null })],
      pinned: false
    });

    expect(screen.getByRole('heading', { name: 'Low RPM bogging at 1:08.104' })).toBeInTheDocument();
    expect(screen.getByText('Throttle ≥ 70, RPM ratio ≤ 0.40')).toBeInTheDocument();
  });

  it('renders multiple nearby issues in a single scrollable body', () => {
    render(IssuePopover, {
      items: [
        makeItem({ id: 'rear-slip', metric: 'rear_combined_slip', issue_kind: 'Rear combined slip', actual_value: 1.28, threshold_value: 1.15, threshold_operator: 'gte', value_label: 'Rear combined slip' }, 12000),
        makeItem({ id: 'hot-tire', metric: 'tire_temperature', issue_kind: 'Hot tire temperature', actual_value: 108, threshold_value: 105, threshold_operator: 'gte', value_label: 'Tire temperature', value_unit: '°C' }, 12100),
        makeItem({ id: 'collision', metric: 'collision_smashable_time_loss', issue_kind: 'Smashable collision', actual_value: 0.42, threshold_value: 0.2, threshold_operator: 'gte', value_label: 'Estimated time loss', value_unit: 's' }, 12200)
      ],
      pinned: true
    });

    expect(screen.getByRole('heading', { name: '3 issues near 0:12.000' })).toBeInTheDocument();
    expect(screen.getByText(/Pinned/)).toBeInTheDocument();
    expect(screen.getByText('Rear combined slip')).toBeInTheDocument();
    expect(screen.getByText('Tire temperature: 108 ≥ 105 °C')).toBeInTheDocument();
    expect(screen.getByText('Estimated time loss: 0.42 ≥ 0.20 s')).toBeInTheDocument();
    expect(screen.getByTestId('issue-popover-list')).toHaveClass('issue-list');
  });

  it('emits close from the close button', async () => {
    const close = vi.fn();
    render(IssuePopover, {
      props: { items: [makeItem()], pinned: false },
      events: { close }
    });

    const closeButton = screen.getByRole('button', { name: 'Close issue popover' });
    expect(closeButton).toHaveAttribute('title', 'Close issue popover');
    await fireEvent.click(closeButton);

    expect(close).toHaveBeenCalledTimes(1);
  });

  it('emits move deltas while dragging the header', async () => {
    const move = vi.fn();
    render(IssuePopover, {
      props: { items: [makeItem()], pinned: false, x: 20, y: 30 },
      events: { move }
    });

    const header = screen.getByRole('button', { name: 'Drag issue popover' });
    expect(header).not.toBeNull();

    await fireEvent.mouseDown(header, {
      button: 0,
      clientX: 20,
      clientY: 20
    });
    await fireEvent.mouseMove(window, { clientX: 50, clientY: 60 });
    await fireEvent.mouseUp(window);

    expect(move).toHaveBeenCalledWith(expect.objectContaining({ detail: { x: 50, y: 70 } }));
  });
});
