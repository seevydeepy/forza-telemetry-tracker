import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import DashboardMiniRouteWidget from './DashboardMiniRouteWidget.svelte';
import { iconPaths } from './Icon.svelte';
import type { LiveSample } from './types';

function sample(overrides: Partial<LiveSample> = {}): LiveSample {
  return {
    sequence: 1,
    received_at_ms: 1,
    game_timestamp_ms: 1,
    lap_number: 1,
    current_lap: 0,
    current_race_time: 0,
    x: 0,
    y: 0,
    z: 0,
    speed_mps: 0,
    throttle: 0,
    brake: 0,
    steer: 0,
    gear: 1,
    ...overrides
  };
}

describe('DashboardMiniRouteWidget', () => {
  it('projects the route with the same z-axis orientation as the main route visualiser', () => {
    render(DashboardMiniRouteWidget, {
      props: {
        samples: [sample({ sequence: 1, x: 0, z: 0 }), sample({ sequence: 2, x: 10, z: 10 })],
        currentSample: sample({ sequence: 2, x: 10, z: 10 })
      }
    });

    const route = screen.getByRole('img', { name: 'Mini route' });
    expect(route.querySelector(':scope > path')).toHaveAttribute('d', 'M 0.0 130.0 L 220.0 0.0');
  });

  it('uses the shared navigation icon for the current player indicator', () => {
    render(DashboardMiniRouteWidget, {
      props: {
        samples: [sample({ sequence: 1, x: 0, z: 0 }), sample({ sequence: 2, x: 10, z: 10 })],
        currentSample: sample({ sequence: 2, x: 10, z: 10, yaw: Math.PI / 2 })
      }
    });

    const indicator = screen.getByLabelText('Current player position');
    expect(indicator).toHaveAttribute('transform', expect.stringContaining('rotate(90.0)'));
    expect(indicator.querySelector('path')).toHaveAttribute('d', iconPaths.navigation.paths[0]);
  });

  it('falls back to the projected route heading when the current sample has no yaw', () => {
    render(DashboardMiniRouteWidget, {
      props: {
        samples: [sample({ sequence: 1, x: 0, z: 0 }), sample({ sequence: 2, x: 10, z: 0 })],
        currentSample: sample({ sequence: 2, x: 10, z: 0 })
      }
    });

    expect(screen.getByLabelText('Current player position')).toHaveAttribute('transform', expect.stringContaining('rotate(90.0)'));
  });
});
