import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import DashboardPlaybackBar from './DashboardPlaybackBar.svelte';
import type { LiveSample } from './types';

function sample(sequence: number, overrides: Partial<LiveSample> = {}): LiveSample {
  return {
    sequence,
    received_at_ms: sequence * 500,
    game_timestamp_ms: sequence * 500,
    is_race_on: true,
    lap_number: 3,
    current_lap: sequence / 10,
    current_race_time: sequence / 10,
    x: sequence,
    y: 0,
    z: sequence,
    speed_mps: 10,
    throttle: 255,
    brake: 0,
    steer: 0,
    gear: 2,
    ...overrides
  };
}

describe('DashboardPlaybackBar', () => {
  it('dispatches play and scrub events for selected-lap playback', async () => {
    const play = vi.fn();
    const pause = vi.fn();
    const scrub = vi.fn();
    const samples = [sample(1), sample(2), sample(3)];
    render(DashboardPlaybackBar, {
      props: {
        source: 'lap',
        samples,
        currentSample: samples[1],
        currentIndex: 1,
        currentTimeMs: 500,
        durationMs: 1000,
        currentElapsedMs: 12345,
        durationElapsedMs: 67890,
        progress: 0.25,
        playing: false
      },
      events: { play, pause, scrub }
    });

    const region = screen.getByRole('region', { name: 'Dashboard playback' });
    expect(region).toHaveTextContent('Selected lap playback');
    expect(region).toHaveTextContent('Sample 2 of 3');
    expect(region).toHaveTextContent('0:12.345 / 1:07.890');
    expect(region).toHaveTextContent('25.0%');

    await fireEvent.click(within(region).getByRole('button', { name: 'Play dashboard playback' }));
    await fireEvent.input(within(region).getByRole('slider', { name: 'Scrub selected lap dashboard playback' }), { target: { value: '750' } });

    expect(play).toHaveBeenCalledTimes(1);
    expect(pause).not.toHaveBeenCalled();
    expect(scrub).toHaveBeenCalledTimes(1);
    expect(scrub.mock.calls[0][0].detail).toEqual({ timeMs: 750 });
  });

  it('dispatches pause when playback is already running', async () => {
    const pause = vi.fn();
    render(DashboardPlaybackBar, {
      props: {
        source: 'lap',
        samples: [sample(1)],
        currentSample: sample(1),
        currentIndex: 0,
        currentTimeMs: 0,
        durationMs: 0,
        playing: true
      },
      events: { pause }
    });

    await fireEvent.click(screen.getByRole('button', { name: 'Pause dashboard playback' }));

    expect(pause).toHaveBeenCalledTimes(1);
  });

  it('shows live dashboard status without historical scrub controls', () => {
    render(DashboardPlaybackBar, {
      props: {
        source: 'live',
        samples: [sample(1), sample(2)],
        currentSample: sample(2, { lap_number: 4, current_lap: 12.345 }),
        currentIndex: 1,
        currentTimeMs: 0,
        durationMs: 0,
        playing: false
      }
    });

    const region = screen.getByRole('region', { name: 'Dashboard playback' });
    expect(region).toHaveTextContent('Live dashboard');
    expect(region).toHaveTextContent('2 samples');
    expect(region).toHaveTextContent('Lap 4');
    expect(region).toHaveTextContent('0:12.345');
    expect(within(region).queryByRole('slider', { name: 'Scrub selected lap dashboard playback' })).toBeNull();
  });
});
