<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import LapHistory from './LapHistory.svelte';
  import type { LapHistoryView, LapSummary, SessionSummary } from './types';

  export let open = true;
  export let laps: LapSummary[] = [];
  export let session: SessionSummary | null = null;
  export let view: LapHistoryView = 'laps';
  export let selectedLapId: string | null = null;
  export let deletingLapIds: string[] = [];

  const EXPANDED_WIDTH = 400;

  const dispatch = createEventDispatcher<{
    close: void;
    deletelap: { lapId: string };
    open: void;
    selectlap: { lapId: string };
    viewchange: { view: LapHistoryView };
  }>();

  $: drawerVisible = open;

  function toggleDrawer() {
    if (drawerVisible) {
      dispatch('close');
    } else {
      dispatch('open');
    }
  }

  function setView(nextView: LapHistoryView) {
    if (nextView === view) return;
    dispatch('viewchange', { view: nextView });
  }
</script>

<div
  class="history-drawer-shell"
  class:closed={!drawerVisible}
  data-width={EXPANDED_WIDTH}
>
  <button
    type="button"
    class="history-drawer-toggle"
    aria-label={drawerVisible ? 'Hide history drawer' : 'Show history drawer'}
    aria-expanded={drawerVisible}
    title={drawerVisible ? 'Hide history drawer' : 'Show history drawer'}
    aria-controls="history-drawer-panel"
    on:click={toggleDrawer}
  >
    <span aria-hidden="true">{drawerVisible ? '›' : '‹'}</span>
  </button>
  <aside
    id="history-drawer-panel"
    class="history-drawer"
    class:closed={!drawerVisible}
    aria-label="Loaded session laps"
    aria-hidden={drawerVisible ? undefined : 'true'}
    inert={!drawerVisible}
    data-width={EXPANDED_WIDTH}
  >
    <header class="history-drawer-header">
      <div class="history-drawer-view-switcher" role="group" aria-label="History drawer view">
        <button type="button" aria-pressed={view === 'laps'} on:click={() => setView('laps')}>Laps</button>
        <button type="button" aria-pressed={view === 'session'} on:click={() => setView('session')}>Session</button>
      </div>
    </header>

    <div class="history-drawer-body">
      <LapHistory
        {laps}
        {session}
        {view}
        {selectedLapId}
        {deletingLapIds}
        on:selectlap={(event) => dispatch('selectlap', event.detail)}
        on:deletelap={(event) => dispatch('deletelap', event.detail)}
      />
    </div>
  </aside>
</div>
