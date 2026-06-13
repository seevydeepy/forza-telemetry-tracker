<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import DashboardAccelerometerWidget from './DashboardAccelerometerWidget.svelte';
  import DashboardCarDetailsWidget from './DashboardCarDetailsWidget.svelte';
  import DashboardFuelRaceWidget from './DashboardFuelRaceWidget.svelte';
  import DashboardInputsWidget from './DashboardInputsWidget.svelte';
  import DashboardLapTimingWidget from './DashboardLapTimingWidget.svelte';
  import DashboardMiniRouteWidget from './DashboardMiniRouteWidget.svelte';
  import DashboardSuspensionWidget from './DashboardSuspensionWidget.svelte';
  import DashboardTachWidget from './DashboardTachWidget.svelte';
  import DashboardTiresWidget from './DashboardTiresWidget.svelte';
  import { DASHBOARD_WIDGETS } from './dashboardWidgets';
  import type { CarInfo, DashboardWidgetId, LiveSample, UnitSystem } from './types';

  export let samples: LiveSample[] = [];
  export let currentSample: LiveSample | null = null;
  export let carInfo: CarInfo | null = null;
  export let unitSystem: UnitSystem = 'imperial';
  export let enabledWidgets: Record<DashboardWidgetId, boolean>;

  const dispatch = createEventDispatcher<{ showall: void }>();

  $: visibleWidgetIds = DASHBOARD_WIDGETS.filter((widget) => enabledWidgets[widget.id]).map((widget) => widget.id);
</script>

<section class="telemetry-dashboard" aria-label="Telemetry dashboard canvas" data-testid="telemetry-dashboard">
  {#if visibleWidgetIds.length === 0}
    <div class="dashboard-empty">
      <h2>No dashboard widgets are visible</h2>
      <p>Use the visibility control to choose widgets, or restore the default dashboard.</p>
      <button type="button" on:click={() => dispatch('showall')}>Show all widgets</button>
    </div>
  {:else}
    <div class="dashboard-grid" data-testid="dashboard-widget-grid">
      {#if enabledWidgets.tachSpeedGear}
        <DashboardTachWidget sample={currentSample} {unitSystem} />
      {/if}
      {#if enabledWidgets.inputsSteering}
        <DashboardInputsWidget sample={currentSample} />
      {/if}
      {#if enabledWidgets.tires}
        <DashboardTiresWidget sample={currentSample} />
      {/if}
      {#if enabledWidgets.suspensionAttitude}
        <DashboardSuspensionWidget sample={currentSample} />
      {/if}
      {#if enabledWidgets.accelerometer}
        <DashboardAccelerometerWidget sample={currentSample} />
      {/if}
      {#if enabledWidgets.lapTiming}
        <DashboardLapTimingWidget sample={currentSample} />
      {/if}
      {#if enabledWidgets.miniRoute}
        <DashboardMiniRouteWidget {samples} currentSample={currentSample} />
      {/if}
      {#if enabledWidgets.fuelRaceInfo}
        <DashboardFuelRaceWidget sample={currentSample} />
      {/if}
      {#if enabledWidgets.carDetails}
        <DashboardCarDetailsWidget car={carInfo} />
      {/if}
    </div>
  {/if}
</section>

<style>
  .telemetry-dashboard {
    box-sizing: border-box;
    height: 100%;
    min-height: 0;
    overflow: auto;
    padding: calc(var(--canvas-floating-margin) + 4.2rem) var(--canvas-floating-margin) calc(var(--dashboard-timeline-height) + 2rem);
  }

  .dashboard-grid {
    align-items: stretch;
    display: grid;
    gap: 0.85rem;
    grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  }

  .dashboard-empty {
    align-content: center;
    background: var(--canvas-overlay-panel-bg);
    border: 1px dashed #52525b;
    border-radius: 1rem;
    display: grid;
    justify-items: center;
    margin: min(20vh, 8rem) auto 0;
    max-width: 34rem;
    padding: 2rem;
    text-align: center;
  }

  .dashboard-empty h2 {
    margin: 0;
  }

  .dashboard-empty p {
    color: var(--text-secondary);
    margin: 0.5rem 0 1rem;
  }

  .dashboard-empty button {
    background: #3f3f46;
    border: 1px solid #71717a;
    border-radius: 0.75rem;
    color: #f4f4f5;
    font-weight: 800;
    padding: 0.65rem 0.9rem;
  }
</style>
