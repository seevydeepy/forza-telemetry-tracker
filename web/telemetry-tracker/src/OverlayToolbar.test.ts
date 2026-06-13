import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import OverlayToolbar from './OverlayToolbar.svelte';

describe('OverlayToolbar', () => {
  it('renders the issues overlay summary as detectable issue types with icons and thresholds', () => {
    render(OverlayToolbar, { props: { selected: 'issues' } });

    const legend = screen.getByTestId('overlay-legend');
    expect(legend).toHaveTextContent('Issues');
    expect(legend).toHaveTextContent('Discrete issue markers show detected telemetry events. Hover an issue marker to inspect nearby issues; click to pin the popover.');
    expect(legend).toHaveTextContent('Rear combined slip');
    expect(legend).toHaveTextContent('Rear combined slip ≥ 1.15');
    expect(legend).toHaveTextContent('Braking instability');
    expect(legend).toHaveTextContent('Brake ≥ 80, Combined slip ≥ 0.35');
    expect(legend).toHaveTextContent('Traction-limited exit');
    expect(legend).toHaveTextContent('Throttle ≥ 90, Rear slip ≥ 0.30');
    expect(legend).toHaveTextContent('Suspension bottoming');
    expect(legend).toHaveTextContent('Compression ≥ 0.98');
    expect(legend).toHaveTextContent('Rev limiter');
    expect(legend).toHaveTextContent('RPM ratio ≥ 0.99; 3 contiguous samples');
    expect(legend).toHaveTextContent('Low RPM bogging');
    expect(legend).toHaveTextContent('Throttle ≥ 70, RPM ratio ≤ 0.40');
    expect(legend).toHaveTextContent('Hot tire temperature');
    expect(legend).toHaveTextContent('Tire temperature ≥ 105 °C');
    expect(legend).toHaveTextContent('Smashable collision');
    expect(legend).toHaveTextContent('Estimated time loss ≥ 0.20 s');
    expect(legend).toHaveTextContent('Solid impact (inferred)');
    expect(legend).toHaveTextContent('Estimated time loss ≥ 0.25 s');
    expect(legend).toHaveTextContent('Rewind');
    expect(legend).toHaveTextContent('Lap kept; route segment after the rewind point was trimmed.');
    expect(legend).toHaveTextContent('Reset');
    expect(legend).toHaveTextContent('Lap kept; route segment after the reset point was trimmed.');
    expect(legend.querySelectorAll('svg.app-icon').length).toBeGreaterThanOrEqual(11);
    expect(legend.querySelectorAll('.overlay-issue-definitions li').length).toBe(11);
    expect(legend.querySelectorAll('.issue-icon-tone-yellow').length).toBe(2);
    expect(legend.querySelectorAll('.issue-icon-tone-red').length).toBe(3);
    expect(legend.querySelectorAll('.issue-icon-tone-green').length).toBe(1);
    expect(legend.querySelectorAll('.issue-icon-tone-blue').length).toBe(2);
    expect(legend.querySelectorAll('.issue-icon-tone-neutral').length).toBe(1);
  });

  it('updates the legend when the selected overlay changes', async () => {
    const { rerender } = render(OverlayToolbar, { props: { selected: 'issues' } });

    await rerender({ selected: 'speed' });

    const legend = screen.getByTestId('overlay-legend');
    expect(legend).toHaveTextContent('Speed');
    expect(legend).toHaveTextContent('Red is slower, yellow is mid-range, green is faster for the loaded lap data.');
    expect(legend).toHaveTextContent('Slower');
    expect(legend).toHaveTextContent('Faster');
  });

  it('collapses the selected overlay info to only the selected overlay label', async () => {
    render(OverlayToolbar, { props: { selected: 'issues' } });

    const toggle = screen.getByRole('button', { name: 'Collapse selected overlay info for Issues' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await fireEvent.click(toggle);

    const legend = screen.getByTestId('overlay-legend');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(within(legend).getByText('Selected Overlay')).toBeInTheDocument();
    expect(within(legend).getByText('Issues')).toBeInTheDocument();
    expect(legend).not.toHaveTextContent('Discrete issue markers show detected telemetry events.');
    expect(legend).not.toHaveTextContent('Detected issue types');
    expect(legend).not.toHaveTextContent('Rear combined slip');
    expect(legend.querySelectorAll('.overlay-issue-definitions li').length).toBe(0);

    await fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(legend).toHaveTextContent('Discrete issue markers show detected telemetry events.');
    expect(legend).toHaveTextContent('Detected issue types');
    expect(legend.querySelectorAll('.overlay-issue-definitions li').length).toBe(11);
  });

  it('keeps the collapsed overlay label current when the selected overlay changes', async () => {
    const { rerender } = render(OverlayToolbar, { props: { selected: 'issues' } });

    await fireEvent.click(screen.getByRole('button', { name: 'Collapse selected overlay info for Issues' }));
    await rerender({ selected: 'speed' });

    const legend = screen.getByTestId('overlay-legend');
    expect(screen.getByRole('button', { name: 'Expand selected overlay info for Speed' })).toHaveAttribute('aria-expanded', 'false');
    expect(within(legend).getByText('Selected Overlay')).toBeInTheDocument();
    expect(within(legend).getByText('Speed')).toBeInTheDocument();
    expect(within(legend).queryByText('Issues')).not.toBeInTheDocument();
    expect(legend).not.toHaveTextContent('Red is slower, yellow is mid-range, green is faster for the loaded lap data.');
  });

  it('shows only the selected overlay legend content', async () => {
    const { rerender } = render(OverlayToolbar, { props: { selected: 'issues' } });

    expect(screen.getByTestId('overlay-legend')).toHaveTextContent('Discrete issue markers');
    expect(screen.queryByText('Green shows throttle-dominant segments.')).not.toBeInTheDocument();

    await rerender({ selected: 'inputs' });

    const legend = screen.getByTestId('overlay-legend');
    expect(legend).toHaveTextContent('Inputs');
    expect(legend).toHaveTextContent('Green shows throttle-dominant segments. Red shows brake-dominant segments. Intensity reflects input strength.');
    expect(screen.queryByText('Issue severity colours highlight detected problem areas.')).not.toBeInTheDocument();
    expect(screen.queryByText('Severity')).not.toBeInTheDocument();
  });

  it('disables unavailable overlays with an explanatory tooltip', async () => {
    const change = vi.fn();
    render(OverlayToolbar, {
      props: {
        selected: 'speed',
        disabledOverlays: ['issues'],
        disabledReasons: {
          issues: 'Issues overlay is only available for completed laps.'
        }
      },
      events: { change }
    });

    const issues = screen.getByRole('button', { name: 'Issues' });
    expect(issues).toBeDisabled();
    expect(issues).toHaveAttribute('title', 'Issues overlay is only available for completed laps.');

    await fireEvent.click(issues);

    expect(change).not.toHaveBeenCalled();
  });
});
