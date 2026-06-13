import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import DashboardWidgetVisibilityPopover from './DashboardWidgetVisibilityPopover.svelte';
import { defaultDashboardWidgetVisibility } from './dashboardWidgets';

describe('DashboardWidgetVisibilityPopover', () => {
  it('opens widget toggles and dispatches toggle and show-all actions', async () => {
    const toggle = vi.fn();
    const showall = vi.fn();
    render(DashboardWidgetVisibilityPopover, {
      props: { enabledWidgets: defaultDashboardWidgetVisibility() },
      events: { toggle, showall }
    });

    await fireEvent.click(screen.getByRole('button', { name: 'Choose dashboard widgets' }));

    const popover = screen.getByRole('region', { name: 'Dashboard widget visibility' });
    expect(popover).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Tach \/ Speed \/ Gear/ })).toHaveAttribute('aria-pressed', 'true');

    await fireEvent.click(screen.getByRole('button', { name: /Tach \/ Speed \/ Gear/ }));
    await fireEvent.click(screen.getByRole('button', { name: 'Show all' }));

    expect(toggle).toHaveBeenCalledTimes(1);
    expect(toggle.mock.calls[0][0].detail).toEqual({ widgetId: 'tachSpeedGear' });
    expect(showall).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape and restores focus to the eye button', async () => {
    render(DashboardWidgetVisibilityPopover, { props: { enabledWidgets: defaultDashboardWidgetVisibility() } });
    const chooser = screen.getByRole('button', { name: 'Choose dashboard widgets' });

    await fireEvent.click(chooser);
    expect(chooser).toHaveAttribute('aria-controls', 'dashboard-widget-visibility-popover');
    expect(screen.getByRole('region', { name: 'Dashboard widget visibility' })).toBeInTheDocument();

    await fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('region', { name: 'Dashboard widget visibility' })).not.toBeInTheDocument());
    await waitFor(() => expect(chooser).toHaveFocus());
  });

  it('closes when clicking outside the popover', async () => {
    render(DashboardWidgetVisibilityPopover, { props: { enabledWidgets: defaultDashboardWidgetVisibility() } });

    await fireEvent.click(screen.getByRole('button', { name: 'Choose dashboard widgets' }));
    expect(screen.getByRole('region', { name: 'Dashboard widget visibility' })).toBeInTheDocument();

    await fireEvent.click(document.body);

    expect(screen.queryByRole('region', { name: 'Dashboard widget visibility' })).not.toBeInTheDocument();
  });
});
