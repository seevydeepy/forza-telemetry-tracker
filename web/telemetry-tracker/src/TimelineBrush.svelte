<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { SequenceRange } from './types';

  export let bounds: SequenceRange | null = null;
  export let selectedRange: SequenceRange | null = null;
  export let disabled = false;

  const dispatch = createEventDispatcher<{
    rangechange: { range: SequenceRange };
  }>();

  let startValue = 0;
  let endValue = 0;

  function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value));
  }

  $: if (!bounds) {
    startValue = 0;
    endValue = 0;
  } else {
    startValue = selectedRange?.startSequence ?? bounds.startSequence;
    endValue = selectedRange?.endSequence ?? bounds.endSequence;
  }

  function emitRange() {
    if (!bounds) return;
    dispatch('rangechange', {
      range: {
        startSequence: startValue,
        endSequence: endValue
      }
    });
  }

  function handleStartInput(event: Event) {
    if (!bounds) return;
    const value = Number((event.currentTarget as HTMLInputElement).value);
    startValue = clamp(value, bounds.startSequence, endValue);
    emitRange();
  }

  function handleEndInput(event: Event) {
    if (!bounds) return;
    const value = Number((event.currentTarget as HTMLInputElement).value);
    endValue = clamp(value, startValue, bounds.endSequence);
    emitRange();
  }

  function resetToFullLap() {
    if (!bounds) return;
    startValue = bounds.startSequence;
    endValue = bounds.endSequence;
    emitRange();
  }
</script>

<section class="timeline-brush" aria-label="Timeline section selector">
  <div class="timeline-header">
    <h2>Timeline brush</h2>
    {#if bounds}
      <button type="button" class="reset-button" on:click={resetToFullLap} disabled={disabled}>
        Full lap
      </button>
    {/if}
  </div>

  {#if bounds}
    <p class="range-readout" aria-live="polite">
      Selected sequences {startValue}–{endValue}
    </p>
    <label>
      <span>Section start sequence</span>
      <input
        type="range"
        min={bounds.startSequence}
        max={bounds.endSequence}
        value={startValue}
        disabled={disabled}
        aria-label="Section start sequence"
        title="Adjust the start of the selected section"
        on:input={handleStartInput}
      />
    </label>
    <label>
      <span>Section end sequence</span>
      <input
        type="range"
        min={bounds.startSequence}
        max={bounds.endSequence}
        value={endValue}
        disabled={disabled}
        aria-label="Section end sequence"
        title="Adjust the end of the selected section"
        on:input={handleEndInput}
      />
    </label>
  {:else}
    <p class="empty-state">Select a completed lap to enable section drilldown.</p>
  {/if}
</section>

<style>
  .timeline-brush {
    border: 1px solid #27272a;
    border-radius: 1rem;
    display: grid;
    gap: 0.75rem;
    padding: 1rem;
  }

  .timeline-header {
    align-items: center;
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  h2 {
    margin: 0;
  }

  .range-readout,
  .empty-state {
    color: #a1a1aa;
    margin: 0;
  }

  label {
    display: grid;
    gap: 0.4rem;
  }

  label span {
    font-size: 0.9rem;
  }

  input[type='range'] {
    width: 100%;
  }

  .reset-button {
    background: #3f3f46;
    border: 1px solid #a1a1aa;
    border-radius: 999px;
    color: #fafafa;
    padding: 0.35rem 0.75rem;
  }
</style>
