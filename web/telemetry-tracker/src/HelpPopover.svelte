<script lang="ts">
  import Icon from './Icon.svelte';

  export let label: string;
  export let popoverLabel = label;
  export let buttonClass = '';

  const popoverId = `help-popover-${Math.random().toString(36).slice(2)}`;
  const POPOVER_WIDTH = 320;
  const POPOVER_HEIGHT = 240;
  const POPOVER_GAP = 12;

  let open = false;
  let left = POPOVER_GAP;
  let top = POPOVER_GAP;
  let button: HTMLButtonElement | null = null;
  let popover: HTMLDivElement | null = null;

  function toggle(event: MouseEvent) {
    const trigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
    const rect = trigger?.getBoundingClientRect();
    const anchorX = event.clientX || (rect ? rect.left + rect.width / 2 : POPOVER_GAP);
    const anchorY = event.clientY || (rect ? rect.bottom : POPOVER_GAP);
    left = clamp(anchorX + POPOVER_GAP, POPOVER_GAP, window.innerWidth - POPOVER_WIDTH - POPOVER_GAP);
    top = clamp(anchorY + POPOVER_GAP, POPOVER_GAP, window.innerHeight - POPOVER_HEIGHT - POPOVER_GAP);
    open = !open;
  }

  function handleDocumentPointerDown(event: PointerEvent) {
    if (!open) return;
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (button?.contains(target) || popover?.contains(target)) return;
    open = false;
  }

  function clamp(value: number, min: number, max: number) {
    return Math.max(min, Math.min(value, Math.max(min, max)));
  }
</script>

<svelte:document on:pointerdown={handleDocumentPointerDown} />

<button
  bind:this={button}
  type="button"
  class={`help-popover-button ${buttonClass}`.trim()}
  aria-label={label}
  aria-controls={open ? popoverId : undefined}
  aria-describedby={open ? popoverId : undefined}
  aria-pressed={open}
  title={label}
  on:click={toggle}
>
  <Icon name="help" size={18} />
</button>

{#if open}
  <div
    bind:this={popover}
    id={popoverId}
    class="help-popover"
    role="dialog"
    aria-label={popoverLabel}
    style={`left: ${left}px; top: ${top}px;`}
  >
    <slot />
  </div>
{/if}

<style>
  .help-popover-button {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 0.35rem;
    color: var(--text-secondary);
    display: inline-flex;
    flex: 0 0 auto;
    height: 1.75rem;
    justify-content: center;
    padding: 0;
    width: 1.75rem;
  }

  .help-popover-button:hover,
  .help-popover-button:focus-visible,
  .help-popover-button[aria-pressed='true'] {
    color: var(--text-primary);
  }

  .help-popover-button:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  .help-popover {
    background: #111827;
    border: 1px solid var(--panel-border);
    border-radius: 0.65rem;
    box-shadow: 0 18px 45px rgb(0 0 0 / 42%);
    color: var(--text-primary);
    display: grid;
    gap: 0.55rem;
    max-width: min(320px, calc(100vw - 24px));
    padding: 0.75rem 0.85rem;
    position: fixed;
    z-index: 70;
  }

  :global(.help-popover p) {
    color: var(--text-secondary);
    line-height: 1.35;
    margin: 0;
  }
</style>
