<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatNumber, formatTemperature } from './dashboardFormat';
  import { wheelTelemetry } from './dashboardGeometry';
  import type { LiveSample } from './types';

  export let sample: LiveSample | null = null;
  $: wheels = wheelTelemetry(sample);
</script>

<DashboardCard title="Tires" subtitle="Per-wheel grip, temperature, and surface state">
  <div class="wheel-grid">
    {#each wheels as wheel}
      <section class="wheel-tile">
        <h3>{wheel.label}</h3>
        <dl>
          <div><dt>Temp</dt><dd>{formatTemperature(wheel.tireTemp)}</dd></div>
          <div><dt>Slip ratio</dt><dd>{formatNumber(wheel.slipRatio, 2)}</dd></div>
          <div><dt>Slip angle</dt><dd>{formatNumber(wheel.slipAngle, 2)}</dd></div>
          <div><dt>Combined</dt><dd>{formatNumber(wheel.combinedSlip, 2)}</dd></div>
          <div><dt>Rotation</dt><dd>{formatNumber(wheel.rotationSpeed, 1)}</dd></div>
          <div><dt>Rumble</dt><dd>{wheel.onRumbleStrip ?? '—'}</dd></div>
          <div><dt>Puddle</dt><dd>{wheel.puddleDepth ?? '—'}</dd></div>
          <div><dt>Surface</dt><dd>{formatNumber(wheel.surfaceRumble, 2)}</dd></div>
        </dl>
      </section>
    {/each}
  </div>
</DashboardCard>

<style>
  .wheel-grid {
    display: grid;
    gap: 0.6rem;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .wheel-tile {
    background: #111113;
    border: 1px solid #27272a;
    border-radius: 0.8rem;
    padding: 0.65rem;
  }

  h3 {
    font-size: 0.82rem;
    margin: 0 0 0.5rem;
  }

  dl {
    display: grid;
    gap: 0.35rem;
    margin: 0;
  }

  div {
    display: flex;
    justify-content: space-between;
  }

  dt {
    color: var(--text-secondary);
  }

  dd {
    font-weight: 700;
    margin: 0;
  }
</style>
