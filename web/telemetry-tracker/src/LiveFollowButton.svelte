<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';

  export let paused = false;

  const dispatch = createEventDispatcher<{
    toggle: void;
  }>();
</script>

<button
  type="button"
  class="live-follow-button"
  class:paused
  aria-label="Live follow"
  aria-pressed={paused}
  title={paused ? 'Resume live follow' : 'Pause live follow'}
  on:click={() => dispatch('toggle')}
>
  <Icon name={paused ? 'play' : 'pause'} size={14} />
  <span>{paused ? 'Live follow paused' : 'Live follow running'}</span>
</button>

<style>
  .live-follow-button {
    align-items: center;
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid #22c55e;
    border-radius: 999px;
    box-shadow: 0 12px 34px rgb(0 0 0 / 32%);
    color: #f4f4f5;
    display: inline-flex;
    font: inherit;
    font-size: 0.78rem;
    font-weight: 650;
    gap: 0.45rem;
    min-height: 36px;
    padding: 0.35rem 0.7rem;
    white-space: nowrap;
  }

  .live-follow-button.paused {
    border-color: #f59e0b;
    color: #fde68a;
  }

  .live-follow-button:focus-visible {
    outline: 2px solid #a1a1aa;
    outline-offset: 2px;
  }
</style>
