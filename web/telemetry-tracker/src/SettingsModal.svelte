<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { updateVisualiserSettings } from './api';
  import AppModal from './AppModal.svelte';
  import WorldMapSettingsPanel from './WorldMapSettingsPanel.svelte';
  import type { CaptureStatus, ListenerStatus, OverlayId, StatusPayload, UnitSystem, VisualiserSettings, WorldMapStatus } from './types';

  export let status: StatusPayload | null = null;
  export let listener: ListenerStatus;
  export let capture: CaptureStatus;
  export let worldMapStatus: WorldMapStatus | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
    resetlayout: void;
    settingschange: { settings: VisualiserSettings; applyPreferredOverlay?: boolean };
    settingserror: { message: string };
    worldmapchange: { status: WorldMapStatus; message: string };
    worldmaperror: { message: string };
  }>();

  const overlayOptions: Array<{ value: OverlayId; label: string }> = [
    { value: 'issues', label: 'Issues' },
    { value: 'speed', label: 'Speed' },
    { value: 'inputs', label: 'Inputs' },
    { value: 'grip', label: 'Grip' },
    { value: 'temperature', label: 'Temperature' },
    { value: 'suspension', label: 'Suspension' },
    { value: 'rpm', label: 'RPM' }
  ];

  const fallbackSettings: VisualiserSettings = {
    capture_mode: 'auto',
    udp_host: '127.0.0.1',
    udp_port: 5400,
    preferred_overlay: 'issues',
    unit_system: 'imperial'
  };

  let savingOverlay = false;
  let overlayErrorMessage = '';
  let selectedDefaultOverlay: OverlayId = 'issues';
  let savingUnits = false;
  let selectedUnitSystem: UnitSystem = 'imperial';
  let unitErrorMessage = '';

  $: settings = status?.settings ?? capture.settings ?? fallbackSettings;
  $: udpHost = settings.udp_host || listener.udp_host;
  $: udpPort = String(settings.udp_port || listener.udp_port);
  $: captureMode = capture.mode ?? settings.capture_mode;
  $: listenerPacketSummary = `${formatPacketCount(listener.packets_received)} received / ${formatPacketCount(listener.packets_recorded)} recorded`;
  $: localStorageSummary = 'Dashboard layout changes are kept in this browser session until persistent layout storage is added.';
  $: if (!savingOverlay) {
    selectedDefaultOverlay = normaliseOverlay(settings.preferred_overlay);
  }
  $: if (!savingUnits) {
    selectedUnitSystem = normaliseUnitSystem(settings.unit_system);
  }

  function formatPacketCount(value: number | null | undefined) {
    return Number(value ?? 0).toLocaleString();
  }

  function normaliseUnitSystem(value: string | null | undefined): UnitSystem {
    return value === 'metric' ? 'metric' : 'imperial';
  }

  function normaliseOverlay(value: string | null | undefined): OverlayId {
    return overlayOptions.some((option) => option.value === value) ? (value as OverlayId) : 'issues';
  }

  async function handleDefaultOverlayChange(event: Event) {
    const target = event.currentTarget as HTMLSelectElement;
    const nextOverlay = normaliseOverlay(target.value);
    if (nextOverlay === normaliseOverlay(settings.preferred_overlay)) {
      selectedDefaultOverlay = nextOverlay;
      return;
    }

    selectedDefaultOverlay = nextOverlay;
    savingOverlay = true;
    overlayErrorMessage = '';
    try {
      const updatedSettings = await updateVisualiserSettings({ preferred_overlay: nextOverlay });
      dispatch('settingschange', { settings: updatedSettings, applyPreferredOverlay: true });
    } catch (error) {
      overlayErrorMessage = 'Unable to save default overlay preference.';
      selectedDefaultOverlay = normaliseOverlay(settings.preferred_overlay);
      dispatch('settingserror', { message: overlayErrorMessage });
    } finally {
      savingOverlay = false;
    }
  }

  async function handleUnitSystemChange(event: Event) {
    const target = event.currentTarget as HTMLSelectElement;
    const nextUnitSystem = normaliseUnitSystem(target.value);
    if (nextUnitSystem === normaliseUnitSystem(settings.unit_system)) {
      selectedUnitSystem = nextUnitSystem;
      return;
    }

    selectedUnitSystem = nextUnitSystem;
    savingUnits = true;
    unitErrorMessage = '';
    try {
      const updatedSettings = await updateVisualiserSettings({ unit_system: nextUnitSystem });
      dispatch('settingschange', { settings: updatedSettings });
    } catch (error) {
      unitErrorMessage = 'Unable to save speed unit preference.';
      selectedUnitSystem = normaliseUnitSystem(settings.unit_system);
      dispatch('settingserror', { message: unitErrorMessage });
    } finally {
      savingUnits = false;
    }
  }
</script>

<AppModal title="Forza Telemetry Tracker settings" on:close={() => dispatch('close')}>
  <form class="settings-form" aria-label="Forza Telemetry Tracker settings form" on:submit|preventDefault>
    <section class="settings-section" aria-label="UDP listener settings">
      <h3>UDP listener</h3>
      <div class="settings-grid">
        <label>
          <span>UDP host</span>
          <input value={udpHost} readonly aria-readonly="true" />
        </label>
        <label>
          <span>UDP port</span>
          <input value={udpPort} readonly aria-readonly="true" inputmode="numeric" />
        </label>
      </div>
      <p class="settings-hint">For desktop v1, run Forza and this tracker on the same Windows PC.</p>
      <p class="settings-hint">Set Forza Data Out to IP {udpHost} and port {udpPort}.</p>
    </section>

    <section class="settings-section" aria-label="Default overlay settings">
      <h3>Visual defaults</h3>
      <label>
        <span>Default overlay</span>
        <select
          value={selectedDefaultOverlay}
          disabled={savingOverlay}
          aria-describedby="overlay-setting-hint"
          on:change={handleDefaultOverlayChange}
        >
          {#each overlayOptions as option}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </label>
      <p id="overlay-setting-hint" class="settings-hint">
        {savingOverlay ? 'Saving default overlay…' : 'New site loads start with this overlay; saving also switches the current overlay.'}
      </p>
      {#if overlayErrorMessage}
        <p class="settings-error" role="alert">{overlayErrorMessage}</p>
      {/if}
    </section>

    <section class="settings-section" aria-label="Units settings">
      <h3>Units</h3>
      <label>
        <span>Speed units</span>
        <select aria-label="Speed units" value={selectedUnitSystem} disabled={savingUnits} on:change={handleUnitSystemChange}>
          <option value="imperial">Imperial (MPH)</option>
          <option value="metric">Metric (KPH)</option>
        </select>
      </label>
      <p class="settings-hint">
        {savingUnits ? 'Saving unit preference…' : 'Full lap and selected-section summaries use this speed unit.'}
      </p>
      {#if unitErrorMessage}
        <p class="settings-error" role="alert">{unitErrorMessage}</p>
      {/if}
    </section>

    <WorldMapSettingsPanel
      status={worldMapStatus}
      on:worldmapchange={(event) => dispatch('worldmapchange', event.detail)}
      on:worldmaperror={(event) => dispatch('worldmaperror', event.detail)}
    />

    <section class="settings-info" aria-label="Tracker status summary">
      <h3>Status summary</h3>
      <dl>
        <div>
          <dt>Capture mode</dt>
          <dd>{captureMode}</dd>
        </div>
        <div>
          <dt>Listener packets</dt>
          <dd>{listenerPacketSummary}</dd>
        </div>
        <div>
          <dt>Local storage</dt>
          <dd>{localStorageSummary}</dd>
        </div>
      </dl>
    </section>

    <div class="modal-actions">
      <button type="button" class="secondary-action" on:click={() => dispatch('resetlayout')}>
        Reset floating panels and layout
      </button>
    </div>
  </form>
</AppModal>
