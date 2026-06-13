<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatNumber, formatTime } from './dashboardFormat';
  import type { LiveSample } from './types';

  export let sample: LiveSample | null = null;
</script>

<DashboardCard title="Lap timing">
  <dl class="timing-grid">
    <div><dt>Lap</dt><dd>{sample?.lap_number ?? '—'}</dd></div>
    <div><dt>Current lap</dt><dd>{formatTime(sample?.current_lap)}</dd></div>
    <div><dt>Race time</dt><dd>{formatTime(sample?.current_race_time)}</dd></div>
    <div><dt>Best lap</dt><dd>{formatTime(sample?.best_lap)}</dd></div>
    <div><dt>Last lap</dt><dd>{formatTime(sample?.last_lap)}</dd></div>
    <div><dt>Distance</dt><dd>{formatNumber(sample?.distance_traveled_m, 1)} m</dd></div>
  </dl>
</DashboardCard>

<style>
  .timing-grid {
    display: grid;
    gap: 0.65rem;
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
    margin: 0;
  }

  .timing-grid div {
    background: #111113;
    border: 1px solid #27272a;
    border-radius: 0.75rem;
    padding: 0.65rem;
  }

  dt {
    color: var(--text-secondary);
    font-size: 0.78rem;
  }

  dd {
    font-size: 1.05rem;
    font-weight: 800;
    margin: 0.15rem 0 0;
  }
</style>
