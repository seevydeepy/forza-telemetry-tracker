<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import { SHORTCUTS } from './KeyboardShortcuts';

  const dispatch = createEventDispatcher<{
    close: void;
  }>();

  let closeButton: HTMLButtonElement | null = null;

  onMount(() => {
    void tick().then(() => closeButton?.focus({ preventScroll: true }));
  });
</script>

<section class="shortcut-backdrop">
  <div class="shortcut-dialog" role="dialog" aria-modal="false" aria-label="Keyboard shortcuts">
    <header class="shortcut-header">
      <div>
        <p class="eyebrow">Forza Telemetry Tracker</p>
        <h2>Keyboard shortcuts</h2>
      </div>
      <button
        bind:this={closeButton}
        type="button"
        class="icon-button"
        aria-label="Close keyboard shortcuts"
        title="Close keyboard shortcuts"
        on:click={() => dispatch('close')}
      >
        ×
      </button>
    </header>

    <dl class="shortcut-list">
      {#each SHORTCUTS as shortcut}
        <div>
          <dt><kbd>{shortcut.key}</kbd></dt>
          <dd>{shortcut.label}</dd>
        </div>
      {/each}
    </dl>
  </div>
</section>

<style>
  .shortcut-backdrop {
    align-items: flex-start;
    display: flex;
    inset: 0;
    justify-content: flex-start;
    padding: 1rem 1rem 1rem 4.75rem;
    pointer-events: none;
    position: fixed;
    z-index: 7;
  }

  .shortcut-dialog {
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid #3f3f46;
    border-radius: 1rem;
    box-shadow: 0 18px 40px rgb(0 0 0 / 42%);
    color: #f4f4f5;
    display: grid;
    gap: 1rem;
    max-width: min(30rem, calc(100vw - 6rem));
    padding: 1rem;
    pointer-events: auto;
    width: 24rem;
  }

  .shortcut-header {
    align-items: start;
    display: flex;
    gap: 1rem;
    justify-content: space-between;
  }

  .shortcut-header h2,
  .eyebrow,
  .shortcut-list {
    margin: 0;
  }

  .shortcut-header h2 {
    color: #d4d4d8;
    font-size: 1.15rem;
  }

  .eyebrow {
    color: #a1a1aa;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    margin-bottom: 0.2rem;
    text-transform: uppercase;
  }

  .icon-button {
    align-items: center;
    background: var(--canvas-overlay-control-bg);
    border: 1px solid #3f3f46;
    border-radius: 0.75rem;
    color: #f4f4f5;
    display: inline-flex;
    font-size: 1.2rem;
    height: 40px;
    justify-content: center;
    width: 40px;
  }

  .shortcut-list {
    display: grid;
    gap: 0.65rem;
  }

  .shortcut-list div {
    align-items: center;
    background: var(--canvas-overlay-control-bg);
    border: 1px solid #27272a;
    border-radius: 0.75rem;
    display: grid;
    gap: 0.75rem;
    grid-template-columns: 5rem 1fr;
    padding: 0.65rem 0.75rem;
  }

  kbd {
    background: #09090b;
    border: 1px solid #52525b;
    border-radius: 0.45rem;
    color: #e4e4e7;
    display: inline-block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
    min-width: 3rem;
    padding: 0.2rem 0.5rem;
    text-align: center;
  }

  dd {
    color: #e2e8f0;
    margin: 0;
  }
</style>
