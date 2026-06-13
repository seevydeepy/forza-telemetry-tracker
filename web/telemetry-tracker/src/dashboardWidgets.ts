import type { DashboardWidgetId } from './types';

export interface DashboardWidgetDefinition {
  id: DashboardWidgetId;
  label: string;
}

export const DASHBOARD_WIDGETS: DashboardWidgetDefinition[] = [
  { id: 'tachSpeedGear', label: 'Tach / Speed / Gear' },
  { id: 'inputsSteering', label: 'Inputs / Steering' },
  { id: 'tires', label: 'Tires' },
  { id: 'suspensionAttitude', label: 'Suspension / Attitude' },
  { id: 'accelerometer', label: 'Accelerometer / G-force' },
  { id: 'lapTiming', label: 'Lap timing' },
  { id: 'miniRoute', label: 'Mini route' },
  { id: 'fuelRaceInfo', label: 'Fuel / Race info' },
  { id: 'carDetails', label: 'Car details' }
];

export function defaultDashboardWidgetVisibility(): Record<DashboardWidgetId, boolean> {
  return Object.fromEntries(DASHBOARD_WIDGETS.map((widget) => [widget.id, true])) as Record<DashboardWidgetId, boolean>;
}
