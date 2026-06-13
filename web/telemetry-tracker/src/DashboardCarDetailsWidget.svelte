<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatBoost, formatPower, formatRpm, formatTorque } from './dashboardFormat';
  import type { CarInfo } from './types';

  export let car: CarInfo | null = null;

  function value(value: string | number | null | undefined): string {
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }

  function normalizePerformanceClass(label: string | null | undefined) {
    const normalized = label?.trim().toUpperCase();
    return normalized && ['D', 'C', 'B', 'A', 'S1', 'S2', 'R', 'X'].includes(normalized) ? normalized : 'unknown';
  }

  $: performanceClassLabel = car?.class_label ?? '--';
  $: performanceIndexLabel = car?.performance_index ?? '---';
  $: performanceText = `${performanceClassLabel} | ${performanceIndexLabel}`;
  $: performanceClassKey = normalizePerformanceClass(car?.class_label);
</script>

<DashboardCard title="Car details" subtitle={car?.drivetrain_label ?? ''}>
  <div class="car-details">
    <header>
      <strong>{car?.name ?? 'Unknown car'}</strong>
      <div class="car-info-card__performance" aria-label={`Performance ${performanceText}`} data-car-performance-class={performanceClassKey}>
        <span class="car-info-card__class-label">{performanceClassLabel}</span>
        <span class="car-info-card__performance-separator" aria-hidden="true"> | </span>
        <span class="car-info-card__pi-label">{performanceIndexLabel}</span>
      </div>
    </header>
    <dl>
      <div><dt>Year</dt><dd>{value(car?.year)}</dd></div>
      <div><dt>Ordinal</dt><dd>{value(car?.ordinal)}</dd></div>
      <div><dt>Drivetrain</dt><dd>{value(car?.drivetrain_label)}</dd></div>
      <div><dt>Car group</dt><dd>{value(car?.details.car_group_label ?? car?.details.car_group)}</dd></div>
      <div><dt>Cylinders</dt><dd>{value(car?.details.num_cylinders)}</dd></div>
      <div><dt>Engine max</dt><dd>{formatRpm(car?.details.engine_max_rpm)}</dd></div>
      <div><dt>Power</dt><dd>{formatPower(car?.details.peak_power_w)}</dd></div>
      <div><dt>Torque</dt><dd>{formatTorque(car?.details.peak_torque_nm)}</dd></div>
      <div><dt>Boost</dt><dd>{formatBoost(car?.details.peak_boost_bar)}</dd></div>
    </dl>
  </div>
</DashboardCard>

<style>
  .car-details {
    --car-info-scale: 0.72;
    display: grid;
    gap: 0.75rem;
  }

  header {
    align-items: start;
    display: grid;
    gap: 0.65rem;
    grid-template-columns: minmax(0, 1fr) auto;
  }

  header strong {
    font-size: 1.45rem;
    line-height: 1.05;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  dt {
    color: var(--text-secondary);
  }

  header :global(.car-info-card__performance) {
    margin-top: 0.1rem;
  }

  dl {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
    margin: 0;
  }

  dd {
    font-weight: 750;
    margin: 0.1rem 0 0;
  }
</style>
