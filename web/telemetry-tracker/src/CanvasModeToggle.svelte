<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import type { CanvasMode } from './types';

  export let mode: CanvasMode = 'route';

  const dispatch = createEventDispatcher<{ change: { mode: CanvasMode } }>();

  function selectMode(nextMode: CanvasMode) {
    if (nextMode !== mode) dispatch('change', { mode: nextMode });
  }
</script>

<div class="canvas-mode-toggle" role="group" aria-label="Canvas mode">
  <button type="button" aria-label="Route visualiser mode" aria-pressed={mode === 'route'} on:click={() => selectMode('route')}>
    <Icon name="laps" />
    <span>Route</span>
  </button>
  <button type="button" aria-label="Telemetry dashboard mode" aria-pressed={mode === 'dashboard'} on:click={() => selectMode('dashboard')}>
    <Icon name="dashboard" />
    <span>Dashboard</span>
  </button>
</div>

<style>
  .canvas-mode-toggle {
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 999px;
    box-shadow: 0 12px 34px rgb(0 0 0 / 28%);
    display: inline-flex;
    gap: 0.25rem;
    padding: 0.25rem;
  }

  button {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 999px;
    color: #d4d4d8;
    display: inline-flex;
    gap: 0.4rem;
    font-weight: 800;
    min-height: 2.35rem;
    padding: 0 0.8rem;
  }

  button[aria-pressed='true'] {
    background: var(--canvas-overlay-control-bg-active);
    color: #fafafa;
  }

  button:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
</style>
