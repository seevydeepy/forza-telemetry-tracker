<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import AppModal from './AppModal.svelte';
  import { canChooseExportFolder, chooseExportFolder } from './desktopBridge';
  import type { TelemetryExportDefaults, TelemetryExportJob, TelemetryExportKind } from './types';

  export let defaults: TelemetryExportDefaults | null = null;
  export let jobs: TelemetryExportJob[] = [];
  export let defaultsLoading = false;
  export let jobsLoading = false;
  export let exporting = false;
  export let cancellingJobIds: string[] = [];

  const dispatch = createEventDispatcher<{
    close: void;
    export: { kind: TelemetryExportKind; output_dir: string; filename_prefix: string };
    refreshjobs: void;
    canceljob: { jobId: string };
  }>();

  const outputDirInputId = `telemetry-export-output-dir-${Math.random().toString(36).slice(2)}`;
  const filenamePrefixInputId = `telemetry-export-filename-prefix-${Math.random().toString(36).slice(2)}`;

  let outputDir = '';
  let filenamePrefix = '';
  let appliedDefaultsKey = '';
  let previousDefaultOutputDir = '';
  let previousDefaultFilenamePrefix = '';
  let nativeFolderPickerAvailable = false;
  let choosingNativeFolder = false;
  let nativeFolderPickerError = '';

  $: defaultsKey = defaults ? `${defaults.output_dir}\u0000${defaults.filename_prefix}` : '';
  $: exportDisabled = exporting || defaultsLoading || !outputDir.trim();
  $: if (defaults && defaultsKey !== appliedDefaultsKey) {
    const isFirstDefaultsLoad = !appliedDefaultsKey;
    if (isFirstDefaultsLoad || outputDir === previousDefaultOutputDir) {
      outputDir = defaults.output_dir;
    }
    if (isFirstDefaultsLoad || filenamePrefix === previousDefaultFilenamePrefix) {
      filenamePrefix = defaults.filename_prefix;
    }
    previousDefaultOutputDir = defaults.output_dir;
    previousDefaultFilenamePrefix = defaults.filename_prefix;
    appliedDefaultsKey = defaultsKey;
  }

  onMount(() => {
    refreshNativeFolderPickerAvailability();
    window.addEventListener('pywebviewready', refreshNativeFolderPickerAvailability);
    return () => window.removeEventListener('pywebviewready', refreshNativeFolderPickerAvailability);
  });

  function useDefaultExportsFolder() {
    if (!defaults) return;
    outputDir = defaults.output_dir;
  }

  function refreshNativeFolderPickerAvailability() {
    nativeFolderPickerAvailable = canChooseExportFolder();
  }

  async function browseForOutputFolder() {
    if (!nativeFolderPickerAvailable || defaultsLoading || exporting || choosingNativeFolder) return;
    nativeFolderPickerError = '';
    choosingNativeFolder = true;
    try {
      const selected = await chooseExportFolder(outputDir);
      if (selected) {
        outputDir = selected;
      }
    } catch {
      nativeFolderPickerError = 'Unable to open the export folder picker.';
    } finally {
      choosingNativeFolder = false;
    }
  }

  function startExport(kind: TelemetryExportKind) {
    const trimmedOutputDir = outputDir.trim();
    if (exporting || defaultsLoading || !trimmedOutputDir) return;
    dispatch('export', {
      kind,
      output_dir: trimmedOutputDir,
      filename_prefix: filenamePrefix.trim()
    });
  }

  function cancelJob(job: TelemetryExportJob) {
    if (!job.can_cancel || cancellingJobIds.includes(job.id)) return;
    dispatch('canceljob', { jobId: job.id });
  }

  function formatCount(value: number, noun: string): string {
    const normalized = Number.isFinite(value) ? value : 0;
    return `${normalized.toLocaleString()} ${noun}${normalized === 1 ? '' : 's'}`;
  }

  function formatBytes(value: number): string {
    const normalized = Number.isFinite(value) ? value : 0;
    return `${normalized.toLocaleString()} bytes`;
  }

  function formatDuration(value: number | null): string {
    if (value === null || !Number.isFinite(value)) return '—';
    if (value < 1000) return `${Math.max(0, Math.round(value))}ms`;
    return `${(value / 1000).toFixed(1)}s`;
  }

  function formatDateTime(value: number | null): string {
    if (value === null || !Number.isFinite(value)) return '—';
    return new Date(value).toLocaleString();
  }

  function statusTone(job: TelemetryExportJob): 'active' | 'completed' | 'failed' {
    if (job.status === 'completed') return 'completed';
    if (job.status === 'failed' || job.status === 'cancelled') return 'failed';
    return 'active';
  }

  function jobStatusLabel(job: TelemetryExportJob): string {
    switch (job.status) {
      case 'queued':
        return 'Queued';
      case 'running':
        return 'Running';
      case 'cancelling':
        return 'Cancelling';
      case 'completed':
        return 'Completed';
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return job.status;
    }
  }

  function exportKindLabel(kind: TelemetryExportKind): string {
    switch (kind) {
      case 'raw_binary':
        return 'Raw binary package';
      case 'raw_csv':
        return 'Raw CSV';
      case 'curated_csv':
        return 'Curated CSV';
      default:
        return kind;
    }
  }
</script>

<AppModal title="Export telemetry" on:close={() => dispatch('close')}>
  <section class="export-telemetry" aria-label="Telemetry export settings">
    <p>
      Exports dump the full telemetry database. They do not filter by session, lap, time range, timeline selection, or
      current review view.
    </p>
    <p class="settings-hint">
      Choose an output folder and file name prefix, then start a background export. You can close this window and return
      later to refresh job status or cancel queued/running exports.
    </p>

    <form class="export-telemetry-form" on:submit|preventDefault>
      <div class="form-field">
        <label for={outputDirInputId}>Output folder</label>
        <input
          id={outputDirInputId}
          aria-label="Output folder"
          type="text"
          bind:value={outputDir}
          placeholder={defaultsLoading ? 'Loading default exports folder…' : 'Choose an exports folder'}
          disabled={defaultsLoading || exporting}
        />
      </div>

      <div class="modal-actions">
        {#if nativeFolderPickerAvailable}
          <button type="button" class="secondary-action" disabled={defaultsLoading || exporting || choosingNativeFolder} on:click={browseForOutputFolder}>
            {choosingNativeFolder ? 'Browsing…' : 'Browse'}
          </button>
        {/if}
        <button type="button" class="secondary-action" disabled={!defaults || defaultsLoading || exporting} on:click={useDefaultExportsFolder}>
          Use default exports folder
        </button>
      </div>
      {#if nativeFolderPickerError}
        <p class="settings-hint export-picker-error" role="alert">{nativeFolderPickerError}</p>
      {/if}

      <div class="form-field">
        <label for={filenamePrefixInputId}>File name prefix</label>
        <input
          id={filenamePrefixInputId}
          aria-label="File name prefix"
          type="text"
          bind:value={filenamePrefix}
          placeholder="telemetry-export"
          disabled={defaultsLoading || exporting}
        />
      </div>

      {#if defaults?.estimate}
        <p class="settings-hint export-estimate">
          Estimate: {formatCount(defaults.estimate.raw_packet_count, 'raw packet')} • {formatCount(defaults.estimate.curated_sample_count, 'curated sample')}
          • {formatCount(defaults.estimate.session_count, 'session')} • {formatBytes(defaults.estimate.raw_byte_count)} raw.
        </p>
      {:else if defaultsLoading}
        <p class="settings-hint export-estimate">Loading export estimate…</p>
      {:else}
        <p class="settings-hint export-estimate">Export estimate unavailable.</p>
      {/if}

      <div class="modal-actions export-actions">
        <button type="button" class="primary-action" disabled={exportDisabled} on:click={() => startExport('raw_binary')}>
          Export raw binary package
        </button>
        <button type="button" class="primary-action" disabled={exportDisabled} on:click={() => startExport('raw_csv')}>
          Export raw CSV
        </button>
        <button type="button" class="primary-action" disabled={exportDisabled} on:click={() => startExport('curated_csv')}>
          Export curated CSV
        </button>
      </div>
    </form>
  </section>

  <section class="export-jobs" aria-label="Telemetry export jobs">
    <header class="export-jobs-header">
      <div>
        <h3>Export jobs</h3>
        <p class="settings-hint">Jobs stay here until the tracker closes.</p>
      </div>
      <button type="button" class="secondary-action" disabled={jobsLoading} on:click={() => dispatch('refreshjobs')}>
        {jobsLoading ? 'Refreshing…' : 'Refresh'}
      </button>
    </header>

    {#if jobs.length === 0}
      <p class="settings-hint">No export jobs are currently queued, running, or completed.</p>
    {:else}
      <div class="export-job-list">
        {#each jobs as job (job.id)}
          <article class="export-job-card" data-status={job.status} data-status-tone={statusTone(job)}>
            <div class="export-job-heading">
              <div>
                <strong>{job.label || exportKindLabel(job.kind)}</strong>
                <p class="settings-hint">{formatCount(job.row_count, 'row')} • {formatBytes(job.total_size_bytes)}</p>
              </div>
              <span class="export-job-status">{jobStatusLabel(job)}</span>
            </div>

            <p class="settings-hint export-job-status-text">{job.status_text}</p>
            <dl class="export-job-details">
              <div>
                <dt>Output folder</dt>
                <dd>{job.output_dir}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{formatDateTime(job.started_at_ms)}</dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>{formatDuration(job.duration_ms)}</dd>
              </div>
              <div>
                <dt>File size</dt>
                <dd>{formatBytes(job.total_size_bytes)}</dd>
              </div>
              <div>
                <dt>Rows</dt>
                <dd>{formatCount(job.row_count, 'row')}</dd>
              </div>
            </dl>

            {#if job.output_files.length > 0}
              <ul class="export-output-files" aria-label={`${job.label || exportKindLabel(job.kind)} output files`}>
                {#each job.output_files as file}
                  <li>
                    <strong>{file.filename}</strong>
                    <span>{formatBytes(file.size_bytes)}</span>
                    <span>{file.path}</span>
                  </li>
                {/each}
              </ul>
            {/if}

            {#if job.error}
              <p class="settings-hint export-job-error">Error: {job.error}</p>
            {/if}

            {#if job.can_cancel}
              <div class="modal-actions">
                <button
                  type="button"
                  class="secondary-action danger-action"
                  disabled={cancellingJobIds.includes(job.id)}
                  on:click={() => cancelJob(job)}
                >
                  {cancellingJobIds.includes(job.id) ? 'Cancelling…' : 'Cancel job'}
                </button>
              </div>
            {/if}
          </article>
        {/each}
      </div>
    {/if}
  </section>
</AppModal>

<style>
  .export-telemetry-form,
  .export-job-list,
  .export-job-card,
  .export-job-details,
  .export-output-files {
    display: grid;
    gap: 0.75rem;
  }

  .export-actions {
    flex-wrap: wrap;
  }

  .export-jobs {
    border-top: 1px solid var(--panel-border-muted);
    display: grid;
    gap: 0.85rem;
    margin-top: 1rem;
    padding-top: 1rem;
  }

  .export-jobs-header,
  .export-job-heading {
    align-items: start;
    display: flex;
    gap: 1rem;
    justify-content: space-between;
  }

  .export-jobs-header h3,
  .export-jobs-header p,
  .export-job-heading p,
  .export-job-status-text {
    margin: 0;
  }

  .export-job-card {
    background: var(--canvas-overlay-control-bg);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.9rem;
    padding: 0.85rem;
  }

  .export-job-card[data-status-tone='active'] {
    border-color: rgb(59 130 246 / 55%);
  }

  .export-job-card[data-status-tone='completed'] {
    border-color: rgb(34 197 94 / 55%);
  }

  .export-job-card[data-status-tone='failed'] {
    border-color: rgb(239 68 68 / 55%);
  }

  .export-job-status {
    background: #18181b;
    border: 1px solid var(--panel-border-muted);
    border-radius: 999px;
    color: #e2e8f0;
    font-size: 0.78rem;
    padding: 0.2rem 0.55rem;
    white-space: nowrap;
  }

  .export-job-details {
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    margin: 0;
  }

  .export-job-details div {
    background: rgb(15 23 42 / 35%);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.65rem;
    padding: 0.55rem;
  }

  .export-job-details dt {
    color: #a1a1aa;
    font-size: 0.75rem;
    margin-bottom: 0.2rem;
  }

  .export-job-details dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .export-output-files {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .export-output-files li {
    background: rgb(15 23 42 / 35%);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.65rem;
    display: grid;
    gap: 0.25rem;
    padding: 0.55rem;
  }

  .export-output-files span {
    overflow-wrap: anywhere;
  }

  .export-job-error {
    color: #fecaca;
  }
</style>
