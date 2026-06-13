<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
  import Icon from './Icon.svelte';
  import { DASHBOARD_WIDGETS } from './dashboardWidgets';
  import type { DashboardWidgetId } from './types';

  export let enabledWidgets: Record<DashboardWidgetId, boolean>;

  const dispatch = createEventDispatcher<{ toggle: { widgetId: DashboardWidgetId }; showall: void }>();

  const popoverId = 'dashboard-widget-visibility-popover';
  let open = false;
  let root: HTMLDivElement | null = null;
  let button: HTMLButtonElement | null = null;

  function toggleOpen() {
    open = !open;
  }

  function close({ restoreFocus = false } = {}) {
    if (!open) return;
    open = false;
    if (restoreFocus) {
      void tick().then(() => button?.focus());
    }
  }

  function handleWindowClick(event: MouseEvent) {
    if (!open || !root || root.contains(event.target as Node)) return;
    close();
  }

  function handleWindowKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      close({ restoreFocus: true });
    }
  }
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleWindowKeydown} />

<div bind:this={root} class="dashboard-visibility">
  <button
    bind:this={button}
    type="button"
    class="visibility-button"
    aria-label="Choose dashboard widgets"
    aria-expanded={open}
    aria-controls={popoverId}
    on:click={toggleOpen}
  >
    <Icon name="visibility" />
  </button>
  {#if open}
    <div id={popoverId} class="visibility-popover" role="region" aria-label="Dashboard widget visibility">
      <header>
        <strong>Dashboard widgets</strong>
        <button type="button" on:click={() => dispatch('showall')}>Show all</button>
      </header>
      <div class="visibility-list">
        {#each DASHBOARD_WIDGETS as widget}
          <button type="button" aria-pressed={enabledWidgets[widget.id]} on:click={() => dispatch('toggle', { widgetId: widget.id })}>
            <span>{widget.label}</span>
            <strong>{enabledWidgets[widget.id] ? 'Shown' : 'Hidden'}</strong>
          </button>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .dashboard-visibility {
    position: relative;
  }

  .visibility-button {
    align-items: center;
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 999px;
    color: #f4f4f5;
    display: inline-flex;
    height: 2.85rem;
    justify-content: center;
    width: 2.85rem;
  }

  button:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  .visibility-popover {
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 1rem;
    box-shadow: 0 20px 60px rgb(0 0 0 / 38%);
    min-width: 18rem;
    padding: 0.75rem;
    position: absolute;
    right: 0;
    top: calc(100% + 0.5rem);
    z-index: 15;
  }

  header {
    align-items: center;
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.65rem;
  }

  header button,
  .visibility-list button {
    background: var(--canvas-overlay-control-bg);
    border: 1px solid #3f3f46;
    border-radius: 0.75rem;
    color: #f4f4f5;
  }

  header button {
    padding: 0.35rem 0.55rem;
  }

  .visibility-list {
    display: grid;
    gap: 0.4rem;
  }

  .visibility-list button {
    align-items: center;
    display: flex;
    justify-content: space-between;
    padding: 0.55rem 0.65rem;
    text-align: left;
  }

  .visibility-list button[aria-pressed='false'] {
    color: #a1a1aa;
    opacity: 0.72;
  }

  .visibility-list strong {
    font-size: 0.75rem;
  }
</style>
