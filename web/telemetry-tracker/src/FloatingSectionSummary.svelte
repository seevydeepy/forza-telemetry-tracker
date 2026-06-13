<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import IconButton from './IconButton.svelte';
  import LapBreakdown from './LapBreakdown.svelte';
  import type { AnalysisSummary, DeltaSummary, LapSummary, ReferenceLap, SequenceRange, UnitSystem } from './types';

  export let summary: AnalysisSummary | null = null;
  export let deltaSummary: DeltaSummary | null = null;
  export let selectedLap: LapSummary | null = null;
  export let selectedRange: SequenceRange | null = null;
  export let unitSystem: UnitSystem | string = 'imperial';
  export let referenceLap: ReferenceLap | null = null;
  export let x = 0;
  export let y = 0;
  export let cardElement: HTMLElement | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
    move: { x: number; y: number };
    trackchange: { lapId: string };
  }>();

  let dragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let originX = 0;
  let originY = 0;

  type DragEvent = MouseEvent | PointerEvent;

  function startDrag(event: DragEvent) {
    if (event.button !== 0) return;
    dragging = true;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    originX = x;
    originY = y;
    event.preventDefault();
  }

  function moveDrag(event: DragEvent) {
    if (!dragging) return;
    dispatch('move', { x: originX + event.clientX - dragStartX, y: originY + event.clientY - dragStartY });
  }

  function stopDrag() {
    dragging = false;
  }

  function handleDragHandleKeydown(event: KeyboardEvent) {
    const step = event.shiftKey ? 48 : 16;
    switch (event.key) {
      case 'ArrowLeft':
        dispatch('move', { x: x - step, y });
        break;
      case 'ArrowRight':
        dispatch('move', { x: x + step, y });
        break;
      case 'ArrowUp':
        dispatch('move', { x, y: y - step });
        break;
      case 'ArrowDown':
        dispatch('move', { x, y: y + step });
        break;
      case 'Home':
        dispatch('move', { x: 0, y: 0 });
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  $: title = selectedRange ? 'Selected section summary' : 'Full lap summary';
  $: packetBadge = summary ? `${summary.packet_count.toLocaleString()} packets` : '';
  $: dragHandleHelp = 'Drag section summary. Use arrow keys to move, Shift plus arrow keys for larger moves, or Home to reset.';
</script>

<svelte:window on:pointermove={moveDrag} on:pointerup={stopDrag} on:mousemove={moveDrag} on:mouseup={stopDrag} />

<section
  bind:this={cardElement}
  class="floating-section-summary"
  role="complementary"
  aria-label="Section summary"
  data-summary-x={x}
  data-summary-y={y}
  style={`--summary-x: ${x}px; --summary-y: ${y}px;`}
>
  <header class="floating-section-summary-header">
    <button
      type="button"
      class="floating-section-summary-drag-handle"
      aria-label={dragHandleHelp}
      title={dragHandleHelp}
      on:pointerdown={startDrag}
      on:mousedown={startDrag}
      on:keydown={handleDragHandleKeydown}
    >
      <strong>{title}</strong>
    </button>
    {#if packetBadge}
      <span class="floating-section-summary-packet-badge">{packetBadge}</span>
    {/if}
    <IconButton icon="close" label="Hide section summary" title="Hide section summary" className="floating-section-summary-close" onClick={() => dispatch('close')} />
  </header>
  <div class="floating-section-summary-body">
    <LapBreakdown
      {summary}
      {deltaSummary}
      {selectedLap}
      {selectedRange}
      {unitSystem}
      {referenceLap}
      on:trackchange={(event) => dispatch('trackchange', event.detail)}
    />
  </div>
</section>
