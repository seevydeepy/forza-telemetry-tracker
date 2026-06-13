<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import IconButton from './IconButton.svelte';
  import type { CarInfo } from './types';

  export let car: CarInfo | null = null;
  export let x = 0;
  export let y = 0;
  export let expanded = false;
  export let cardElement: HTMLElement | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
    move: { x: number; y: number };
    expandedchange: { expanded: boolean };
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

  function toggleExpanded() {
    dispatch('expandedchange', { expanded: !expanded });
  }

  function formatInteger(value: number | null | undefined) {
    return value == null ? '—' : Math.round(value).toLocaleString();
  }

  function formatPower(value: number | null | undefined) {
    return value == null ? '—' : `${Math.round(value / 1000).toLocaleString()} kW`;
  }

  function formatTorque(value: number | null | undefined) {
    return value == null ? '—' : `${Math.round(value).toLocaleString()} Nm`;
  }

  function formatCarGroup(label: string | null | undefined, value: number | null | undefined) {
    return label ?? formatInteger(value);
  }

  function normalizePerformanceClass(label: string | null | undefined) {
    const normalized = label?.trim().toUpperCase();
    return normalized && ['D', 'C', 'B', 'A', 'S1', 'S2', 'R', 'X'].includes(normalized) ? normalized : 'unknown';
  }

  $: title = car?.name ?? 'Unknown';
  $: performanceClassLabel = car?.class_label ?? '--';
  $: performanceIndexLabel = car?.performance_index ?? '---';
  $: performanceText = `${performanceClassLabel} | ${performanceIndexLabel}`;
  $: performanceClassKey = normalizePerformanceClass(car?.class_label);
  $: dragHandleHelp = 'Drag car info. Use arrow keys to move, Shift plus arrow keys for larger moves, or Home to reset.';
  $: dragHandleAccessibleLabel = `${title}${car?.year ? ` ${car.year}` : ''}. ${dragHandleHelp}`;
</script>

<svelte:window on:pointermove={moveDrag} on:pointerup={stopDrag} on:mousemove={moveDrag} on:mouseup={stopDrag} />

<section
  bind:this={cardElement}
  class:expanded
  class="floating-car-info"
  role="complementary"
  aria-label="Car info"
  data-car-info-anchor="bottom-left"
  data-car-info-x={x}
  data-car-info-y={y}
  style={`--car-info-x: ${x}px; --car-info-y: ${y}px;`}
>
  <article class="car-info-card">
    <header class="car-info-card__chrome-header">
      <button
        type="button"
        class="car-info-card__chrome-drag-handle"
        aria-label={dragHandleAccessibleLabel}
        title={dragHandleHelp}
        on:pointerdown={startDrag}
        on:mousedown={startDrag}
        on:keydown={handleDragHandleKeydown}
      >
        <span class="car-info-card__chrome-title">
          <span class="car-info-card__chrome-car-name">{title}</span>
          {#if car?.year}
            <span class="car-info-card__chrome-year">{car.year}</span>
          {/if}
        </span>
      </button>
      <IconButton icon="close" label="Dismiss card" title="Dismiss card" className="car-info-card__close" onClick={() => dispatch('close')} />
    </header>

    <div class="car-info-card__body">
      <div class="car-info-card__summary">
        <div class="car-info-card__performance" aria-label={`Performance ${performanceText}`} data-car-performance-class={performanceClassKey}>
          <span class="car-info-card__class-label">{performanceClassLabel}</span>
          <span class="car-info-card__performance-separator" aria-hidden="true"> | </span>
          <span class="car-info-card__pi-label">{performanceIndexLabel}</span>
        </div>
        {#if car?.drivetrain_label}
          <div class="car-info-card__drivetrain">{car.drivetrain_label}</div>
        {/if}
      </div>

      {#if expanded}
        <dl class="car-info-card__details" aria-label="Curated car details">
          <div><dt>Ordinal</dt><dd>{car?.ordinal ?? '—'}</dd></div>
          <div><dt>Engine max</dt><dd>{formatInteger(car?.details.engine_max_rpm)} rpm</dd></div>
          <div><dt>Cylinders</dt><dd>{formatInteger(car?.details.num_cylinders)}</dd></div>
          <div><dt>Car group</dt><dd>{formatCarGroup(car?.details.car_group_label, car?.details.car_group)}</dd></div>
          <div><dt>Peak power</dt><dd>{formatPower(car?.details.peak_power_w)}</dd></div>
          <div><dt>Peak torque</dt><dd>{formatTorque(car?.details.peak_torque_nm)}</dd></div>
        </dl>
      {/if}

      <button
        type="button"
        class="car-info-card__expand"
        aria-label={expanded ? 'Collapse car details' : 'Expand car details'}
        title={expanded ? 'Collapse car details' : 'Expand car details'}
        on:click={toggleExpanded}
      >
        <Icon name={expanded ? 'collapseAll' : 'expandAll'} size={16} />
      </button>
    </div>
  </article>
</section>
