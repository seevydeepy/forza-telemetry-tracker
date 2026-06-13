import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import TelemetryDashboard from './TelemetryDashboard.svelte';
import { defaultDashboardWidgetVisibility } from './dashboardWidgets';
import type { CarInfo, DashboardWidgetId, LiveSample } from './types';

function sample(overrides: Partial<LiveSample> = {}): LiveSample {
  return {
    sequence: 1,
    received_at_ms: 1,
    game_timestamp_ms: 1,
    is_race_on: true,
    lap_number: 2,
    current_lap: 12.345,
    current_race_time: 72.345,
    x: 0,
    y: 0,
    z: 0,
    speed_mps: 44.704,
    throttle: 128,
    brake: 64,
    steer: 0,
    gear: 4,
    current_rpm: 7250,
    engine_max_rpm: 9000,
    engine_idle_rpm: 900,
    power_w: 372850,
    torque_nm: 500,
    boost_bar: 1.23,
    acceleration_x: 9.80665,
    acceleration_y: 0,
    acceleration_z: 0,
    yaw: Math.PI / 2,
    tire_temp_front_left: 91,
    tire_slip_ratio_front_left: 0.2,
    suspension_travel_front_left: 0.4,
    fuel: 0.625,
    race_position: 1,
    ...overrides
  };
}

const car: CarInfo = {
  ordinal: 1229,
  name: 'Mazda Furai',
  display_name: 'Furai',
  model_short: 'Mazda Furai',
  year: 2008,
  class_id: 6,
  class_label: 'R',
  performance_index: 998,
  drivetrain_id: 1,
  drivetrain_label: 'RWD',
  catalog_source: 'test',
  catalog: null,
  details: {
    num_cylinders: 3,
    car_group: 26,
    car_group_label: 'Extreme Track Toys',
    engine_max_rpm: 9999.995,
    peak_power_w: 331000,
    average_power_w: 300000,
    peak_torque_nm: 392,
    average_torque_nm: 350,
    peak_boost_bar: 0,
    fuel: 0.75
  }
};

function hiddenVisibility(): Record<DashboardWidgetId, boolean> {
  return Object.fromEntries(Object.keys(defaultDashboardWidgetVisibility()).map((id) => [id, false])) as Record<DashboardWidgetId, boolean>;
}

describe('TelemetryDashboard', () => {
  it('renders the dashboard widget grid with current sample and car details', () => {
    render(TelemetryDashboard, {
      props: {
        samples: [sample({ sequence: 1, x: 0, z: 0 }), sample({ sequence: 2, x: 10, z: 10 })],
        currentSample: sample({ sequence: 2, x: 10, z: 10 }),
        carInfo: car,
        unitSystem: 'imperial',
        enabledWidgets: defaultDashboardWidgetVisibility()
      }
    });

    const dashboard = screen.getByRole('region', { name: 'Telemetry dashboard canvas' });
    expect(dashboard).toBeInTheDocument();
    expect(within(dashboard).getByRole('region', { name: 'Tach / Speed / Gear' })).toHaveTextContent('100 mph');
    expect(within(dashboard).getByRole('region', { name: 'Inputs / Steering' })).toHaveTextContent('Throttle');
    expect(within(dashboard).getByRole('region', { name: 'Tires' })).toHaveTextContent('Front left');
    const carDetails = within(dashboard).getByRole('region', { name: 'Car details' });
    expect(carDetails).toHaveTextContent('Mazda Furai');
    const performance = within(carDetails).getByLabelText('Performance R | 998');
    expect(performance).toHaveClass('car-info-card__performance');
    expect(performance).toHaveAttribute('data-car-performance-class', 'R');
    expect(within(performance).getByText('R')).toHaveClass('car-info-card__class-label');
    expect(within(performance).getByText('998')).toHaveClass('car-info-card__pi-label');
    expect(carDetails).toHaveTextContent('Extreme Track Toys');
    expect(carDetails).not.toHaveTextContent('Fuel');
  });

  it('hides disabled widgets while keeping the rest of the grid visible', () => {
    const enabledWidgets = { ...defaultDashboardWidgetVisibility(), tires: false, carDetails: false };
    render(TelemetryDashboard, {
      props: {
        samples: [sample()],
        currentSample: sample(),
        carInfo: car,
        unitSystem: 'imperial',
        enabledWidgets
      }
    });

    expect(screen.getByTestId('dashboard-widget-grid')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Tires' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Car details' })).toBeNull();
    expect(screen.getByRole('region', { name: 'Tach / Speed / Gear' })).toBeInTheDocument();
  });

  it('shows an empty state and emits showall when every widget is hidden', async () => {
    const showall = vi.fn();
    render(TelemetryDashboard, {
      props: {
        samples: [sample()],
        currentSample: sample(),
        carInfo: car,
        unitSystem: 'imperial',
        enabledWidgets: hiddenVisibility()
      },
      events: { showall }
    });

    expect(screen.getByText('No dashboard widgets are visible')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Show all widgets' }));

    expect(showall).toHaveBeenCalledTimes(1);
  });
});
