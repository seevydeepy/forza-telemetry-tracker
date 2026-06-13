<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatDegrees, formatNumber } from './dashboardFormat';
  import { attitudeDegrees, wheelTelemetry } from './dashboardGeometry';
  import type { LiveSample } from './types';

  export let sample: LiveSample | null = null;
  $: wheels = wheelTelemetry(sample);
  $: attitude = attitudeDegrees(sample);
</script>

<DashboardCard title="Suspension / Attitude">
  <div class="metric-grid">
    <div><span>Yaw</span><strong>{attitude.yaw === null ? '—' : `${attitude.yaw}°`}</strong></div>
    <div><span>Pitch</span><strong>{attitude.pitch === null ? '—' : `${attitude.pitch}°`}</strong></div>
    <div><span>Roll</span><strong>{attitude.roll === null ? '—' : `${attitude.roll}°`}</strong></div>
    <div><span>Angular X</span><strong>{formatDegrees(sample?.angular_velocity_x)}</strong></div>
    <div><span>Angular Y</span><strong>{formatDegrees(sample?.angular_velocity_y)}</strong></div>
    <div><span>Angular Z</span><strong>{formatDegrees(sample?.angular_velocity_z)}</strong></div>
  </div>
  <div class="suspension-list">
    {#each wheels as wheel}
      <div>
        <span>{wheel.label}</span>
        <strong>{formatNumber(wheel.suspensionTravel, 2)}</strong>
        <em>{formatNumber(wheel.suspensionTravelMeters, 3)} m</em>
      </div>
    {/each}
  </div>
</DashboardCard>

<style>
  .metric-grid {
    display: grid;
    gap: 0.6rem;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric-grid div,
  .suspension-list div {
    background: #111113;
    border: 1px solid #27272a;
    border-radius: 0.75rem;
    display: grid;
    gap: 0.15rem;
    padding: 0.6rem;
  }

  span,
  em {
    color: var(--text-secondary);
    font-size: 0.78rem;
    font-style: normal;
  }

  strong {
    font-size: 1rem;
  }

  .suspension-list {
    display: grid;
    gap: 0.55rem;
    margin-top: 0.75rem;
  }
</style>
