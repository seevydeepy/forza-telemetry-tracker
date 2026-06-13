<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import AppModal from './AppModal.svelte';
  import type { RawTelemetryImportJob } from './types';

  export let importing = false;
  export let jobs: RawTelemetryImportJob[] = [];
  export let jobsLoading = false;
  export let cancellingJobIds: string[] = [];

  type ImportSourceType = 'file' | 'files' | 'folder';

  const dispatch = createEventDispatcher<{
    close: void;
    import: { files: File[]; label: string; sourceType: ImportSourceType };
    refreshjobs: void;
    canceljob: { jobId: string };
  }>();

  let selectedFiles: File[] = [];
  let selectedSourceType: ImportSourceType = 'file';
  let label = '';
  let fileInput: HTMLInputElement | null = null;
  let folderInput: HTMLInputElement | null = null;
  const fileInputId = `raw-telemetry-file-${Math.random().toString(36).slice(2)}`;
  const folderInputId = `raw-telemetry-folder-${Math.random().toString(36).slice(2)}`;
  const labelInputId = `raw-telemetry-label-${Math.random().toString(36).slice(2)}`;

  function defaultLabelForSelection(files: File[], sourceType: ImportSourceType): string {
    if (files.length === 0) return 'Imported raw telemetry';
    if (sourceType === 'folder') {
      const firstRelativePath = (files[0] as File & { webkitRelativePath?: string }).webkitRelativePath ?? '';
      const folderName = firstRelativePath.split('/')[0]?.trim();
      if (folderName) return folderName;
      return 'Imported raw telemetry folder';
    }
    if (files.length > 1) return `Imported ${files.length} raw telemetry files`;
    const name = files[0].name.trim();
    if (!name) return 'Imported raw telemetry';
    return name.replace(/\.[^.]+$/, '') || name;
  }

  function handleSelectionChange(event: Event, sourceType: ImportSourceType) {
    const input = event.currentTarget as HTMLInputElement;
    selectedFiles = Array.from(input.files ?? []);
    selectedSourceType = sourceType === 'file' && selectedFiles.length > 1 ? 'files' : sourceType;
    if (sourceType === 'folder' && fileInput) fileInput.value = '';
    if (sourceType !== 'folder' && folderInput) folderInput.value = '';
    if (selectedFiles.length > 0 && !label.trim()) {
      label = defaultLabelForSelection(selectedFiles, selectedSourceType);
    }
  }

  function submitImport() {
    if (selectedFiles.length === 0 || importing) return;
    dispatch('import', {
      files: selectedFiles,
      label: label.trim() || defaultLabelForSelection(selectedFiles, selectedSourceType),
      sourceType: selectedSourceType
    });
  }

  function progressPercent(job: RawTelemetryImportJob): string {
    const progress = Math.max(0, Math.min(1, Number(job.progress) || 0));
    return `${Math.round(progress * 100)}%`;
  }

  function jobStatusLabel(job: RawTelemetryImportJob): string {
    switch (job.status) {
      case 'queued':
        return 'Queued';
      case 'running':
        return 'Running';
      case 'cancelling':
        return 'Cancelling';
      case 'completed':
        return job.failed_files > 0 ? 'Completed with errors' : 'Completed';
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return job.status;
    }
  }

  function jobFileSummary(job: RawTelemetryImportJob): string {
    const fileNoun = job.total_files === 1 ? 'file' : 'files';
    const packetNoun = job.packet_count === 1 ? 'packet' : 'packets';
    return `${job.processed_files}/${job.total_files} ${fileNoun} • ${job.packet_count.toLocaleString()} ${packetNoun}`;
  }

  function selectedFilesSummary(): string {
    if (selectedFiles.length === 0) return '';
    const totalBytes = selectedFiles.reduce((total, file) => total + file.size, 0);
    const fileNoun = selectedFiles.length === 1 ? 'file' : 'files';
    return `Selected ${selectedFiles.length.toLocaleString()} ${fileNoun} (${totalBytes.toLocaleString()} bytes)`;
  }

  function cancelJob(job: RawTelemetryImportJob) {
    if (!job.can_cancel || cancellingJobIds.includes(job.id)) return;
    dispatch('canceljob', { jobId: job.id });
  }
</script>

<AppModal title="Import raw telemetry" on:close={() => dispatch('close')}>
  <section class="import-telemetry" aria-label="Raw telemetry import">
    <p>
      Choose a saved raw Forza UDP packet capture file, several files, or a whole folder of raw telemetry captures.
      The tracker imports them through the same session and lap pipeline used for live recordings.
    </p>
    <p class="settings-hint">
      Imports run as background jobs. You can close this window, keep using the tracker, then reopen it to check
      progress or cancel queued/running work. Empty files and partial packets are reported on the job instead of
      stopping the whole folder.
    </p>

    <form class="import-telemetry-form" on:submit|preventDefault={submitImport}>
      <div class="form-field">
        <label for={fileInputId}>Raw telemetry file or files</label>
        <input
          bind:this={fileInput}
          id={fileInputId}
          aria-label="Raw telemetry file or files"
          type="file"
          multiple
          accept=".bin,.raw,application/octet-stream"
          disabled={importing}
          on:change={(event) => handleSelectionChange(event, 'file')}
        />
      </div>

      <div class="form-field">
        <label for={folderInputId}>Raw telemetry folder</label>
        <input
          bind:this={folderInput}
          id={folderInputId}
          aria-label="Raw telemetry folder"
          type="file"
          multiple
          webkitdirectory
          disabled={importing}
          on:change={(event) => handleSelectionChange(event, 'folder')}
        />
        <p class="settings-hint">Folder selection imports every selected file; invalid raw telemetry files are listed as job errors.</p>
      </div>

      {#if selectedFiles.length > 0}
        <p class="settings-hint">{selectedFilesSummary()}</p>
      {/if}

      <div class="form-field">
        <label for={labelInputId}>Import label</label>
        <input
          id={labelInputId}
          aria-label="Import label"
          type="text"
          bind:value={label}
          placeholder="Imported raw telemetry"
          disabled={importing}
        />
      </div>

      <div class="modal-actions">
        <button type="submit" class="primary-action" disabled={selectedFiles.length === 0 || importing}>
          {importing ? 'Starting import…' : 'Start background import'}
        </button>
      </div>
    </form>
  </section>

  <section class="import-jobs" aria-label="Raw telemetry import jobs">
    <header class="import-jobs-header">
      <div>
        <h3>Import jobs</h3>
        <p class="settings-hint">Jobs stay here until the tracker closes.</p>
      </div>
      <button type="button" class="secondary-action" disabled={jobsLoading} on:click={() => dispatch('refreshjobs')}>
        {jobsLoading ? 'Refreshing…' : 'Refresh'}
      </button>
    </header>

    {#if jobs.length === 0}
      <p class="settings-hint">No import jobs are currently queued, running, or completed.</p>
    {:else}
      <div class="import-job-list">
        {#each jobs as job (job.id)}
          <article class="import-job-card" data-status={job.status}>
            <div class="import-job-heading">
              <div>
                <strong>{job.label}</strong>
                <p class="settings-hint">{jobFileSummary(job)}</p>
              </div>
              <span class="import-job-status">{jobStatusLabel(job)}</span>
            </div>
            <progress max="1" value={Math.max(0, Math.min(1, Number(job.progress) || 0))} aria-label={`${job.label} import progress`}>
              {progressPercent(job)}
            </progress>
            <p class="settings-hint import-job-status-text">{job.status_text}</p>
            {#if job.current_file}
              <p class="settings-hint">Current file: {job.current_file}</p>
            {/if}
            {#if job.errors.length > 0}
              <details class="import-job-errors">
                <summary>
                  {job.error_count} {job.error_count === 1 ? 'error' : 'errors'}
                </summary>
                <ul>
                  {#each job.errors as error}
                    <li>
                      {#if error.file}<strong>{error.file}:</strong> {/if}{error.message}
                    </li>
                  {/each}
                </ul>
              </details>
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
