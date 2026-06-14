<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { buildWorldMapCache, updateWorldMapSettings } from './api';
  import WorldMapInstallLocationField from './WorldMapInstallLocationField.svelte';
  import type { WorldMapSeason, WorldMapSettings, WorldMapStatus } from './types';

  export let status: WorldMapStatus | null = null;

  const dispatch = createEventDispatcher<{
    worldmapchange: { status: WorldMapStatus; message: string };
    worldmaperror: { message: string };
  }>();

  const seasonOptions: Array<{ value: WorldMapSeason; label: string }> = [
    { value: 'summer', label: 'Summer' },
    { value: 'spring', label: 'Spring' },
    { value: 'autumn', label: 'Autumn' },
    { value: 'winter', label: 'Winter' }
  ];

  let mediaRoot = '';
  let enabled = false;
  let season: WorldMapSeason = 'summer';
  let saving = false;
  let building = false;
  let errorMessage = '';
  let lastSettingsSignature = '';

  $: settingsSignature = JSON.stringify(status?.settings ?? null);
  $: if (!saving && !building && settingsSignature !== lastSettingsSignature) {
    mediaRoot = status?.settings.fh6_media_root ?? '';
    enabled = status?.settings.world_map_enabled ?? false;
    season = status?.settings.world_map_season ?? 'summer';
    lastSettingsSignature = settingsSignature;
  }
  $: busy = saving || building;
  $: sourceStatus = sourceStatusLabel(status, mediaRoot);
  $: cacheStatus = cacheStatusLabel(status);
  $: converterStatus = converterStatusLabel(status);

  function settingsInput(): WorldMapSettings {
    return {
      fh6_media_root: mediaRoot.trim() || null,
      world_map_enabled: enabled,
      world_map_season: season
    };
  }

  async function handleSave() {
    saving = true;
    errorMessage = '';
    try {
      const nextStatus = await updateWorldMapSettings(settingsInput());
      dispatch('worldmapchange', { status: nextStatus, message: 'World map settings saved' });
    } catch (error) {
      errorMessage = 'Unable to save FH6 world map settings.';
      dispatch('worldmaperror', { message: errorMessage });
    } finally {
      saving = false;
    }
  }

  async function handleBuild() {
    building = true;
    errorMessage = '';
    try {
      const savedStatus = await updateWorldMapSettings(settingsInput());
      dispatch('worldmapchange', { status: savedStatus, message: 'World map settings saved' });
      const nextStatus = await buildWorldMapCache(season);
      if (nextStatus.status === 'ready') {
        dispatch('worldmapchange', { status: nextStatus, message: 'World map cache ready' });
      } else {
        const message = nextStatus.error_message ?? 'World map cache build did not complete.';
        errorMessage = message;
        dispatch('worldmapchange', { status: nextStatus, message });
      }
    } catch (error) {
      errorMessage = 'Unable to build the FH6 world map cache.';
      dispatch('worldmaperror', { message: errorMessage });
    } finally {
      building = false;
    }
  }

  function sourceStatusLabel(nextStatus: WorldMapStatus | null, nextMediaRoot: string) {
    if (!nextMediaRoot.trim()) return 'FH6 install location is not configured.';
    if (!nextStatus) return 'World map source status has not loaded yet.';
    return nextStatus.source.available
      ? `Source archive found for ${nextStatus.source.season}.`
      : `Source archive not found for ${nextStatus.source.season}.`;
  }

  function cacheStatusLabel(nextStatus: WorldMapStatus | null) {
    if (!nextStatus) return 'Cache status has not loaded yet.';
    if (nextStatus.tile_set?.status === 'ready') {
      return `Cache ready: ${nextStatus.tile_set.id}.`;
    }
    switch (nextStatus.status) {
      case 'disabled':
        return 'World map overlay is disabled.';
      case 'cache_missing':
        return 'Cache has not been built for this season yet.';
      case 'cache_stale':
        return 'Cache was built with an older tile layout; rebuild the local map cache.';
      case 'converter_missing':
        return 'Map converter is missing from this installation. Reinstall the tracker or install a repaired build.';
      case 'source_missing':
        return 'Waiting for a valid FH6 install location and seasonal map archive.';
      case 'error':
        return nextStatus.error_message ?? 'Last map cache build failed.';
      default:
        return 'Cache status is unknown.';
    }
  }

  function converterStatusLabel(nextStatus: WorldMapStatus | null) {
    if (!nextStatus) return 'Converter status has not loaded yet.';
    return nextStatus.converter.available
      ? 'Map converter ready.'
      : 'Map converter unavailable in this installation.';
  }
</script>

<section class="settings-section world-map-panel" aria-label="FH6 world map settings">
  <h3>FH6 world map</h3>
  <p class="settings-hint">
    Link the tracker to your FH6 game install folder. Map tiles are generated from your local FH6 install and stored only in your local tracker cache.
    The app does not bundle or upload map assets.
  </p>

  <WorldMapInstallLocationField bind:value={mediaRoot} disabled={busy} />

  <div class="world-map-grid">
    <label>
      <span>Map season</span>
      <select aria-label="Map season" bind:value={season} disabled={busy}>
        {#each seasonOptions as option}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
    </label>

    <label class="inline-toggle">
      <input type="checkbox" bind:checked={enabled} disabled={busy} />
      <span>Enable world map overlay</span>
    </label>
  </div>

  <dl class="world-map-status" aria-label="World map cache status">
    <div>
      <dt>Source</dt>
      <dd>{sourceStatus}</dd>
    </div>
    <div>
      <dt>Cache</dt>
      <dd>{cacheStatus}</dd>
    </div>
    <div>
      <dt>Converter</dt>
      <dd>{converterStatus}</dd>
    </div>
  </dl>

  {#if errorMessage}
    <p class="settings-error" role="alert">{errorMessage}</p>
  {/if}

  <div class="world-map-actions">
    <button type="button" class="primary-action" disabled={busy || !mediaRoot.trim()} on:click={handleBuild}>
      {building ? 'Building local map cache…' : 'Build local map cache'}
    </button>
    <button type="button" class="secondary-action" disabled={busy} on:click={handleSave}>
      {saving ? 'Saving map settings…' : 'Save map settings'}
    </button>
  </div>
</section>

<style>
  .world-map-panel {
    display: grid;
    gap: 0.75rem;
  }

  .world-map-panel h3 {
    margin: 0;
  }

  .world-map-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.75rem;
    align-items: end;
  }

  .inline-toggle {
    display: inline-flex;
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    min-height: 2.5rem;
  }

  .inline-toggle input {
    width: auto;
  }

  .world-map-status {
    display: grid;
    gap: 0.45rem;
    margin: 0;
    padding: 0.75rem;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.45);
  }

  .world-map-status div {
    display: grid;
    grid-template-columns: 5rem minmax(0, 1fr);
    gap: 0.75rem;
  }

  .world-map-status dt {
    color: #94a3b8;
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .world-map-status dd {
    margin: 0;
    color: #e2e8f0;
  }

  .world-map-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    justify-content: flex-end;
  }

  @media (max-width: 720px) {
    .world-map-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
