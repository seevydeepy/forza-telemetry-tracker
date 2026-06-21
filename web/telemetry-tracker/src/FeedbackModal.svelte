<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import AppModal from './AppModal.svelte';
  import type { FeedbackCategory, FeedbackConfig, FeedbackReportInput } from './types';

  export let config: FeedbackConfig;
  export let submitting = false;

  const dispatch = createEventDispatcher<{
    close: void;
    submit: FeedbackReportInput;
  }>();

  const placeholders: Record<FeedbackCategory, string> = {
    Bug: 'What went wrong, and what were you doing just before it happened?',
    'Data Out setup': 'What step of the Forza Data Out setup is confusing or failing?',
    'Telemetry recording': 'What happened while recording or reviewing telemetry?',
    'Map or route visualisation': 'What looks wrong on the map or route visualisation?',
    'Import or export': 'What file or workflow did you try to import or export?',
    Performance: 'What felt slow, and roughly how large was the session?',
    'UI or UX': 'What was hard to find, read, or use?',
    Other: 'What would you like to tell us?'
  };

  let category: FeedbackCategory = 'Bug';
  let description = '';
  let includeDiagnostics = false;
  let diagnosticsInitialized = false;

  $: categories = config?.categories?.length ? config.categories : (['Bug', 'Other'] as FeedbackCategory[]);
  $: if (!categories.includes(category)) {
    category = categories[0];
  }
  $: if (!diagnosticsInitialized && config) {
    includeDiagnostics = Boolean(config.diagnostics_default);
    diagnosticsInitialized = true;
  }
  $: trimmedDescription = description.trim();
  $: maxLength = config?.max_description_length ?? 4000;
  $: canSubmit = !submitting && trimmedDescription.length >= 3 && trimmedDescription.length <= maxLength;
  $: placeholder = placeholders[category] ?? placeholders.Other;

  function handleSubmit() {
    if (!canSubmit) return;
    dispatch('submit', {
      category,
      description: trimmedDescription,
      include_diagnostics: includeDiagnostics,
      source: 'desktop-app'
    });
  }
</script>

<AppModal title="Send Feedback" on:close={() => dispatch('close')}>
  <form class="feedback-form" aria-label="Send feedback form" on:submit|preventDefault={handleSubmit}>
    <label class="feedback-field">
      <span>Category</span>
      <select bind:value={category} disabled={submitting}>
        {#each categories as option}
          <option value={option}>{option}</option>
        {/each}
      </select>
    </label>

    <label class="feedback-field">
      <span>Description</span>
      <textarea
        bind:value={description}
        disabled={submitting}
        maxlength={maxLength}
        placeholder={placeholder}
        rows="8"
      ></textarea>
    </label>

    <label class="feedback-diagnostics">
      <input type="checkbox" bind:checked={includeDiagnostics} disabled={submitting} />
      <span>Include diagnostics</span>
    </label>
    <p class="feedback-disclosure">{config.diagnostics_description}</p>

    <div class="modal-actions">
      <button type="button" class="secondary-action" disabled={submitting} on:click={() => dispatch('close')}>Cancel</button>
      <button type="submit" class="primary-action" disabled={!canSubmit}>Send</button>
    </div>
  </form>
</AppModal>

<style>
  .feedback-form {
    display: grid;
    gap: 0.85rem;
    max-width: min(42rem, calc(100vw - 96px));
    min-width: min(34rem, calc(100vw - 96px));
  }

  .feedback-field {
    display: grid;
    gap: 0.35rem;
  }

  .feedback-field span,
  .feedback-disclosure {
    color: var(--text-secondary);
  }

  .feedback-field select,
  .feedback-field textarea {
    background: #18181b;
    border: 1px solid var(--panel-border);
    border-radius: 0.65rem;
    color: #e2e8f0;
    font: inherit;
    padding: 0.55rem 0.65rem;
  }

  .feedback-field textarea {
    min-height: 11rem;
    resize: vertical;
  }

  .feedback-diagnostics {
    align-items: center;
    color: var(--text-primary);
    display: flex;
    gap: 0.55rem;
  }

  .feedback-disclosure {
    line-height: 1.45;
    margin: 0;
  }

  @media (max-width: 680px) {
    .feedback-form {
      min-width: 0;
      width: calc(100vw - 48px);
    }
  }
</style>
