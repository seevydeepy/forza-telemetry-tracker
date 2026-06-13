<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import { formatTime } from './dashboardFormat';
  import type { DashboardPlaybackSource, LiveSample } from './types';

  export let source: DashboardPlaybackSource = 'live';
  export let samples: LiveSample[] = [];
  export let currentSample: LiveSample | null = null;
  export let currentIndex = -1;
  export let currentTimeMs = 0;
  export let durationMs = 0;
  export let currentElapsedMs: number | null = null;
  export let durationElapsedMs: number | null = null;
  export let progress = 0;
  export let playing = false;

  const dispatch = createEventDispatcher<{ play: void; pause: void; scrub: { timeMs: number } }>();

  function handleScrub(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    dispatch('scrub', { timeMs: Number(input.value) });
  }

  $: currentSeconds = (currentElapsedMs ?? currentTimeMs) / 1000;
  $: durationSeconds = (durationElapsedMs ?? durationMs) / 1000;
  $: progressPercent = Math.max(0, Math.min(100, progress * 100));
</script>

<div class="dashboard-playback-bar" role="region" aria-label="Dashboard playback">
  {#if source === 'lap'}
    <button type="button" class="playback-button" aria-label={playing ? 'Pause dashboard playback' : 'Play dashboard playback'} on:click={() => dispatch(playing ? 'pause' : 'play')}>
      <Icon name={playing ? 'pause' : 'play'} />
    </button>
    <div class="playback-main">
      <div class="playback-label">
        <strong>Selected lap playback</strong>
        <span>{formatTime(currentSeconds)} / {formatTime(durationSeconds)} · Sample {currentIndex + 1} of {samples.length} · {progressPercent.toFixed(1)}%</span>
      </div>
      <input
        type="range"
        min="0"
        max={Math.max(0, durationMs)}
        value={Math.min(currentTimeMs, durationMs)}
        step="1"
        aria-label="Scrub selected lap dashboard playback"
        aria-valuetext={`${progressPercent.toFixed(1)}%`}
        on:input={handleScrub}
      />
    </div>
  {:else}
    <div class="live-dashboard-status">
      <strong>Live dashboard</strong>
      <span>{samples.length} samples · Lap {currentSample?.lap_number ?? '—'} · {formatTime(currentSample?.current_lap)}</span>
    </div>
  {/if}
</div>

<style>
  .dashboard-playback-bar {
    align-items: center;
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 1rem;
    box-shadow: 0 20px 60px rgb(0 0 0 / 38%);
    display: flex;
    gap: 0.75rem;
    min-height: 0;
    padding: 0.85rem 1rem;
  }

  .playback-button {
    align-items: center;
    background: var(--canvas-overlay-control-bg-active);
    border: 1px solid #71717a;
    border-radius: 999px;
    color: #f4f4f5;
    display: inline-flex;
    height: 2.5rem;
    justify-content: center;
    width: 2.5rem;
  }

  .playback-main {
    display: grid;
    flex: 1 1 auto;
    gap: 0.55rem;
    min-width: 0;
  }

  .playback-label,
  .live-dashboard-status {
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
  }

  span {
    color: var(--text-secondary);
  }

  input[type='range'] {
    width: 100%;
  }

  @media (max-width: 720px) {
    .playback-label,
    .live-dashboard-status {
      display: grid;
      gap: 0.25rem;
    }
  }
</style>
