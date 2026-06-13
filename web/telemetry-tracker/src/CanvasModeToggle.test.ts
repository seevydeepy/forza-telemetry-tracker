import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import CanvasModeToggle from './CanvasModeToggle.svelte';

describe('CanvasModeToggle', () => {
  it('renders route mode as selected by default and dispatches dashboard selection', async () => {
    const change = vi.fn();
    render(CanvasModeToggle, { props: { mode: 'route' }, events: { change } });

    expect(screen.getByRole('group', { name: 'Canvas mode' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Route visualiser mode' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Telemetry dashboard mode' })).toHaveAttribute('aria-pressed', 'false');

    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));

    expect(change).toHaveBeenCalledTimes(1);
    expect(change.mock.calls[0][0].detail).toEqual({ mode: 'dashboard' });
  });

  it('does not dispatch when the selected mode is clicked again', async () => {
    const change = vi.fn();
    render(CanvasModeToggle, { props: { mode: 'dashboard' }, events: { change } });

    const dashboard = screen.getByRole('button', { name: 'Telemetry dashboard mode' });
    expect(dashboard).toHaveAttribute('aria-pressed', 'true');

    await fireEvent.click(dashboard);

    expect(change).not.toHaveBeenCalled();
  });
});
