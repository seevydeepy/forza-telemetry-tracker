<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
  import AppModal from './AppModal.svelte';
  import IconButton from './IconButton.svelte';
  import type { DiagnosticsPayload } from './types';

  export let payload: DiagnosticsPayload | null = null;
  export let loading = false;
  export let restarting = false;
  export let deletingTelemetry = false;

  type AnyRecord = Record<string, unknown>;

  const dispatch = createEventDispatcher<{
    close: void;
    refresh: void;
    restart: void;
    deleteAllTelemetry: void;
  }>();

  let listenerStatus: AnyRecord | null = null;
  let captureStatus: AnyRecord | null = null;
  let captureRecording: AnyRecord | null = null;
  let capturePacketReceipt: AnyRecord | null = null;
  let deleteConfirmOpen = false;
  let deleteConfirmDialog: HTMLDivElement | null = null;
  let deleteConfirmCancelButton: HTMLButtonElement | null = null;

  $: listenerStatus = asRecord(payload?.listener_status);
  $: captureStatus = asRecord(payload?.capture_status);
  $: captureRecording = nestedRecord(captureStatus, 'recording');
  $: capturePacketReceipt = nestedRecord(captureStatus, 'packet_receipt');

  function asRecord(value: unknown): AnyRecord | null {
    return value && typeof value === 'object' ? (value as AnyRecord) : null;
  }

  function nestedRecord(record: AnyRecord | null, key: string): AnyRecord | null {
    return asRecord(record?.[key]);
  }

  function displayValue(record: AnyRecord | null, key: string): string {
    const value = record?.[key];
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'boolean') return value ? 'yes' : 'no';
    return String(value);
  }

  function formatBytes(value: number | null | undefined): string {
    const bytes = Number(value ?? 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 bytes';
    if (bytes === 1) return '1 byte';
    if (bytes < 1024) return `${bytes} bytes`;

    const units = ['KiB', 'MiB', 'GiB', 'TiB'];
    let amount = bytes / 1024;
    let unitIndex = 0;
    while (amount >= 1024 && unitIndex < units.length - 1) {
      amount /= 1024;
      unitIndex += 1;
    }
    return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unitIndex]} (${bytes.toLocaleString()} bytes)`;
  }

  function formatCount(value: number | undefined): string {
    return Number(value ?? 0).toLocaleString();
  }

  function errorText(error: unknown): string {
    if (typeof error === 'string') return error;
    try {
      return JSON.stringify(error);
    } catch {
      return String(error);
    }
  }

  function openDeleteConfirm() {
    if (loading || deletingTelemetry) return;
    deleteConfirmOpen = true;
    void tick().then(() => deleteConfirmCancelButton?.focus({ preventScroll: true }));
  }

  function closeDeleteConfirm() {
    if (deletingTelemetry) return;
    deleteConfirmOpen = false;
  }

  function handleDeleteConfirmBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      closeDeleteConfirm();
    }
  }

  function confirmDeleteAllTelemetry() {
    if (deletingTelemetry) return;
    deleteConfirmOpen = false;
    dispatch('deleteAllTelemetry');
  }

  function handleModalClose() {
    if (deleteConfirmOpen) {
      closeDeleteConfirm();
      return;
    }
    dispatch('close');
  }
</script>

<AppModal title="Diagnostics" ariaLabel="Telemetry diagnostics" closeLabel="Close diagnostics" on:close={handleModalClose}>
  <div class="diagnostics-panel">
    <div class="diagnostics-toolbar">
      <p class="eyebrow">Forza Telemetry Tracker</p>
      <IconButton icon="refresh" label="Refresh diagnostics" title="Refresh diagnostics" disabled={loading} onClick={() => dispatch('refresh')} />
    </div>

    {#if loading}
      <p class="diagnostics-loading">Loading diagnostics…</p>
    {/if}

    {#if payload}
      <section class="diagnostics-section" aria-label="Application diagnostics">
        <dl class="diagnostics-grid">
          <div>
            <dt>App version</dt>
            <dd>{payload.app_version}</dd>
          </div>
          <div>
            <dt>Database path</dt>
            <dd class="path-value">{payload.database_path}</dd>
          </div>
          <div>
            <dt>Database size</dt>
            <dd>{formatBytes(payload.database_size_bytes)}</dd>
          </div>
          <div>
            <dt>WAL size</dt>
            <dd>{formatBytes(payload.wal_size_bytes)}</dd>
          </div>
        </dl>
      </section>

      <section class="diagnostics-section" aria-label="Diagnostics row counts">
        <div class="section-heading-row">
          <h3>Row counts</h3>
          <button
            type="button"
            class="text-button danger-button"
            disabled={loading || deletingTelemetry}
            on:click={openDeleteConfirm}
          >
            {deletingTelemetry ? 'Deleting…' : 'Delete All Telemetry'}
          </button>
        </div>
        <ul class="metric-list">
          <li><span>Sessions</span><strong>{formatCount(payload.row_counts.sessions)}</strong></li>
          <li><span>Laps</span><strong>{formatCount(payload.row_counts.laps)}</strong></li>
          <li><span>Packets</span><strong>{formatCount(payload.row_counts.packets)}</strong></li>
          <li><span>Issue markers</span><strong>{formatCount(payload.row_counts.issue_markers)}</strong></li>
          <li><span>Track profiles</span><strong>{formatCount(payload.row_counts.track_profiles)}</strong></li>
        </ul>
      </section>

      <section class="diagnostics-section" aria-label="Listener diagnostics">
        <div class="section-heading-row">
          <h3>Listener</h3>
          <button
            type="button"
            class="text-button"
            disabled={loading || restarting}
            on:click={() => dispatch('restart')}
          >
            {restarting ? 'Restarting…' : 'Restart Listener'}
          </button>
        </div>
        <ul class="metric-list">
          <li><span>State</span><strong>{displayValue(listenerStatus, 'state')}</strong></li>
          <li><span>Message</span><strong>{displayValue(listenerStatus, 'message')}</strong></li>
          <li><span>UDP host</span><strong>{displayValue(listenerStatus, 'udp_host')}</strong></li>
          <li><span>UDP port</span><strong>{displayValue(listenerStatus, 'udp_port')}</strong></li>
          <li><span>Packets received</span><strong>{displayValue(listenerStatus, 'packets_received')}</strong></li>
          <li><span>Packets recorded</span><strong>{displayValue(listenerStatus, 'packets_recorded')}</strong></li>
        </ul>
      </section>

      <section class="diagnostics-section" aria-label="Capture diagnostics">
        <h3>Capture</h3>
        <ul class="metric-list">
          <li><span>Mode</span><strong>{displayValue(captureStatus, 'mode')}</strong></li>
          <li><span>Phase</span><strong>{displayValue(captureStatus, 'phase')}</strong></li>
          <li><span>Recording active</span><strong>{displayValue(captureRecording, 'active')}</strong></li>
          <li><span>Packet receipt</span><strong>{displayValue(capturePacketReceipt, 'state')}</strong></li>
          <li><span>Packets observed</span><strong>{displayValue(capturePacketReceipt, 'packets_observed')}</strong></li>
        </ul>
      </section>

      <section class="diagnostics-section" aria-label="Recent errors">
        <h3>Recent errors</h3>
        {#if payload.recent_errors.length > 0}
          <ul class="error-list">
            {#each payload.recent_errors as error}
              <li>{errorText(error)}</li>
            {/each}
          </ul>
        {:else}
          <p class="empty-state">No recent errors.</p>
        {/if}
      </section>
    {:else if !loading}
      <p class="empty-state">Diagnostics unavailable.</p>
    {/if}

    {#if deleteConfirmOpen}
      <section
        class="diagnostics-confirm-backdrop"
        role="presentation"
        on:click={handleDeleteConfirmBackdropClick}
      >
        <div
          bind:this={deleteConfirmDialog}
          class="diagnostics-confirm-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-all-telemetry-title"
          tabindex="-1"
        >
          <h3 id="delete-all-telemetry-title">Delete all telemetry?</h3>
          <p>
            This will permanently erase all recorded telemetry captured by this system,
            including sessions, laps, packets, issue markers, lap summaries, and recorded stats.
          </p>
          <p><strong>This cannot be undone.</strong></p>
          <div class="confirm-actions">
            <button
              bind:this={deleteConfirmCancelButton}
              type="button"
              class="secondary-button"
              on:click={closeDeleteConfirm}
            >
              Cancel
            </button>
            <button type="button" class="danger-confirm-button" on:click={confirmDeleteAllTelemetry}>
              Delete All Telemetry
            </button>
          </div>
        </div>
      </section>
    {/if}
  </div>
</AppModal>

<style>
  .diagnostics-panel {
    display: grid;
    gap: 1rem;
  }

  .diagnostics-toolbar {
    align-items: center;
    display: flex;
    gap: 1rem;
    justify-content: space-between;
  }

  .eyebrow {
    color: #a1a1aa;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    margin: 0 0 0.2rem;
    text-transform: uppercase;
  }

  .diagnostics-loading {
    color: #e4e4e7;
    margin: 0;
  }

  .diagnostics-section {
    background: var(--canvas-overlay-control-bg);
    border: 1px solid #27272a;
    border-radius: 0.85rem;
    padding: 0.85rem;
  }

  .diagnostics-section h3 {
    color: #e4e4e7;
    font-size: 1rem;
    margin: 0 0 0.75rem;
  }

  .section-heading-row {
    align-items: start;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
    margin: 0 0 0.75rem;
  }

  .section-heading-row h3 {
    margin: 0;
  }

  .text-button {
    background: #0c4a6e;
    border: 1px solid #0369a1;
    border-radius: 0.65rem;
    color: #e0f2fe;
    font: inherit;
    font-size: 0.85rem;
    font-weight: 700;
    padding: 0.45rem 0.7rem;
    white-space: nowrap;
  }

  .danger-button {
    background: #7f1d1d;
    border-color: #dc2626;
    color: #fee2e2;
  }

  .text-button:disabled {
    cursor: wait;
    opacity: 0.6;
  }

  .diagnostics-confirm-backdrop {
    align-items: center;
    background: rgb(9 9 11 / 72%);
    border-radius: 1rem;
    display: flex;
    inset: 0;
    justify-content: center;
    padding: 1rem;
    position: fixed;
    z-index: 9;
  }

  .diagnostics-confirm-dialog {
    background: #18181b;
    border: 1px solid #7f1d1d;
    border-radius: 1rem;
    box-shadow: 0 20px 60px rgb(0 0 0 / 55%);
    color: #f4f4f5;
    display: grid;
    gap: 0.85rem;
    max-width: 420px;
    padding: 1rem;
  }

  .diagnostics-confirm-dialog h3,
  .diagnostics-confirm-dialog p {
    margin: 0;
  }

  .diagnostics-confirm-dialog p {
    color: #d4d4d8;
    line-height: 1.45;
  }

  .confirm-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    justify-content: flex-end;
  }

  .secondary-button,
  .danger-confirm-button {
    border-radius: 0.75rem;
    cursor: pointer;
    font: inherit;
    font-weight: 700;
    padding: 0.55rem 0.85rem;
  }

  .secondary-button {
    background: #27272a;
    border: 1px solid #3f3f46;
    color: #f4f4f5;
  }

  .danger-confirm-button {
    background: #991b1b;
    border: 1px solid #ef4444;
    color: #fee2e2;
  }

  .diagnostics-grid,
  .metric-list {
    display: grid;
    gap: 0.65rem;
    margin: 0;
  }

  .diagnostics-grid div,
  .metric-list li {
    align-items: baseline;
    display: grid;
    gap: 0.75rem;
    grid-template-columns: 140px 1fr;
  }

  .diagnostics-grid dt,
  .metric-list span {
    color: #a1a1aa;
  }

  .diagnostics-grid dd {
    margin: 0;
  }

  .metric-list {
    list-style: none;
    padding: 0;
  }

  .metric-list strong {
    color: #e0f2fe;
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .path-value {
    overflow-wrap: anywhere;
  }

  .error-list {
    margin: 0;
    padding-left: 1.25rem;
  }

  .empty-state {
    color: #a1a1aa;
    margin: 0;
  }
</style>
