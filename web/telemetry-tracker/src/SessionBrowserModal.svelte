<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
  import AppModal from './AppModal.svelte';
  import Icon from './Icon.svelte';
  import type { SessionFilters, SessionPageResponse, SessionSummary } from './types';

  export let page: SessionPageResponse = {
    sessions: [],
    page: 1,
    page_size: 100,
    total: 0,
    total_pages: 0
  };
  export let filters: SessionFilters = { page: 1, pageSize: 100 };
  export let busy = false;
  export let error: string | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
    filterchange: { filters: SessionFilters };
    pagechange: { page: number };
    open: { sessionId: string };
    rename: { sessionId: string; label: string };
    delete: { sessionId: string };
  }>();

  let nameFilter = filters.name ?? '';
  let createdFromFilter = dateInputValue(filters.createdFrom);
  let createdToFilter = dateInputValue(filters.createdTo);
  let lastActiveFromFilter = dateInputValue(filters.lastActiveFrom);
  let lastActiveToFilter = dateInputValue(filters.lastActiveTo);
  let lapCountMinFilter = filters.lapCountMin === undefined ? '' : String(filters.lapCountMin);
  let lapCountMaxFilter = filters.lapCountMax === undefined ? '' : String(filters.lapCountMax);
  let trackFilter = filters.track ?? '';
  let carFilter = filters.car ?? '';
  let filtersExpanded = false;
  let lapCountMinInput: HTMLInputElement | null = null;
  let renamingSessionId: string | null = null;
  let renameLabel = '';
  let deleteCandidate: SessionSummary | null = null;

  $: currentPage = page.total_pages === 0 ? 0 : page.page;
  $: hasPreviousPage = page.page > 1;
  $: hasNextPage = page.total_pages > 0 && page.page < page.total_pages;

  function dateInputValue(value?: number): string {
    if (value === undefined || value === null) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toISOString().slice(0, 10);
  }

  function startOfDayMs(value: string): number | undefined {
    if (!value) return undefined;
    const ms = new Date(`${value}T00:00:00`).getTime();
    return Number.isFinite(ms) ? ms : undefined;
  }

  function endOfDayMs(value: string): number | undefined {
    if (!value) return undefined;
    const ms = new Date(`${value}T23:59:59.999`).getTime();
    return Number.isFinite(ms) ? ms : undefined;
  }

  function optionalInteger(value: string | number): number | undefined {
    const text = String(value);
    if (!text.trim()) return undefined;
    const parsed = Number.parseInt(text, 10);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  function applyFilters() {
    dispatch('filterchange', {
      filters: {
        page: 1,
        pageSize: 100,
        name: nameFilter.trim() || undefined,
        createdFrom: startOfDayMs(createdFromFilter),
        createdTo: endOfDayMs(createdToFilter),
        lastActiveFrom: startOfDayMs(lastActiveFromFilter),
        lastActiveTo: endOfDayMs(lastActiveToFilter),
        lapCountMin: optionalInteger(lapCountMinFilter),
        lapCountMax: optionalInteger(lapCountMaxFilter),
        track: trackFilter.trim() || undefined,
        car: carFilter.trim() || undefined
      }
    });
  }

  async function toggleFilters() {
    const expanding = !filtersExpanded;
    filtersExpanded = expanding;
    if (expanding) {
      await tick();
      lapCountMinInput?.focus();
    }
  }

  function changePage(nextPage: number) {
    if (nextPage < 1 || nextPage === page.page || busy) return;
    dispatch('pagechange', { page: nextPage });
  }

  function formatTimestamp(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—';
    return new Date(value).toLocaleString();
  }

  function sessionSubtitle(session: SessionSummary): string {
    if (session.car_name) {
      const classText = [session.car_class_label, session.car_performance_index].filter(Boolean).join(' ');
      const driveText = session.drivetrain_label ?? '';
      return [session.car_name, classText, driveText].filter(Boolean).join(' · ');
    }
    return `${session.lap_count} ${session.lap_count === 1 ? 'lap' : 'laps'}`;
  }

  function startRename(session: SessionSummary) {
    renamingSessionId = session.id;
    renameLabel = session.label;
  }

  function saveRename() {
    if (!renamingSessionId) return;
    const label = renameLabel.trim();
    if (!label) return;
    dispatch('rename', { sessionId: renamingSessionId, label });
    renamingSessionId = null;
    renameLabel = '';
  }

  function cancelRename() {
    renamingSessionId = null;
    renameLabel = '';
  }

  function confirmDelete(session: SessionSummary) {
    deleteCandidate = session;
  }

  function deleteConfirmed() {
    if (!deleteCandidate) return;
    dispatch('delete', { sessionId: deleteCandidate.id });
    deleteCandidate = null;
  }
</script>

<AppModal title="Sessions" on:close={() => dispatch('close')}>
  <section class="session-browser" aria-label="Session browser content">
    <form class="session-filters" aria-label="Session filters" on:submit|preventDefault={applyFilters}>
      <div class="session-filters-header">
        <h3>Filters</h3>
      </div>

      <div class="filter-row filter-row-primary">
        <label>
          <span>Session Name</span>
          <input type="search" bind:value={nameFilter} />
        </label>
        <label>
          <span>Track</span>
          <input type="search" bind:value={trackFilter} />
        </label>
        <label>
          <span>Car</span>
          <input type="search" bind:value={carFilter} />
        </label>
      </div>

      {#if filtersExpanded}
        <div class="extra-filter-rows">
          <div class="filter-row filter-row-paired">
            <label>
              <span>Min. Laps</span>
              <input bind:this={lapCountMinInput} type="number" min="0" step="1" bind:value={lapCountMinFilter} />
            </label>
            <label>
              <span>Max. Laps</span>
              <input type="number" min="0" step="1" bind:value={lapCountMaxFilter} />
            </label>
          </div>
          <div class="filter-row filter-row-paired">
            <label>
              <span>Created From</span>
              <input type="date" bind:value={createdFromFilter} />
            </label>
            <label>
              <span>Created To</span>
              <input type="date" bind:value={createdToFilter} />
            </label>
          </div>
          <div class="filter-row filter-row-paired">
            <label>
              <span>Active From</span>
              <input type="date" bind:value={lastActiveFromFilter} />
            </label>
            <label>
              <span>Active To</span>
              <input type="date" bind:value={lastActiveToFilter} />
            </label>
          </div>
        </div>
      {/if}

      <div class="filter-actions">
        <button
          type="button"
          class="filter-toggle"
          aria-expanded={filtersExpanded}
          on:click={toggleFilters}
        >
          {filtersExpanded ? 'Hide extra filters' : 'Show more filters'}
        </button>
        <button type="submit" disabled={busy}>Apply session filters</button>
      </div>
    </form>

    <div class="session-browser-status">
      <p>Page {currentPage} of {page.total_pages} · {page.total} sessions</p>
      {#if busy}
        <p class="status-muted">Loading sessions…</p>
      {/if}
      {#if error}
        <p class="status-error">{error}</p>
      {/if}
    </div>

    {#if page.sessions.length === 0}
      <p class="empty-state">No sessions match these filters.</p>
    {:else}
      <div class="session-list" role="list" aria-label="Stored sessions">
        {#each page.sessions as session}
          <article class="session-row" role="listitem">
            <div class="session-row-main">
              <div>
                <h3>{session.label}</h3>
                <p>{sessionSubtitle(session)}</p>
              </div>
              <span class={`session-status session-status-${session.status}`}>{session.status}</span>
            </div>
            <dl class="session-meta">
              <div>
                <dt>Created</dt>
                <dd>{formatTimestamp(session.started_at_ms)}</dd>
              </div>
              <div>
                <dt>Last active</dt>
                <dd>{formatTimestamp(session.last_active_at_ms)}</dd>
              </div>
              <div>
                <dt>Laps</dt>
                <dd>{session.lap_count}</dd>
              </div>
            </dl>
            {#if renamingSessionId === session.id}
              <div class="rename-row">
                <label>
                  <span>Session name</span>
                  <input bind:value={renameLabel} />
                </label>
                <button type="button" on:click={saveRename} disabled={!renameLabel.trim()}>Save session name</button>
                <button type="button" on:click={cancelRename}>Cancel rename</button>
              </div>
            {/if}
            <div class="session-actions">
              <button
                type="button"
                class="icon-action"
                aria-label={`Open ${session.label}`}
                title={`Open ${session.label}`}
                on:click={() => dispatch('open', { sessionId: session.id })}
              >
                <Icon name="play" size={18} />
              </button>
              <button
                type="button"
                class="icon-action"
                aria-label={`Rename ${session.label}`}
                title={`Rename ${session.label}`}
                on:click={() => startRename(session)}
              >
                <Icon name="edit" size={18} />
              </button>
              <button
                type="button"
                class="icon-action danger"
                aria-label={`Delete ${session.label}`}
                title={`Delete ${session.label}`}
                on:click={() => confirmDelete(session)}
              >
                <Icon name="delete" size={18} />
              </button>
            </div>
          </article>
        {/each}
      </div>
    {/if}

    <nav class="session-pages" aria-label="Session pages">
      <button type="button" on:click={() => changePage(page.page - 1)} disabled={!hasPreviousPage || busy}>Previous page</button>
      <span>Showing {page.sessions.length} of {page.total}</span>
      <button type="button" on:click={() => changePage(page.page + 1)} disabled={!hasNextPage || busy}>Next page</button>
    </nav>
  </section>
</AppModal>

{#if deleteCandidate}
  <AppModal title="Delete session" on:close={() => (deleteCandidate = null)}>
    <section class="delete-confirmation">
      <p>Delete <strong>{deleteCandidate.label}</strong>? This removes the session and all laps stored in it.</p>
      <div class="confirm-actions">
        <button type="button" on:click={() => (deleteCandidate = null)}>Cancel delete</button>
        <button type="button" class="danger" on:click={deleteConfirmed}>Confirm delete session</button>
      </div>
    </section>
  </AppModal>
{/if}

<style>
  .session-browser {
    display: grid;
    gap: 1rem;
    min-width: 0;
    width: min(100%, 44rem);
  }

  .session-filters {
    background: #18181b;
    border: 1px solid #27272a;
    border-radius: 1rem;
    display: grid;
    gap: 0.8rem;
    padding: 1rem;
  }

  .session-filters-header,
  .filter-actions {
    align-items: center;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
  }

  .session-filters-header h3 {
    font-size: 1rem;
    margin: 0;
  }

  .filter-toggle {
    align-self: center;
  }

  .filter-row,
  .extra-filter-rows {
    display: grid;
    gap: 0.75rem;
    min-width: 0;
  }

  .filter-row-primary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .filter-row-paired {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .filter-actions {
    justify-content: flex-end;
  }

  label {
    color: #d4d4d8;
    display: grid;
    gap: 0.35rem;
    font-size: 0.85rem;
    font-weight: 700;
  }

  input {
    background: #09090b;
    border: 1px solid #3f3f46;
    border-radius: 0.65rem;
    color: #f4f4f5;
    min-width: 0;
    padding: 0.55rem 0.65rem;
  }

  button {
    align-self: end;
    background: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 0.75rem;
    color: #f4f4f5;
    cursor: pointer;
    font-weight: 700;
    padding: 0.6rem 0.8rem;
  }

  button:hover:not(:disabled),
  button:focus-visible:not(:disabled) {
    background: #3f3f46;
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .danger {
    border-color: #7f1d1d;
    color: #fecaca;
  }

  .session-browser-status,
  .session-pages,
  .confirm-actions {
    align-items: center;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
  }

  .session-browser-status p,
  .empty-state,
  .delete-confirmation p {
    margin: 0;
  }

  .status-muted,
  .empty-state {
    color: #a1a1aa;
  }

  .status-error {
    color: #fca5a5;
  }

  .session-list {
    display: grid;
    gap: 0.75rem;
    max-height: min(52vh, 620px);
    overflow: auto;
    padding-right: 0.25rem;
  }

  .session-row {
    background: #111113;
    border: 1px solid #27272a;
    border-radius: 1rem;
    display: grid;
    gap: 0.75rem;
    padding: 1rem;
  }

  .session-row-main,
  .session-actions,
  .rename-row {
    align-items: center;
    display: flex;
    gap: 0.65rem;
  }

  .session-row-main {
    justify-content: space-between;
  }

  h3,
  .session-row-main p,
  dl,
  dd {
    margin: 0;
  }

  h3 {
    font-size: 1rem;
  }

  .session-row-main p,
  dt {
    color: #a1a1aa;
    font-size: 0.8rem;
  }

  .session-status {
    border: 1px solid #3f3f46;
    border-radius: 999px;
    font-size: 0.75rem;
    padding: 0.2rem 0.55rem;
    text-transform: capitalize;
  }

  .session-status-active,
  .session-status-recording {
    border-color: #22c55e;
    color: #bbf7d0;
  }

  .session-meta {
    display: grid;
    gap: 0.65rem;
    grid-template-columns: 1fr 1fr auto;
  }

  .session-meta div {
    display: grid;
    gap: 0.2rem;
  }

  .rename-row label {
    flex: 1;
  }

  .session-actions {
    flex-wrap: wrap;
  }

  .icon-action {
    align-items: center;
    aspect-ratio: 1;
    display: inline-grid;
    justify-content: center;
    min-width: 2.4rem;
    padding: 0.55rem;
  }

  .delete-confirmation {
    display: grid;
    gap: 1rem;
    min-width: min(420px, 80vw);
  }

  .confirm-actions {
    justify-content: flex-end;
  }

  @media (max-width: 900px) {
    .session-browser {
      width: 100%;
    }

    .filter-row-primary,
    .filter-row-paired,
    .session-meta {
      grid-template-columns: 1fr;
    }

    .session-row-main,
    .rename-row,
    .session-pages {
      align-items: stretch;
      flex-direction: column;
    }
  }
</style>
