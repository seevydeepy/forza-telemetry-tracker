<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatInputPercent } from './dashboardFormat';
  import { normalizeGauge } from './dashboardGeometry';
  import type { LiveSample } from './types';

  export let sample: LiveSample | null = null;

  const rows = [
    { label: 'Throttle', key: 'throttle' },
    { label: 'Brake', key: 'brake' },
    { label: 'Clutch', key: 'clutch' },
    { label: 'Handbrake', key: 'handbrake' }
  ] as const;

  $: steeringPercent = normalizeGauge((sample?.steer ?? 0) + 127, 0, 254);
</script>

<DashboardCard title="Inputs / Steering">
  <div class="input-widget">
    <div class="steering" aria-label="Steering position">
      <span style={`left: ${steeringPercent * 100}%`}></span>
      <strong>Steer</strong>
      <em>{sample?.steer ?? '—'}</em>
    </div>
    {#each rows as row}
      {@const value = sample?.[row.key]}
      <div class="input-row">
        <span>{row.label}</span>
        <div class="input-bar" aria-label={`${row.label} ${formatInputPercent(value)}`}>
          <span style={`width: ${normalizeGauge(value, 0, 255) * 100}%`}></span>
        </div>
        <strong>{formatInputPercent(value)}</strong>
      </div>
    {/each}
  </div>
</DashboardCard>

<style>
  .input-widget {
    display: grid;
    gap: 0.65rem;
  }

  .steering {
    background: #111113;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    display: grid;
    grid-template-columns: 1fr auto;
    padding: 0.55rem 0.75rem;
    position: relative;
  }

  .steering span {
    background: #f4f4f5;
    border-radius: 999px;
    height: 1.4rem;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 0.4rem;
  }

  .steering strong,
  .steering em {
    position: relative;
  }

  .steering em {
    color: var(--text-secondary);
    font-style: normal;
  }

  .input-row {
    align-items: center;
    display: grid;
    gap: 0.6rem;
    grid-template-columns: 5.5rem minmax(0, 1fr) 3.5rem;
  }

  .input-row span {
    color: var(--text-secondary);
    font-size: 0.82rem;
  }

  .input-bar {
    background: #111113;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    height: 0.7rem;
    overflow: hidden;
  }

  .input-bar span {
    background: #60a5fa;
    display: block;
    height: 100%;
  }

  .input-row strong {
    text-align: right;
  }
</style>
