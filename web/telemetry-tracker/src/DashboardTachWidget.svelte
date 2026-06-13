<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { formatBoost, formatPower, formatRpm, formatSpeed, formatTorque } from './dashboardFormat';
  import { normalizeGauge, rpmGaugeColor } from './dashboardGeometry';
  import type { LiveSample, UnitSystem } from './types';

  export let sample: LiveSample | null = null;
  export let unitSystem: UnitSystem = 'imperial';

  $: rpmPercent = normalizeGauge(sample?.current_rpm, sample?.engine_idle_rpm ?? 0, sample?.engine_max_rpm ?? 1);
  $: rpmColor = rpmGaugeColor(rpmPercent);
  $: gearLabel = sample ? (sample.gear === 0 ? 'N' : String(sample.gear)) : '—';
</script>

<DashboardCard title="Tach / Speed / Gear" subtitle={formatSpeed(sample?.speed_mps, unitSystem)}>
  <div class="tach-widget">
    <div class="tach-widget__speed">{formatSpeed(sample?.speed_mps, unitSystem)}</div>
    <div class="tach-widget__gear" aria-label="Gear">{gearLabel}</div>
    <div class="tach-widget__bar" aria-label="RPM gauge">
      <span style={`width: ${rpmPercent * 100}%; background: ${rpmColor}`}></span>
    </div>
    <dl>
      <div><dt>RPM</dt><dd>{formatRpm(sample?.current_rpm)}</dd></div>
      <div><dt>Max</dt><dd>{formatRpm(sample?.engine_max_rpm)}</dd></div>
      <div><dt>Power</dt><dd>{formatPower(sample?.power_w)}</dd></div>
      <div><dt>Torque</dt><dd>{formatTorque(sample?.torque_nm)}</dd></div>
      <div><dt>Boost</dt><dd>{formatBoost(sample?.boost_bar)}</dd></div>
    </dl>
  </div>
</DashboardCard>

<style>
  .tach-widget {
    display: grid;
    gap: 0.75rem;
  }

  .tach-widget__speed {
    font-size: clamp(2rem, 5vw, 4rem);
    font-weight: 850;
    letter-spacing: -0.07em;
    line-height: 0.95;
  }

  .tach-widget__gear {
    align-items: center;
    background: #27272a;
    border: 1px solid #52525b;
    border-radius: 0.8rem;
    display: inline-flex;
    font-size: 2rem;
    font-weight: 900;
    height: 4rem;
    justify-content: center;
    justify-self: start;
    width: 4rem;
  }

  .tach-widget__bar {
    background: #111113;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    height: 0.85rem;
    overflow: hidden;
  }

  .tach-widget__bar span {
    display: block;
    height: 100%;
  }

  dl {
    display: grid;
    gap: 0.45rem;
    grid-template-columns: repeat(auto-fit, minmax(6.5rem, 1fr));
    margin: 0;
  }

  dt {
    color: var(--text-secondary);
    font-size: 0.72rem;
    text-transform: uppercase;
  }

  dd {
    font-weight: 750;
    margin: 0.1rem 0 0;
  }
</style>
