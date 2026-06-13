<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import type { IconName } from './Icon.svelte';
  import Icon from './Icon.svelte';
  import { issueDefinitions, issueIconToneColor, thresholdSummaryForDefinition, type IssueDefinition } from './issueMetadata';
  import IconButton from './IconButton.svelte';
  import type { OverlayId } from './types';

  export let selected: OverlayId = 'issues';
  export let disabledOverlays: OverlayId[] = [];
  export let disabledReasons: Partial<Record<OverlayId, string>> = {};

  let overlayLegendExpanded = true;
  let overlayToolbarWidth = 0;
  let overlayToolbarElement: HTMLDivElement | null = null;

  const dispatch = createEventDispatcher<{
    change: { overlay: OverlayId };
  }>();

  type LegendKeyItem = {
    label: string;
    color: string;
  };

  type OverlayOption = {
    id: OverlayId;
    label: string;
    title: string;
    icon: IconName;
    className: string;
    legend: {
      description: string;
      keyLabel: string;
      items: LegendKeyItem[];
    };
    issueDefinitions?: IssueDefinition[];
  };

  const overlays: OverlayOption[] = [
    {
      id: 'issues',
      label: 'Issues',
      title: 'Show issue markers overlay',
      icon: 'overlayIssues',
      className: 'icon-report',
      legend: {
        description: 'Discrete issue markers show detected telemetry events. Hover an issue marker to inspect nearby issues; click to pin the popover.',
        keyLabel: 'Detected issue types',
        items: []
      },
      issueDefinitions
    },
    {
      id: 'speed',
      label: 'Speed',
      title: 'Show speed overlay',
      icon: 'speed',
      className: 'icon-speed',
      legend: {
        description: 'Red is slower, yellow is mid-range, green is faster for the loaded lap data.',
        keyLabel: 'Relative speed',
        items: [
          { label: 'Slower', color: '#ff0000' },
          { label: 'Mid', color: '#ffff00' },
          { label: 'Faster', color: '#00ff00' }
        ]
      }
    },
    {
      id: 'inputs',
      label: 'Inputs',
      title: 'Show throttle and brake overlay',
      icon: 'inputs',
      className: 'icon-inputs',
      legend: {
        description: 'Green shows throttle-dominant segments. Red shows brake-dominant segments. Intensity reflects input strength.',
        keyLabel: 'Dominant input',
        items: [
          { label: 'Throttle', color: '#22c55e' },
          { label: 'Brake', color: '#ef4444' }
        ]
      }
    },
    {
      id: 'grip',
      label: 'Grip',
      title: 'Show grip overlay',
      icon: 'grip',
      className: 'icon-grip',
      legend: {
        description: 'Green indicates settled grip, yellow shows rising slip, red flags heavy slip.',
        keyLabel: 'Slip level',
        items: [
          { label: 'Settled', color: '#84cc16' },
          { label: 'Rising', color: '#eab308' },
          { label: 'Heavy', color: '#dc2626' }
        ]
      }
    },
    {
      id: 'temperature',
      label: 'Temperature',
      title: 'Show tyre temperature overlay',
      icon: 'temperature',
      className: 'icon-temperature',
      legend: {
        description: 'Green is cooler, yellow is mid-range, red is hotter for the loaded tyre temperature data.',
        keyLabel: 'Tyre temperature',
        items: [
          { label: 'Cooler', color: '#00ff00' },
          { label: 'Mid', color: '#ffff00' },
          { label: 'Hotter', color: '#ff0000' }
        ]
      }
    },
    {
      id: 'suspension',
      label: 'Suspension',
      title: 'Show suspension travel overlay',
      icon: 'suspension',
      className: 'icon-suspension',
      legend: {
        description: 'Green is lower travel, yellow is mid travel, red is higher travel.',
        keyLabel: 'Travel',
        items: [
          { label: 'Lower', color: '#00ff00' },
          { label: 'Mid', color: '#ffff00' },
          { label: 'Higher', color: '#ff0000' }
        ]
      }
    },
    {
      id: 'rpm',
      label: 'RPM',
      title: 'Show engine RPM overlay',
      icon: 'rpm',
      className: 'icon-rpm',
      legend: {
        description: 'Green is lower rev range, yellow is mid range, red is near the engine limit.',
        keyLabel: 'Rev range',
        items: [
          { label: 'Lower', color: '#00ff00' },
          { label: 'Mid', color: '#ffff00' },
          { label: 'Limit', color: '#ff0000' }
        ]
      }
    }
  ];

  $: selectedOverlay = overlays.find((overlay) => overlay.id === selected) ?? overlays[0];
  $: overlayLegendStyle = overlayToolbarWidth > 0 ? `width: ${overlayToolbarWidth}px;` : undefined;

  function isDisabled(overlay: OverlayId): boolean {
    return disabledOverlays.includes(overlay);
  }

  function toggleOverlayLegend() {
    overlayLegendExpanded = !overlayLegendExpanded;
  }

  function updateOverlayToolbarWidth() {
    overlayToolbarWidth = overlayToolbarElement?.getBoundingClientRect().width ?? 0;
  }

  function selectOverlay(overlay: OverlayId) {
    if (isDisabled(overlay)) return;
    dispatch('change', { overlay });
  }

  onMount(() => {
    tick().then(updateOverlayToolbarWidth);
    window.addEventListener('resize', updateOverlayToolbarWidth);

    return () => {
      window.removeEventListener('resize', updateOverlayToolbarWidth);
    };
  });
</script>

<section class="overlay-toolbar-panel" aria-label="Telemetry overlays">
  <div class="overlay-toolbar" bind:this={overlayToolbarElement}>
    {#each overlays as overlay}
      <IconButton
        icon={overlay.icon}
        label={overlay.label}
        title={disabledOverlays.includes(overlay.id) ? disabledReasons[overlay.id] ?? overlay.title : overlay.title}
        pressed={selected === overlay.id}
        disabled={disabledOverlays.includes(overlay.id)}
        className={`overlay-button ${selected === overlay.id ? 'selected' : ''} ${overlay.className}`}
        onClick={() => selectOverlay(overlay.id)}
      />
    {/each}
  </div>

  <aside class:overlay-legend-collapsed={!overlayLegendExpanded} class="overlay-legend" style={overlayLegendStyle} aria-live="polite" data-testid="overlay-legend">
    <button
      class="overlay-legend-header"
      type="button"
      aria-expanded={overlayLegendExpanded}
      aria-label={`${overlayLegendExpanded ? 'Collapse' : 'Expand'} selected overlay info for ${selectedOverlay.label}`}
      title={`${overlayLegendExpanded ? 'Collapse' : 'Expand'} selected overlay info`}
      on:click={toggleOverlayLegend}
    >
      <span class="overlay-legend-kicker">Selected Overlay</span>
      <strong>{selectedOverlay.label}</strong>
    </button>
    {#if overlayLegendExpanded}
      <p>{selectedOverlay.legend.description}</p>
      {#if selectedOverlay.id === 'issues' && selectedOverlay.issueDefinitions}
        <div class="overlay-issue-definitions" role="group" aria-label="Detected issue types">
          <span class="overlay-legend-key-label">Detected issue types</span>
          <ul>
            {#each selectedOverlay.issueDefinitions as definition}
              <li>
                <span class={`overlay-issue-icon issue-icon-tone-${definition.iconTone}`} style={`color: ${issueIconToneColor(definition.iconTone)};`} aria-hidden="true">
                  <Icon name={definition.icon} size={16} />
                </span>
                <span class="overlay-issue-copy">
                  <strong>{definition.issueKind}</strong>
                  <small>{thresholdSummaryForDefinition(definition)}</small>
                </span>
              </li>
            {/each}
          </ul>
        </div>
      {:else}
        <div class="overlay-legend-key" role="group" aria-label={selectedOverlay.legend.keyLabel}>
          <span class="overlay-legend-key-label">{selectedOverlay.legend.keyLabel}</span>
          <ul>
            {#each selectedOverlay.legend.items as item}
              <li><span class="overlay-legend-swatch" style={`--legend-colour: ${item.color};`} aria-hidden="true"></span><span>{item.label}</span></li>
            {/each}
          </ul>
        </div>
      {/if}
    {/if}
  </aside>
</section>

<style>
  .overlay-toolbar-panel {
    align-items: flex-start;
    display: inline-flex;
    flex-direction: column;
    gap: 0.55rem;
    max-width: min(28rem, calc(100vw - var(--dashboard-menu-width) - var(--canvas-floating-margin) - var(--canvas-floating-margin)));
  }

  .overlay-toolbar {
    display: inline-flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    max-width: 100%;
  }

  .overlay-legend {
    backdrop-filter: var(--canvas-overlay-backdrop-filter);
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 0.9rem;
    box-shadow: 0 12px 34px rgb(0 0 0 / 32%);
    box-sizing: border-box;
    color: var(--text-primary);
    display: grid;
    gap: 0.45rem;
    max-width: 100%;
    min-width: 0;
    padding: 0.7rem 0.8rem;
  }

  .overlay-legend-header {
    align-items: baseline;
    background: transparent;
    border: 0;
    color: inherit;
    cursor: pointer;
    display: flex;
    font: inherit;
    gap: 0.5rem;
    justify-content: space-between;
    margin: 0;
    padding: 0;
    text-align: left;
    width: 100%;
  }

  .overlay-legend-header:focus-visible {
    border-radius: 0.35rem;
    outline: 2px solid var(--focus-ring);
    outline-offset: 4px;
  }

  .overlay-legend-collapsed {
    gap: 0;
  }

  .overlay-legend-kicker,
  .overlay-legend-key-label {
    color: var(--text-muted);
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .overlay-legend strong {
    font-size: 0.95rem;
  }

  .overlay-legend p {
    color: var(--text-secondary);
    font-size: 0.82rem;
    line-height: 1.35;
    margin: 0;
  }

  .overlay-legend-key {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem 0.6rem;
  }

  .overlay-legend-key ul {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .overlay-legend-key li {
    align-items: center;
    color: #d4d4d8;
    display: inline-flex;
    font-size: 0.76rem;
    gap: 0.3rem;
  }

  .overlay-legend-swatch {
    background: var(--legend-colour);
    border: 1px solid rgb(244 244 245 / 42%);
    border-radius: 999px;
    box-shadow: 0 0 0 1px rgb(0 0 0 / 32%);
    display: inline-block;
    height: 0.65rem;
    width: 0.65rem;
  }

  .overlay-issue-definitions { display: grid; gap: 0.45rem; }
  .overlay-issue-definitions ul { display: grid; gap: 0.45rem; grid-template-columns: 1fr; list-style: none; margin: 0; padding: 0; }
  .overlay-issue-definitions li { align-items: center; display: grid; gap: 0.45rem; grid-template-columns: auto 1fr; }
  .overlay-issue-icon { align-items: center; background: #27272a; border: 1px solid #3f3f46; border-radius: 999px; color: #e4e4e7; display: inline-flex; height: 1.65rem; justify-content: center; width: 1.65rem; }
  .overlay-issue-copy { display: grid; gap: 0.05rem; min-width: 0; }
  .overlay-issue-copy strong { color: #e4e4e7; font-size: 0.78rem; }
  .overlay-issue-copy small { color: var(--text-secondary); font-size: 0.72rem; line-height: 1.25; }

  @media (max-width: 680px) {
    .overlay-toolbar-panel {
      max-width: calc(100vw - var(--canvas-floating-margin) - var(--canvas-floating-margin));
    }
  }
</style>
