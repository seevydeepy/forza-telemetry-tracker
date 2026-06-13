<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatNumber } from './dashboardFormat';
  import { gForceMagnitude } from './dashboardGeometry';
  import type { LiveSample } from './types';

  export let sample: LiveSample | null = null;
  $: gForce = gForceMagnitude(sample);
</script>

<DashboardCard title="Accelerometer / G-force">
  <div class="gforce-readout">
    <strong>{formatNumber(gForce, 2)} g</strong>
    <span>Total acceleration</span>
  </div>
  <dl>
    <div><dt>X</dt><dd>{formatNumber(sample?.acceleration_x, 2)} m/s²</dd></div>
    <div><dt>Y</dt><dd>{formatNumber(sample?.acceleration_y, 2)} m/s²</dd></div>
    <div><dt>Z</dt><dd>{formatNumber(sample?.acceleration_z, 2)} m/s²</dd></div>
    <div><dt>Velocity X</dt><dd>{formatNumber(sample?.velocity_x, 2)} m/s</dd></div>
    <div><dt>Velocity Y</dt><dd>{formatNumber(sample?.velocity_y, 2)} m/s</dd></div>
    <div><dt>Velocity Z</dt><dd>{formatNumber(sample?.velocity_z, 2)} m/s</dd></div>
  </dl>
</DashboardCard>

<style>
  .gforce-readout {
    background: radial-gradient(circle, rgb(37 99 235 / 28%), #111113 70%);
    border: 1px solid #3f3f46;
    border-radius: 1rem;
    display: grid;
    gap: 0.25rem;
    justify-items: center;
    margin-bottom: 0.75rem;
    padding: 1rem;
  }

  .gforce-readout strong {
    font-size: 2rem;
  }

  span,
  dt {
    color: var(--text-secondary);
  }

  dl {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
    margin: 0;
  }

  dd {
    font-weight: 700;
    margin: 0.1rem 0 0;
  }
</style>
