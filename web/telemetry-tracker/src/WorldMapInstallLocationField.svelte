<script lang="ts">
  import Icon from './Icon.svelte';

  export let value = '';
  export let disabled = false;
  export let inputElement: HTMLInputElement | null = null;

  const inputId = `world-map-install-location-${Math.random().toString(36).slice(2)}`;
  const helpId = `${inputId}-help`;
  const placeholder = 'e.g. C:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6';
  const POPOVER_WIDTH = 300;
  const POPOVER_HEIGHT = 230;
  const POPOVER_GAP = 12;

  let helpOpen = false;
  let helpLeft = POPOVER_GAP;
  let helpTop = POPOVER_GAP;

  function toggleHelp(event: MouseEvent) {
    const trigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
    const rect = trigger?.getBoundingClientRect();
    const anchorX = event.clientX || (rect ? rect.left + rect.width / 2 : POPOVER_GAP);
    const anchorY = event.clientY || (rect ? rect.bottom : POPOVER_GAP);
    helpLeft = clamp(anchorX + POPOVER_GAP, POPOVER_GAP, window.innerWidth - POPOVER_WIDTH - POPOVER_GAP);
    helpTop = clamp(anchorY + POPOVER_GAP, POPOVER_GAP, window.innerHeight - POPOVER_HEIGHT - POPOVER_GAP);
    helpOpen = !helpOpen;
  }

  function clamp(value: number, min: number, max: number) {
    return Math.max(min, Math.min(value, Math.max(min, max)));
  }
</script>

<div class="world-map-install-location">
  <div class="world-map-install-location-label-row">
    <label for={inputId}>FH6 Local Install Location</label>
    <button
      type="button"
      class="world-map-install-location-help"
      aria-label="How to find the FH6 install folder"
      aria-pressed={helpOpen}
      title="How to find the FH6 install folder"
      on:click={toggleHelp}
    >
      <Icon name="help" size={18} />
    </button>
  </div>
  <input
    id={inputId}
    aria-describedby={helpOpen ? helpId : undefined}
    aria-label="FH6 Local Install Location"
    bind:this={inputElement}
    bind:value
    {placeholder}
    {disabled}
  />
  {#if helpOpen}
    <div
      id={helpId}
      class="world-map-install-location-popover"
      role="dialog"
      aria-label="How to find the FH6 install folder"
      style={`left: ${helpLeft}px; top: ${helpTop}px;`}
    >
      <ol>
        <li>Start the game.</li>
        <li>Open Task Manager.</li>
        <li>Right click the FH6 process.</li>
        <li>Click Open file location.</li>
      </ol>
      <p>The folder that opens is the folder the tracker needs the filepath for to find the map assets.</p>
    </div>
  {/if}
</div>

<style>
  .world-map-install-location {
    display: grid;
    gap: 0.35rem;
    min-width: 0;
    width: 100%;
  }

  .world-map-install-location-label-row {
    align-items: center;
    display: flex;
    gap: 0.4rem;
    justify-content: flex-start;
  }

  .world-map-install-location-label-row label {
    color: var(--text-secondary);
  }

  .world-map-install-location-help {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 0.35rem;
    color: var(--text-secondary);
    display: inline-flex;
    height: 1.75rem;
    justify-content: center;
    padding: 0;
    width: 1.75rem;
  }

  .world-map-install-location-help:hover,
  .world-map-install-location-help:focus-visible,
  .world-map-install-location-help[aria-pressed='true'] {
    color: var(--text-primary);
  }

  .world-map-install-location-help:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  .world-map-install-location input {
    background: #18181b;
    border: 1px solid var(--panel-border);
    border-radius: 0.65rem;
    box-sizing: border-box;
    color: #e2e8f0;
    min-width: 0;
    padding: 0.5rem 0.6rem;
    width: 100%;
  }

  .world-map-install-location-popover {
    background: #111827;
    border: 1px solid var(--panel-border);
    border-radius: 0.65rem;
    box-shadow: 0 18px 45px rgb(0 0 0 / 42%);
    color: var(--text-primary);
    display: grid;
    gap: 0.55rem;
    max-width: min(300px, calc(100vw - 24px));
    padding: 0.75rem 0.85rem;
    position: fixed;
    z-index: 60;
  }

  .world-map-install-location-popover ol,
  .world-map-install-location-popover p {
    margin: 0;
  }

  .world-map-install-location-popover ol {
    display: grid;
    gap: 0.25rem;
    padding-left: 1.25rem;
  }

  .world-map-install-location-popover p {
    color: var(--text-secondary);
    line-height: 1.35;
  }
</style>
