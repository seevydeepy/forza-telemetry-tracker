<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IconButton from './IconButton.svelte';
  import type { SequenceRange } from './types';

  export let bounds: SequenceRange | null = null;
  export let selectedRange: SequenceRange | null = null;
  export let disabled = false;
  export let message = 'Timeline available after a saved lap or session is selected.';

  const dispatch = createEventDispatcher<{ rangechange: { range: SequenceRange } }>();

  let startValue = 0;
  let endValue = 0;
  let selectedStartPercent = 0;
  let selectedEndPercent = 0;
  let selectedWidthPercent = 0;
  let rangeControlElement: HTMLDivElement | null = null;
  let startInputElement: HTMLInputElement | null = null;
  let endInputElement: HTMLInputElement | null = null;
  let activeThumb: 'start' | 'end' | null = null;

  function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value));
  }

  $: if (!bounds) {
    startValue = 0;
    endValue = 0;
  } else {
    const nextStart = clamp(selectedRange?.startSequence ?? bounds.startSequence, bounds.startSequence, bounds.endSequence);
    const nextEnd = clamp(selectedRange?.endSequence ?? bounds.endSequence, bounds.startSequence, bounds.endSequence);
    startValue = Math.min(nextStart, nextEnd);
    endValue = Math.max(nextStart, nextEnd);
  }

  $: timelineSpan = bounds ? Math.max(1, bounds.endSequence - bounds.startSequence) : 1;
  $: selectedStartPercent = bounds ? ((startValue - bounds.startSequence) / timelineSpan) * 100 : 0;
  $: selectedEndPercent = bounds ? ((endValue - bounds.startSequence) / timelineSpan) * 100 : 0;
  $: selectedWidthPercent = Math.max(0, selectedEndPercent - selectedStartPercent);

  function emitRange() {
    if (!bounds || disabled) return;
    dispatch('rangechange', { range: { startSequence: startValue, endSequence: endValue } });
  }

  function setStartValue(value: number) {
    if (!bounds) return;
    startValue = clamp(value, bounds.startSequence, endValue);
    if (startInputElement) startInputElement.value = String(startValue);
  }

  function setEndValue(value: number) {
    if (!bounds) return;
    endValue = clamp(value, startValue, bounds.endSequence);
    if (endInputElement) endInputElement.value = String(endValue);
  }

  function handleStartInput(event: Event) {
    if (!bounds || disabled) return;
    const input = event.currentTarget as HTMLInputElement;
    setStartValue(Number(input.value));
    emitRange();
  }

  function handleEndInput(event: Event) {
    if (!bounds || disabled) return;
    const input = event.currentTarget as HTMLInputElement;
    setEndValue(Number(input.value));
    emitRange();
  }

  function resetToFullLap() {
    if (!bounds || disabled) return;
    startValue = bounds.startSequence;
    endValue = bounds.endSequence;
    emitRange();
  }

  function sequenceFromClientX(clientX: number) {
    if (!bounds || !rangeControlElement) return null;
    const rect = rangeControlElement.getBoundingClientRect();
    const fraction = clamp((clientX - rect.left) / Math.max(1, rect.width), 0, 1);
    return bounds.startSequence + Math.round(fraction * (bounds.endSequence - bounds.startSequence));
  }

  function updateThumbFromPointer(thumb: 'start' | 'end', clientX: number) {
    const sequence = sequenceFromClientX(clientX);
    if (sequence === null) return;
    if (thumb === 'start') {
      setStartValue(sequence);
    } else {
      setEndValue(sequence);
    }
    emitRange();
  }

  function thumbNearestSequence(sequence: number): 'start' | 'end' {
    const startDistance = Math.abs(sequence - startValue);
    const endDistance = Math.abs(sequence - endValue);
    if (startDistance === endDistance) {
      return sequence < startValue ? 'start' : 'end';
    }
    return startDistance < endDistance ? 'start' : 'end';
  }

  function focusThumbInput(thumb: 'start' | 'end') {
    if (thumb === 'start') {
      startInputElement?.focus({ preventScroll: true });
    } else {
      endInputElement?.focus({ preventScroll: true });
    }
  }

  function beginThumbDrag(thumb: 'start' | 'end', event: PointerEvent) {
    event.preventDefault();
    activeThumb = thumb;
    focusThumbInput(thumb);
    rangeControlElement?.setPointerCapture?.(event.pointerId);
    updateThumbFromPointer(thumb, event.clientX);
  }

  function handleRangeControlPointerDown(event: PointerEvent) {
    if (!bounds || disabled) return;
    if (event.target instanceof Element && event.target.closest('.timeline-thumb')) return;
    const sequence = sequenceFromClientX(event.clientX);
    if (sequence === null) return;
    beginThumbDrag(thumbNearestSequence(sequence), event);
  }

  function handleThumbPointerDown(thumb: 'start' | 'end', event: PointerEvent) {
    if (!bounds || disabled) return;
    event.stopPropagation();
    beginThumbDrag(thumb, event);
  }

  function handleWindowPointerMove(event: PointerEvent) {
    if (!activeThumb) return;
    if (disabled) {
      activeThumb = null;
      return;
    }
    updateThumbFromPointer(activeThumb, event.clientX);
  }

  function handleWindowPointerUp() {
    activeThumb = null;
  }
</script>

<svelte:window on:pointermove={handleWindowPointerMove} on:pointerup={handleWindowPointerUp} on:pointercancel={handleWindowPointerUp} />

<div class="review-timeline" role="region" aria-label="Review timeline">
  <div class="review-timeline-label">
    <strong>Review timeline</strong>
    {#if bounds}
      <span>Sequences {startValue}–{endValue}</span>
    {/if}
  </div>

  {#if bounds}
    <div class="review-timeline-controls">
      <div bind:this={rangeControlElement} class="timeline-range-control" class:disabled role="group" aria-label="Timeline selected range" on:pointerdown={handleRangeControlPointerDown}>
        <div class="timeline-track" aria-hidden="true"></div>
        <div class="timeline-selected-segment" data-testid="timeline-selected-segment" style={`left: ${selectedStartPercent}%; width: ${selectedWidthPercent}%;`} aria-hidden="true"></div>
        <input
          bind:this={startInputElement}
          class="timeline-range-input timeline-range-input-start"
          type="range"
          min={bounds.startSequence}
          max={endValue}
          value={startValue}
          disabled={disabled}
          aria-label="Section start sequence"
          title="Adjust the start of the selected section"
          on:input={handleStartInput}
        />
        <input
          bind:this={endInputElement}
          class="timeline-range-input timeline-range-input-end"
          type="range"
          min={startValue}
          max={bounds.endSequence}
          value={endValue}
          disabled={disabled}
          aria-label="Section end sequence"
          title="Adjust the end of the selected section"
          on:input={handleEndInput}
        />
        <span
          class="timeline-thumb timeline-thumb-start"
          class:active={activeThumb === 'start'}
          aria-hidden="true"
          style={`left: ${selectedStartPercent}%;`}
          on:pointerdown={(event) => handleThumbPointerDown('start', event)}
        ></span>
        <span
          class="timeline-thumb timeline-thumb-end"
          class:active={activeThumb === 'end'}
          aria-hidden="true"
          style={`left: ${selectedEndPercent}%;`}
          on:pointerdown={(event) => handleThumbPointerDown('end', event)}
        ></span>
      </div>
      <IconButton icon="fit" label="Reset timeline to full lap" title="Reset timeline to full lap" disabled={disabled} onClick={resetToFullLap} />
    </div>
  {:else}
    <p class="review-timeline-empty">{message}</p>
  {/if}
</div>

<style>
  .review-timeline {
    border: 1px solid #3f3f46;
    border-radius: 1rem;
    display: grid;
    gap: 0.75rem;
    padding: 1rem;
  }

  .review-timeline-label {
    align-items: center;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
  }

  .review-timeline-label span,
  .review-timeline-empty {
    color: #a1a1aa;
  }

  .review-timeline-empty {
    margin: 0;
  }

  .review-timeline-controls {
    align-items: center;
    display: grid;
    gap: 0.75rem;
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .timeline-range-control {
    margin-inline: 0.75rem;
    min-width: 0;
    position: relative;
    height: 2.35rem;
  }

  .timeline-track,
  .timeline-selected-segment {
    border-radius: 999px;
    height: 0.45rem;
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
  }

  .timeline-track {
    background: #111113;
    border: 1px solid #3f3f46;
    left: 0;
    right: 0;
  }

  .timeline-selected-segment {
    background: linear-gradient(90deg, #a1a1aa, #e4e4e7);
    border: 1px solid #71717a;
    box-shadow: 0 0 0 1px rgb(212 212 216 / 22%);
    pointer-events: none;
  }

  .timeline-range-input {
    background: transparent;
    height: 2.35rem;
    left: 0;
    margin: 0;
    opacity: 0;
    pointer-events: none;
    position: absolute;
    top: 0;
    width: 100%;
    z-index: 1;
  }

  .timeline-range-input:focus {
    outline: none;
  }

  .timeline-thumb {
    background: #e4e4e7;
    border: 2px solid #71717a;
    border-radius: 999px;
    box-shadow: 0 0 0 3px rgb(212 212 216 / 22%);
    cursor: grab;
    height: 1.2rem;
    pointer-events: auto;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 1.2rem;
    z-index: 5;
  }

  .timeline-thumb-end {
    z-index: 6;
  }

  .timeline-thumb.active {
    cursor: grabbing;
    z-index: 7;
  }

  .timeline-range-input-start:focus-visible ~ .timeline-thumb-start,
  .timeline-range-input-end:focus-visible ~ .timeline-thumb-end {
    box-shadow: 0 0 0 4px rgb(161 161 170 / 40%);
  }

  .timeline-range-control.disabled .timeline-thumb {
    background: #52525b;
    border-color: #71717a;
    box-shadow: none;
    cursor: not-allowed;
    pointer-events: none;
  }

  @media (max-width: 720px) {
    .review-timeline-controls {
      align-items: stretch;
      grid-template-columns: 1fr;
    }
  }
</style>
