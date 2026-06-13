import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import StatsModal from './StatsModal.svelte';
import type { StatsSummary } from './types';

const statsFixture: StatsSummary = {
  laps_recorded: 12,
  sessions_created: 4,
  tracks_driven: 3,
  cars_driven: 2,
  max_speed_mps: 44.704,
  favourite_car: {
    value: 'Mazda Furai',
    lap_count: 7,
    session_count: 2
  },
  favourite_track: {
    value: 'Emerald Circuit',
    detail: 'Full',
    lap_count: 5,
    session_count: 2
  },
  favourite_pi_class: {
    value: 'S1',
    lap_count: 9,
    session_count: 3
  },
  favoured_drive: {
    value: 'RWD',
    lap_count: 8,
    session_count: 3
  },
  time_spent_racing_ms: 3_661_000
};

function renderStatsModal(
  props: Partial<{ stats: StatsSummary | null; unitSystem: 'imperial' | 'metric'; loading: boolean; error: string | null }> = {}
) {
  const close = vi.fn();
  const result = render(StatsModal, {
    props: {
      stats: statsFixture,
      unitSystem: 'imperial',
      ...props
    },
    events: { close }
  });

  return { close, ...result };
}

function expectCard(label: string, value: string, detail?: string) {
  const card = screen.getByRole('group', { name: label });
  expect(within(card).getByText(label)).toBeInTheDocument();
  expect(within(card).getByText(value)).toBeInTheDocument();
  if (detail) {
    expect(within(card).getByText(detail)).toBeInTheDocument();
  }
}

describe('StatsModal', () => {
  it('renders the approved stat cards with imperial speed formatting', () => {
    renderStatsModal();

    expect(screen.getByRole('dialog', { name: 'Stats' })).toBeInTheDocument();
    const cards = screen.getAllByRole('group');
    expect(cards).toHaveLength(10);
    expectCard('Laps recorded', '12');
    expectCard('Sessions created', '4');
    expectCard('Tracks driven', '3');
    expectCard('Cars driven', '2');
    expectCard('Max speed', '100 mph');
    expectCard('Favourite car', 'Mazda Furai', '7 laps');
    expectCard('Favourite track', 'Emerald Circuit', 'Full · 5 laps');
    expectCard('Favourite PI class', 'S1', '9 laps');
    expectCard('Favoured drive', 'RWD', '8 laps');
    expectCard('Lifetime Telemetry Recorded', '1h 01m 01s');
  });

  it('renders missing favourites, missing speed, and zero racing time', () => {
    renderStatsModal({
      stats: {
        ...statsFixture,
        tracks_driven: 0,
        cars_driven: 0,
        max_speed_mps: null,
        favourite_car: null,
        favourite_track: null,
        favourite_pi_class: null,
        favoured_drive: null,
        time_spent_racing_ms: 0
      }
    });

    expectCard('Tracks driven', '0');
    expectCard('Cars driven', '0');
    expectCard('Max speed', '—');
    expectCard('Favourite car', '—');
    expectCard('Favourite track', '—');
    expectCard('Favourite PI class', '—');
    expectCard('Favoured drive', '—');
    expectCard('Lifetime Telemetry Recorded', '0s');
  });

  it('updates max speed when the unit system changes for the same stats object', async () => {
    const { rerender } = renderStatsModal({ stats: statsFixture, unitSystem: 'imperial' });
    expectCard('Max speed', '100 mph');

    await rerender({ stats: statsFixture, unitSystem: 'metric' });
    expectCard('Max speed', '161 km/h');
    expect(screen.queryByText('100 mph')).not.toBeInTheDocument();
  });

  it('renders the empty state when no stats have been recorded', () => {
    renderStatsModal({ stats: null });

    expect(screen.getByText('No recorded stats yet.')).toBeInTheDocument();
  });

  it('renders loading and error states', async () => {
    const { rerender } = renderStatsModal({ stats: null, loading: true });
    expect(screen.getByText('Loading stats…')).toBeInTheDocument();

    await rerender({ stats: null, loading: false, error: 'database unavailable' });
    expect(screen.getByText('Unable to load stats')).toBeInTheDocument();
    expect(screen.getByText('database unavailable')).toBeInTheDocument();
  });

  it('omits intro copy and manual refresh while still dispatching close events', async () => {
    const { close } = renderStatsModal();

    expect(screen.queryByText('Lifetime telemetry totals and favourites from recorded laps.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Refresh stats' })).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Close Stats' }));
    expect(close).toHaveBeenCalledTimes(1);
  });
});
