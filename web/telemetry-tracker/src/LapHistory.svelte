<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Icon from './Icon.svelte';
  import type { LapHistoryView, LapSummary, SessionSummary } from './types';

  export let laps: LapSummary[] = [];
  export let session: SessionSummary | null = null;
  export let selectedLapId: string | null = null;
  export let view: LapHistoryView = 'laps';
  export let deletingLapIds: string[] = [];

  const dispatch = createEventDispatcher<{
    selectlap: { lapId: string };
    deletelap: { lapId: string };
  }>();

  const ACTIVE_LAP_STATUSES = new Set(['active', 'recording', 'in_progress']);

  function newestFirst<T extends { started_at_ms: number; ended_at_ms: number | null }>(items: T[]): T[] {
    return [...items].sort((left, right) => {
      const leftTime = left.ended_at_ms ?? left.started_at_ms ?? 0;
      const rightTime = right.ended_at_ms ?? right.started_at_ms ?? 0;
      if (rightTime !== leftTime) return rightTime - leftTime;
      return (right.started_at_ms ?? 0) - (left.started_at_ms ?? 0);
    });
  }

  $: sortedLaps = newestFirst(laps);
  $: loadedSessionTitle = session?.label ?? sortedLaps[0]?.session_label ?? 'Loaded session';

  function formatTimestamp(value: number | null): string {
    if (value === null) return 'In progress';
    return new Date(value).toLocaleString();
  }

  function formatDurationMs(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
    const totalMs = Math.max(0, Math.round(value));
    const minutes = Math.floor(totalMs / 60_000);
    const seconds = Math.floor((totalMs % 60_000) / 1000);
    const milliseconds = totalMs % 1000;
    return `${minutes}:${String(seconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`;
  }

  function normalizedStatus(lap: LapSummary): string {
    return String(lap.status ?? '').trim().toLowerCase();
  }

  function formatLapTime(lap: LapSummary): string {
    if (lap.ended_at_ms === null || ACTIVE_LAP_STATUSES.has(normalizedStatus(lap))) return 'TBD';
    return formatDurationMs(lap.lap_time_ms);
  }

  function lapDisplayName(lap: LapSummary): string {
    return `${lap.session_label} lap ${lap.lap_number ?? '—'}`;
  }

  function lapTrackLabel(lap: LapSummary): string {
    if (lap.track_profile_name && lap.track_profile_layout) {
      return `${lap.track_profile_name} — ${lap.track_profile_layout}`;
    }
    return lap.track_profile_name ?? lap.track_profile_layout ?? 'Unknown track';
  }

  function isDeleting(lapId: string): boolean {
    return deletingLapIds.includes(lapId);
  }

  function requestDeleteLap(lap: LapSummary) {
    if (isDeleting(lap.id)) return;
    dispatch('deletelap', { lapId: lap.id });
  }

  function selectLap(lapId: string) {
    dispatch('selectlap', { lapId });
  }

  function sessionStatusLabel(summary: SessionSummary): string {
    return summary.status.replace(/_/g, ' ');
  }

  function completedLapCount(summary: SessionSummary): number {
    return summary.completed_lap_count ?? 0;
  }

  function totalLapCount(summary: SessionSummary): number {
    return summary.lap_count ?? 0;
  }
</script>

<section class="lap-history" aria-label={view === 'laps' ? 'Session laps' : 'Session aggregate'}>
  {#if view === 'laps'}
    <div class="history-header">
      <h2>{loadedSessionTitle}</h2>
    </div>

    {#if sortedLaps.length === 0}
      <p class="empty-state">No laps in the loaded session yet.</p>
    {:else}
      <ul>
        {#each sortedLaps as lap}
          <li class="history-row lap-row">
            <button
              type="button"
              class="lap-button"
              class:selected={selectedLapId === lap.id}
              aria-pressed={selectedLapId === lap.id}
              on:click={() => selectLap(lap.id)}
            >
              <div class="row-header">
                <strong>Lap {lap.lap_number ?? '—'}</strong>
                <span class="history-timestamp">{formatTimestamp(lap.ended_at_ms ?? lap.started_at_ms)}</span>
              </div>
              <div class="row-body">
                <span class="lap-time">{formatLapTime(lap)}</span>
                <span class="lap-track">{lapTrackLabel(lap)}</span>
              </div>
            </button>
            <button
              type="button"
              class="delete-lap-button"
              aria-label={`Delete ${lapDisplayName(lap)}`}
              title={`Delete ${lapDisplayName(lap)}`}
              disabled={isDeleting(lap.id)}
              aria-busy={isDeleting(lap.id)}
              on:click={() => requestDeleteLap(lap)}
            >
              <Icon name="delete" size={18} />
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {:else}
    <div class="history-header">
      <h2>Session summary</h2>
    </div>

    {#if !session}
      <p class="empty-state">No loaded session to summarize.</p>
    {:else}
      <article class="session-summary-card" role="region" aria-label={`${session.label} lap aggregate summary`}>
        <div class="row-header session-summary-title">
          <div>
            <strong>{session.label}</strong>
          </div>
          <span class="session-status-badge">{sessionStatusLabel(session)}</span>
        </div>

        <div class="session-aggregate-grid">
          <div>
            <span class="aggregate-label">Laps</span>
            <strong>{completedLapCount(session)}/{totalLapCount(session)}</strong>
          </div>
          <div>
            <span class="aggregate-label">Best</span>
            <strong>{formatDurationMs(session.best_lap_time_ms)}</strong>
          </div>
          <div>
            <span class="aggregate-label">Average</span>
            <strong>{formatDurationMs(session.average_lap_time_ms)}</strong>
          </div>
          <div>
            <span class="aggregate-label">Total</span>
            <strong>{formatDurationMs(session.total_lap_time_ms)}</strong>
          </div>
        </div>

        {#if completedLapCount(session) === 0}
          <p class="empty-state">No completed laps in this session yet.</p>
        {/if}

        <dl class="session-summary-meta">
          <div>
            <dt>Created</dt>
            <dd>{formatTimestamp(session.started_at_ms)}</dd>
          </div>
          <div>
            <dt>Last active</dt>
            <dd>{formatTimestamp(session.last_active_at_ms)}</dd>
          </div>
        </dl>
      </article>
    {/if}
  {/if}
</section>

<style>
  .lap-history {
    border: 1px solid #27272a;
    border-radius: 1rem;
    display: grid;
    gap: 0.9rem;
    padding: 1rem;
  }

  .history-header {
    align-items: center;
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  h2 {
    margin: 0;
  }

  ul {
    display: grid;
    gap: 0.65rem;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .history-row,
  .session-summary-card {
    background: #1f1f23;
    border: 1px solid #27272a;
    border-radius: 0.9rem;
    padding: 0;
  }

  .lap-row {
    align-items: stretch;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .lap-button {
    background: transparent;
    border: 0;
    border-radius: 0.9rem 0 0 0.9rem;
    color: inherit;
    display: grid;
    padding: 0.8rem;
    text-align: left;
    width: 100%;
  }

  .lap-button:hover,
  .lap-button:focus-visible {
    background: #27272a;
  }

  .lap-button.selected,
  .lap-button[aria-pressed='true'] {
    box-shadow: inset 0 0 0 1px #a1a1aa;
  }

  .delete-lap-button {
    align-self: stretch;
    background: transparent;
    border: 0;
    border-left: 1px solid #27272a;
    border-radius: 0 0.9rem 0.9rem 0;
    color: #f87171;
    cursor: pointer;
    display: grid;
    font-size: 0.78rem;
    font-weight: 700;
    line-height: 0;
    min-width: 2.65rem;
    padding: 0 0.7rem;
    place-items: center;
  }

  .delete-lap-button:hover,
  .delete-lap-button:focus-visible {
    background: rgb(127 29 29 / 45%);
    color: #fecaca;
  }

  .delete-lap-button:disabled {
    color: #71717a;
    cursor: not-allowed;
  }

  .row-header,
  .row-body {
    align-items: center;
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .row-body {
    color: #a1a1aa;
    margin-top: 0.4rem;
    justify-content: flex-start;
  }

  .history-timestamp,
  .lap-time,
  .lap-track {
    color: #d4d4d8;
    font-size: 0.82rem;
    white-space: nowrap;
  }

  .lap-time {
    font-variant-numeric: tabular-nums;
    font-size: 1.08rem;
    font-weight: 700;
  }

  .lap-track {
    color: #a1a1aa;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .session-summary-card {
    display: grid;
    gap: 0.8rem;
    padding: 0.8rem;
  }

  .session-summary-title {
    align-items: start;
  }


  .session-status-badge {
    background: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    color: #e4e4e7;
    font-size: 0.72rem;
    font-weight: 800;
    padding: 0.2rem 0.55rem;
    text-transform: lowercase;
  }

  .session-aggregate-grid {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .session-aggregate-grid div {
    background: #18181b;
    border: 1px solid #27272a;
    border-radius: 0.65rem;
    display: grid;
    gap: 0.2rem;
    padding: 0.55rem 0.6rem;
  }

  .session-aggregate-grid strong {
    color: #f4f4f5;
    font-size: 0.92rem;
    font-variant-numeric: tabular-nums;
  }

  .aggregate-label,
  .session-summary-meta dt {
    color: #a1a1aa;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .session-summary-meta {
    display: grid;
    gap: 0.4rem;
    margin: 0;
  }

  .session-summary-meta div {
    align-items: center;
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .session-summary-meta dd {
    color: #d4d4d8;
    font-size: 0.82rem;
    margin: 0;
    text-align: right;
  }

  .empty-state {
    color: #a1a1aa;
    margin: 0;
  }
</style>
