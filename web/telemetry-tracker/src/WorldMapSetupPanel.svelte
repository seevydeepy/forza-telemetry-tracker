<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import { buildWorldMapCache, updateWorldMapSettings } from './api';
  import IconButton from './IconButton.svelte';
  import type { WorldMapSeason, WorldMapSettings, WorldMapStatus } from './types';

  export let status: WorldMapStatus | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
    ready: { status: WorldMapStatus };
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
  let season: WorldMapSeason = 'summer';
  let building = false;
  let errorMessage = '';
  let lastSettingsSignature = '';
  let mediaRootInput: HTMLInputElement | null = null;

  $: settingsSignature = JSON.stringify(status?.settings ?? null);
  $: if (!building && settingsSignature !== lastSettingsSignature) {
    mediaRoot = status?.settings.fh6_media_root ?? '';
    season = status?.settings.world_map_season ?? 'summer';
    lastSettingsSignature = settingsSignature;
  }
  $: sourceStatus = sourceStatusLabel(status, mediaRoot);
  $: cacheStatus = cacheStatusLabel(status);
  $: converterStatus = converterStatusLabel(status);

  onMount(async () => {
    await tick();
    mediaRootInput?.focus({ preventScroll: true });
  });

  function settingsInput(): WorldMapSettings {
    return {
      fh6_media_root: mediaRoot.trim() || null,
      world_map_enabled: true,
      world_map_season: season
    };
  }

  async function handleBuild() {
    building = true;
    errorMessage = '';
    try {
      const savedStatus = await updateWorldMapSettings(settingsInput());
      dispatch('worldmapchange', { status: savedStatus, message: 'World map settings saved' });
      const nextStatus = await buildWorldMapCache(season);
      const message =
        nextStatus.status === 'ready'
          ? 'World map cache ready'
          : nextStatus.error_message ?? 'World map cache build did not complete.';
      dispatch('worldmapchange', { status: nextStatus, message });
      if (nextStatus.status === 'ready' && nextStatus.tile_set?.status === 'ready') {
        dispatch('ready', { status: nextStatus });
        return;
      }
      errorMessage = nextStatus.error_message ?? statusActionLabel(nextStatus);
    } catch (error) {
      errorMessage = 'Unable to build the FH6 world map cache.';
      dispatch('worldmaperror', { message: errorMessage });
    } finally {
      building = false;
    }
  }

  function sourceStatusLabel(nextStatus: WorldMapStatus | null, nextMediaRoot: string) {
    if (!nextMediaRoot.trim()) return 'Choose your FH6 media folder to locate the seasonal map archive.';
    if (!nextStatus) return 'World map source status has not loaded yet.';
    return nextStatus.source.available
      ? `Source archive found for ${nextStatus.source.season}.`
      : `Source archive not found for ${nextStatus.source.season}.`;
  }

  function cacheStatusLabel(nextStatus: WorldMapStatus | null) {
    if (!nextStatus) return 'Cache status has not loaded yet.';
    if (nextStatus.tile_set?.status === 'ready') return `Cache ready: ${nextStatus.tile_set.id}.`;
    return statusActionLabel(nextStatus);
  }

  function converterStatusLabel(nextStatus: WorldMapStatus | null) {
    if (!nextStatus) return 'Converter status has not loaded yet.';
    return nextStatus.converter.available
      ? 'Map converter ready.'
      : 'Map converter unavailable in this installation.';
  }

  function statusActionLabel(nextStatus: WorldMapStatus) {
    switch (nextStatus.status) {
      case 'cache_missing':
        return 'Cache has not been built for this season yet.';
      case 'cache_stale':
        return 'Cache was built with an older tile layout; rebuild the local map cache.';
      case 'converter_missing':
        return 'Map converter is missing from this installation. Reinstall the tracker or install a repaired build.';
      case 'source_missing':
        return 'The selected FH6 media folder did not contain the expected seasonal map archive.';
      case 'error':
        return nextStatus.error_message ?? 'Last map cache build failed.';
      case 'disabled':
        return 'World map overlay is disabled until setup completes.';
      case 'ready':
        return 'World map cache is ready.';
      default:
        return 'World map cache build did not complete.';
    }
  }
</script>

<section class="world-map-setup-panel" aria-label="FH6 world map setup">
  <header class="world-map-setup-header">
    <div>
      <h2>FH6 world map setup</h2>
      <p>Map cache has not been initialized.</p>
    </div>
    <IconButton icon="close" label="Close map setup" title="Close map setup" onClick={() => dispatch('close')} />
  </header>

  <p class="settings-hint">
    Link the tracker to your FH6 media folder. The tracker will look there for seasonal map tile archives,
    build a local cache, and then turn the map overlay on.
  </p>

  <label>
    <span>FH6 media folder</span>
    <input
      aria-label="FH6 media folder"
      bind:this={mediaRootInput}
      bind:value={mediaRoot}
      placeholder="G:\SteamLibrary\steamapps\common\ForzaHorizon6\media"
      disabled={building}
    />
  </label>

  <label>
    <span>Map season</span>
    <select aria-label="Map season" bind:value={season} disabled={building}>
      {#each seasonOptions as option}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </label>

  <dl class="world-map-setup-status" aria-label="World map setup status">
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

  <div class="world-map-setup-actions">
    <button type="button" class="primary-action" disabled={building || !mediaRoot.trim()} on:click={handleBuild}>
      {building ? 'Building local map cache…' : 'Build local map cache'}
    </button>
  </div>
</section>
