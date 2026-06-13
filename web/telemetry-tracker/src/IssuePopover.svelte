<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import Icon from './Icon.svelte';
  import IconButton from './IconButton.svelte';
  import { issueDefinitionForMarker, issueIconForMarker, issueIconToneColor, issueValueLine } from './issueMetadata';
  import type { IssueMarker, LiveSample } from './types';

  export type IssuePopoverItem = { marker: IssueMarker; sample: LiveSample | null; elapsedMs: number | null };
  export let items: IssuePopoverItem[] = [];
  export let pinned = false;
  export let x = 16;
  export let y = 16;

  const dispatch = createEventDispatcher<{
    close: void;
    move: { x: number; y: number };
  }>();

  export let card: HTMLElement | null = null;
  let dragging = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let originX = 0;
  let originY = 0;

  function closePopover() {
    dispatch('close');
  }

  function startDrag(event: PointerEvent | MouseEvent) {
    if (event.button !== 0) return;
    if (!(event.target instanceof Element) || !event.target.closest('.issue-popover__chrome-drag-handle')) return;
    if (event.target.closest('.issue-popover__close')) return;
    dragging = true;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    originX = x;
    originY = y;
    event.preventDefault();
  }

  function moveDrag(event: PointerEvent | MouseEvent) {
    if (!dragging) return;
    dispatch('move', { x: originX + event.clientX - dragStartX, y: originY + event.clientY - dragStartY });
  }

  function stopDrag() {
    dragging = false;
  }

  function handleDocumentPointerDown(event: PointerEvent) {
    if (!card) return;
    const target = event.target;
    if (target instanceof Node && !card.contains(target)) {
      closePopover();
    }
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('pointerdown', handleDocumentPointerDown);
  }

  onDestroy(() => {
    if (typeof document !== 'undefined') {
      document.removeEventListener('pointerdown', handleDocumentPointerDown);
    }
  });

  function formatLapTimeFromMs(valueMs: number): string {
    const safeMs = Math.max(0, Math.round(valueMs));
    const minutes = Math.floor(safeMs / 60_000);
    const seconds = Math.floor((safeMs % 60_000) / 1000);
    const milliseconds = safeMs % 1000;
    return `${minutes}:${String(seconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`;
  }

  function formatLapTime(item: IssuePopoverItem | null): string {
    if (typeof item?.elapsedMs === 'number' && Number.isFinite(item.elapsedMs)) return formatLapTimeFromMs(item.elapsedMs);
    if (typeof item?.sample?.current_lap === 'number' && Number.isFinite(item.sample.current_lap)) return formatLapTimeFromMs(item.sample.current_lap * 1000);
    return `sequence ${item?.sample?.sequence ?? item?.marker.anchor_sequence ?? item?.marker.start_sequence ?? ''}`;
  }

  $: primaryItem = items[0] ?? null;
  $: primaryIssueKind = primaryItem ? issueDefinitionForMarker(primaryItem.marker).issueKind : 'Issue';
  $: issueTitle = items.length === 1 ? `${primaryIssueKind} at ${formatLapTime(primaryItem)}` : `${items.length} issues near ${formatLapTime(primaryItem)}`;
  $: interactionHint = pinned ? 'Pinned issue details' : 'Hover issue details · click an issue marker to pin';
</script>

<svelte:window on:pointermove={moveDrag} on:pointerup={stopDrag} on:mousemove={moveDrag} on:mouseup={stopDrag} />

<div
  class:pinned
  class="issue-popover"
  bind:this={card}
  aria-label="Issue details"
  role="dialog"
  tabindex="-1"
  aria-modal="false"
  style={`--issue-popover-x: ${x}px; --issue-popover-y: ${y}px;`}
  on:pointerdown={startDrag}
  on:mousedown={startDrag}
>
  <header class="issue-popover__chrome-header">
    <button
      type="button"
      class="issue-popover__chrome-drag-handle"
      aria-label="Drag issue popover"
      title="Drag issue popover"
      on:pointerdown={startDrag}
      on:mousedown={startDrag}
    >
      <h2 class="issue-popover__chrome-title">{issueTitle}</h2>
      <span class="issue-popover__chrome-subtitle">{interactionHint}</span>
    </button>
    <IconButton icon="close" label="Close issue popover" title="Close issue popover" className="issue-popover__close" onClick={closePopover} />
  </header>

  <div class="issue-list" data-testid="issue-popover-list">
    {#each items as item (item.marker.id)}
      {@const definition = issueDefinitionForMarker(item.marker)}
      <article class="issue-row">
        <span class={`issue-row-icon issue-icon-tone-${definition.iconTone}`} style={`color: ${issueIconToneColor(definition.iconTone)};`} aria-label={`${definition.issueKind} issue icon`} role="img">
          <Icon name={issueIconForMarker(item.marker)} size={18} />
        </span>
        <div class="issue-row-copy">
          <div class="issue-row-title"><strong>{definition.issueKind}</strong><span>{item.marker.severity}</span></div>
          <p>{issueValueLine(item.marker)}</p>
          <small>Sequences {item.marker.start_sequence}–{item.marker.end_sequence}</small>
        </div>
      </article>
    {/each}
  </div>
</div>

<style>
  .issue-popover {
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 1rem;
    box-shadow: 0 18px 40px rgb(0 0 0 / 50%);
    max-height: min(70vh, 24rem);
    overflow: auto;
    pointer-events: none;
    position: absolute;
    left: 0;
    top: 0;
    transform: translate(var(--issue-popover-x), var(--issue-popover-y));
    width: min(28rem, calc(100% - 2rem));
    z-index: 5;
  }

  .issue-popover.pinned {
    pointer-events: auto;
  }

  .issue-popover__chrome-header {
    align-items: center;
    border-bottom: 1px solid var(--panel-border-muted);
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
    min-width: 0;
    padding: 0.65rem 0.75rem;
  }

  .issue-popover__chrome-drag-handle {
    align-items: flex-start;
    align-self: stretch;
    background: transparent;
    border: 0;
    color: inherit;
    cursor: move;
    display: grid;
    flex: 1 1 auto;
    gap: 0.15rem;
    min-width: 0;
    padding: 0;
    text-align: left;
    touch-action: none;
    user-select: none;
  }

  .issue-popover__chrome-title {
    color: #fafafa;
    font-size: 1.05rem;
    font-weight: 800;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .issue-popover__chrome-subtitle {
    color: #a1a1aa;
    font-size: 0.85rem;
  }

  :global(.issue-popover__close.app-icon-button) { flex: 0 0 auto; }
  .issue-popover :global(.app-icon-button) {
    backdrop-filter: none;
    background: var(--canvas-overlay-control-bg);
    box-shadow: none;
  }
  .issue-list { display: grid; gap: 0.55rem; max-height: min(48vh, 20rem); overflow-y: auto; padding: 0.75rem; }
  .issue-row { align-items: flex-start; background: var(--canvas-overlay-control-bg); border: 1px solid #27272a; border-radius: 0.8rem; display: grid; gap: 0.65rem; grid-template-columns: auto 1fr; padding: 0.65rem 0.75rem; }
  .issue-row-icon { align-items: center; background: #27272a; border: 1px solid #3f3f46; border-radius: 999px; color: #e4e4e7; display: inline-flex; height: 2rem; justify-content: center; width: 2rem; }
  .issue-row-copy { display: grid; gap: 0.25rem; min-width: 0; }
  .issue-row-title { align-items: baseline; display: flex; gap: 0.5rem; justify-content: space-between; }
  .issue-row-title span, .issue-row-copy small { color: #a1a1aa; font-size: 0.76rem; text-transform: capitalize; }
  .issue-row-copy p { color: #d4d4d8; font-size: 0.88rem; margin: 0; }
</style>
