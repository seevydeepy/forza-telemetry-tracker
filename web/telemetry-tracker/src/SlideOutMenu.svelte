<script lang="ts" context="module">
  import type { IconName } from './Icon.svelte';

  export type MenuAction =
    | 'new-session'
    | 'import-telemetry'
    | 'export-telemetry'
    | 'session-browser'
    | 'stats'
    | 'diagnostics'
    | 'settings'
    | 'about';

  interface MenuItem {
    action: MenuAction;
    icon: IconName;
    label: string;
    title: string;
    text: string;
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import IconButton from './IconButton.svelte';

  export let expanded = false;

  const FEEDBACK_URL = 'https://github.com/seevydeepy/forza-telemetry-tracker/issues';

  const dispatch = createEventDispatcher<{
    action: { action: MenuAction; opener: HTMLElement };
    toggle: { expanded: boolean };
  }>();

  const menuItems: MenuItem[] = [
    {
      action: 'new-session',
      icon: 'add',
      label: 'New session',
      title: 'Start a new session',
      text: 'New session'
    },
    {
      action: 'import-telemetry',
      icon: 'import',
      label: 'Import raw telemetry',
      title: 'Import raw telemetry',
      text: 'Import raw telemetry'
    },
    {
      action: 'export-telemetry',
      icon: 'exportTelemetry',
      label: 'Export telemetry',
      title: 'Export telemetry',
      text: 'Export telemetry'
    },
    {
      action: 'session-browser',
      icon: 'history',
      label: 'Session browser',
      title: 'Open session browser',
      text: 'Session browser'
    },
    {
      action: 'stats',
      icon: 'leaderboard',
      label: 'Stats',
      title: 'Open stats window',
      text: 'Stats'
    },
    {
      action: 'diagnostics',
      icon: 'diagnostics',
      label: 'Open diagnostics',
      title: 'Open diagnostics',
      text: 'Diagnostics'
    },
    {
      action: 'settings',
      icon: 'settings',
      label: 'Settings',
      title: 'Open telemetry tracker settings',
      text: 'Settings'
    },
    {
      action: 'about',
      icon: 'info',
      label: 'About',
      title: 'About Forza Telemetry Tracker',
      text: 'About'
    }
  ];

  function toggleMenu() {
    dispatch('toggle', { expanded: !expanded });
  }

  function dispatchAction(action: MenuAction, event: MouseEvent) {
    dispatch('action', { action, opener: event.currentTarget as HTMLElement });
  }
</script>

<nav class="slide-out-menu" aria-label="Main menu" data-expanded={expanded ? 'true' : 'false'}>
  <div class="menu-section menu-section-toggle">
    <button
      type="button"
      class="app-icon-button app-icon-button-default slide-menu-button slide-menu-toggle"
      aria-label={expanded ? 'Collapse menu' : 'Expand menu'}
      aria-expanded={expanded}
      aria-controls="slide-menu-actions"
      title={expanded ? 'Collapse menu' : 'Expand menu'}
      on:click={toggleMenu}
    >
      <Icon name="menu" />
      {#if expanded}
        <span class="menu-action-label">Collapse menu</span>
      {/if}
    </button>
  </div>

  <div id="slide-menu-actions" class="menu-section menu-section-actions">
    {#each menuItems as item}
      <IconButton
        icon={item.icon}
        label={item.label}
        title={item.title}
        className="slide-menu-button"
        onClick={(event) => dispatchAction(item.action, event)}
      >
        {#if expanded}
          <span class="menu-action-label">{item.text}</span>
        {/if}
      </IconButton>
    {/each}
  </div>

  <div class="menu-section menu-section-feedback">
    <a
      class="app-icon-button app-icon-button-default slide-menu-button slide-menu-feedback-link"
      href={FEEDBACK_URL}
      target="_blank"
      rel="noreferrer"
      aria-label="Feedback"
      title="Open feedback on GitHub"
    >
      <Icon name="help" />
      {#if expanded}
        <span class="menu-action-label">Feedback</span>
      {/if}
    </a>
  </div>
</nav>

<style>
  .slide-out-menu {
    background: linear-gradient(180deg, #111113 0%, #18181b 100%);
    border-right: 1px solid #27272a;
    bottom: var(--dashboard-footer-height, 42px);
    box-shadow: 10px 0 30px rgb(0 0 0 / 28%);
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    gap: 0.75rem;
    left: 0;
    overflow: hidden;
    padding: 0.75rem 0.5rem;
    position: fixed;
    top: 0;
    transition: width 160ms ease, box-shadow 160ms ease;
    width: var(--dashboard-menu-width, 58px);
    z-index: 9;
  }

  .slide-out-menu[data-expanded='true'] {
    box-shadow: 18px 0 45px rgb(0 0 0 / 55%);
    width: 248px;
  }

  .menu-section {
    display: grid;
    gap: 0.5rem;
    min-width: 0;
  }

  .menu-section-actions {
    align-content: start;
    overflow: hidden auto;
    scrollbar-width: thin;
  }

  .menu-section-feedback {
    align-content: end;
    border-top: 1px solid rgb(244 244 245 / 10%);
    padding-top: 0.5rem;
  }

  .slide-out-menu :global(.slide-menu-button) {
    background: transparent;
    border-color: transparent;
    box-shadow: none;
    justify-content: flex-start;
    overflow: hidden;
    padding-inline: 0.55rem;
    width: 100%;
  }

  .slide-out-menu :global(.slide-menu-button:hover),
  .slide-out-menu :global(.slide-menu-button:focus-visible) {
    background: rgb(244 244 245 / 10%);
    border-color: transparent;
  }

  .slide-out-menu :global(.slide-menu-button:active) {
    background: rgb(244 244 245 / 16%);
  }

  .slide-menu-feedback-link {
    text-decoration: none;
  }

  .slide-out-menu[data-expanded='false'] :global(.slide-menu-button) {
    justify-content: center;
    padding-inline: 0;
  }

  .menu-action-label {
    font-size: 0.9rem;
    font-weight: 600;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
