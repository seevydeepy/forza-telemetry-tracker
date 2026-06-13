<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IconButton from './IconButton.svelte';
  import type { CaptureMode, CaptureStatus } from './types';

  export let capture: CaptureStatus;
  export let disabled = false;
  export let canStart = true;
  export let canStop = true;
  export let controlsElement: HTMLDivElement | null = null;

  const dispatch = createEventDispatcher<{
    modechange: { mode: CaptureMode };
    start: void;
    stop: void;
  }>();

  $: manualMode = capture.mode === 'manual';
  $: canStartManual = manualMode && !capture.recording.active && !disabled && canStart;
  $: canStopManual = manualMode && capture.recording.active && !disabled && canStop;
  $: manualActionDisabled = manualMode ? (capture.recording.active ? !canStopManual : !canStartManual) : true;
  $: manualActionIcon = capture.recording.active ? 'stop' : 'play';
  $: manualActionLabel = capture.recording.active ? 'Stop manual capture' : 'Start manual capture';

  function setMode(mode: CaptureMode) {
    if (disabled || capture.mode === mode) return;
    dispatch('modechange', { mode });
  }
</script>

<div bind:this={controlsElement} class="floating-capture-controls" role="group" aria-label="Floating capture controls">
  <div class="capture-mode-switch" role="group" aria-label="Recording mode">
    <button
      type="button"
      class:active={capture.mode === 'auto'}
      aria-label="Auto capture"
      aria-pressed={capture.mode === 'auto'}
      title="Use automatic race detection"
      disabled={disabled}
      on:click={() => setMode('auto')}
    >
      Auto
    </button>
    <button
      type="button"
      class:active={capture.mode === 'manual'}
      aria-label="Manual capture"
      aria-pressed={capture.mode === 'manual'}
      title="Use manual capture"
      disabled={disabled}
      on:click={() => setMode('manual')}
    >
      Manual
    </button>
  </div>
  <IconButton
    icon={manualActionIcon}
    label={manualActionLabel}
    title={manualMode ? manualActionLabel : 'Manual start/stop is disabled in auto mode'}
    disabled={manualActionDisabled}
    kind={capture.recording.active ? 'danger' : 'primary'}
    onClick={() => dispatch(capture.recording.active ? 'stop' : 'start')}
  />
</div>

<style>
  .capture-mode-switch {
    align-items: center;
    background: var(--canvas-overlay-control-bg);
    border: 1px solid #3f3f46;
    border-radius: 999px;
    display: inline-flex;
    gap: 0.15rem;
    padding: 0.15rem;
  }

  .capture-mode-switch button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 999px;
    color: #d4d4d8;
    font: inherit;
    min-height: 32px;
    padding: 0.35rem 0.7rem;
  }

  .capture-mode-switch button.active,
  .capture-mode-switch button[aria-pressed='true'] {
    background: var(--canvas-overlay-control-bg-active);
    border-color: #71717a;
    color: #fafafa;
  }

  .capture-mode-switch button:focus-visible {
    outline: 2px solid #a1a1aa;
    outline-offset: 2px;
  }

  .capture-mode-switch button:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }
</style>
