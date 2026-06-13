<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatFuel, formatInputPercent } from './dashboardFormat';
  import type { LiveSample } from './types';

  export let sample: LiveSample | null = null;
</script>

<DashboardCard title="Fuel / Race info">
  <dl class="race-grid">
    <div><dt>Fuel</dt><dd>{formatFuel(sample?.fuel)}</dd></div>
    <div><dt>Position</dt><dd>{sample?.race_position ?? '—'}</dd></div>
    <div><dt>Race on</dt><dd>{sample?.is_race_on === undefined ? '—' : sample.is_race_on ? 'Yes' : 'No'}</dd></div>
    <div><dt>Driving line</dt><dd>{formatInputPercent(sample?.normalized_driving_line, 127)}</dd></div>
    <div><dt>AI brake diff</dt><dd>{sample?.normalized_ai_brake_difference ?? '—'}</dd></div>
  </dl>
</DashboardCard>

<style>
  .race-grid {
    display: grid;
    gap: 0.65rem;
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
    margin: 0;
  }

  .race-grid div {
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
