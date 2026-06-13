<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IconButton from './IconButton.svelte';
  import type { CaptureMode, CaptureStatus } from './types';

  export let capture: CaptureStatus;
  export let disabled = false;

  const dispatch = createEventDispatcher<{
    modechange: { mode: CaptureMode };
    start: void;
    stop: void;
  }>();

  $: manualMode = capture.mode === 'manual';
  $: canStartManual = manualMode && !capture.recording.active && !disabled;
  $: canStopManual = manualMode && capture.recording.active && !disabled;

  function setMode(mode: CaptureMode) {
    dispatch('modechange', { mode });
  }
</script>

<section class="capture-controls" aria-label="Capture controls">
  <div class="capture-header">
    <h2>Capture</h2>
    <p>{capture.mode === 'auto' ? 'Automatic race detection is enabled.' : 'Manual capture requires explicit start/stop.'}</p>
  </div>

  <fieldset class="mode-group" disabled={disabled}>
    <legend>Capture mode</legend>
    <label class:active={capture.mode === 'auto'}>
      <input
        type="radio"
        name="capture-mode"
        value="auto"
        checked={capture.mode === 'auto'}
        on:change={() => setMode('auto')}
      />
      <span>Auto capture</span>
    </label>
    <label class:active={capture.mode === 'manual'}>
      <input
        type="radio"
        name="capture-mode"
        value="manual"
        checked={capture.mode === 'manual'}
        on:change={() => setMode('manual')}
      />
      <span>Manual capture</span>
    </label>
  </fieldset>

  <div class="manual-controls">
    <IconButton icon="play" label="Start manual capture" title="Start manual capture" disabled={!canStartManual} kind="primary" onClick={() => dispatch('start')} />
    <IconButton icon="stop" label="Stop manual capture" title="Stop manual capture" disabled={!canStopManual} kind="danger" onClick={() => dispatch('stop')} />
  </div>

  <dl class="capture-meta">
    <div>
      <dt>Phase</dt>
      <dd>{capture.phase}</dd>
    </div>
    <div>
      <dt>Packets seen</dt>
      <dd>{capture.packet_receipt.packets_observed}</dd>
    </div>
    <div>
      <dt>Buffered</dt>
      <dd>{capture.prebuffer.size}/{capture.prebuffer.capacity}</dd>
    </div>
  </dl>
</section>

<style>
  .capture-controls {
    border: 1px solid #27272a;
    border-radius: 1rem;
    display: grid;
    gap: 0.9rem;
    padding: 1rem;
  }

  .capture-header h2,
  .capture-header p {
    margin: 0;
  }

  .capture-header p {
    color: #a1a1aa;
    font-size: 0.9rem;
    margin-top: 0.3rem;
  }

  .mode-group {
    border: 0;
    display: grid;
    gap: 0.5rem;
    margin: 0;
    padding: 0;
  }

  .mode-group legend {
    font-size: 0.85rem;
    margin-bottom: 0.35rem;
  }

  .mode-group label {
    align-items: center;
    background: #1f1f23;
    border: 1px solid #3f3f46;
    border-radius: 0.9rem;
    display: flex;
    gap: 0.6rem;
    padding: 0.7rem 0.85rem;
  }

  .mode-group label.active {
    border-color: #a1a1aa;
    box-shadow: inset 0 0 0 1px #a1a1aa;
  }

  .manual-controls {
    display: flex;
    gap: 0.75rem;
  }

  .capture-meta {
    display: grid;
    gap: 0.6rem;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin: 0;
  }

  .capture-meta div {
    background: #1f1f23;
    border-radius: 0.8rem;
    padding: 0.7rem;
  }

  .capture-meta dt {
    color: #a1a1aa;
    font-size: 0.78rem;
    margin-bottom: 0.2rem;
  }

  .capture-meta dd {
    margin: 0;
  }
</style>
