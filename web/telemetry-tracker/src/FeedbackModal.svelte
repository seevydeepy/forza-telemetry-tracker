<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
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
  let includeDiagnostics = true;
  let diagnosticsInitialized = false;
  let tooltipVisible = false;
  let tooltipX = 0;
  let tooltipY = 0;
  let tooltipElement: HTMLDivElement | null = null;

  const tooltipOffsetPx = 14;
  const tooltipViewportMarginPx = 12;

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

  function showTooltipAt(clientX: number, clientY: number) {
    tooltipVisible = true;
    tooltipX = clientX + tooltipOffsetPx;
    tooltipY = clientY + tooltipOffsetPx;
    void constrainTooltipToViewport();
  }

  async function constrainTooltipToViewport() {
    await tick();
    if (!tooltipVisible || !tooltipElement) return;

    const rect = tooltipElement.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - tooltipViewportMarginPx;
    const maxY = window.innerHeight - rect.height - tooltipViewportMarginPx;
    tooltipX = Math.max(tooltipViewportMarginPx, Math.min(tooltipX, maxX));
    tooltipY = Math.max(tooltipViewportMarginPx, Math.min(tooltipY, maxY));
  }

  function handleDiagnosticsPointer(event: PointerEvent) {
    showTooltipAt(event.clientX, event.clientY);
  }

  function handleDiagnosticsFocus(event: FocusEvent) {
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) return;
    const rect = target.getBoundingClientRect();
    showTooltipAt(rect.left, rect.bottom);
  }

  function hideTooltip() {
    tooltipVisible = false;
  }
</script>

<AppModal title="Send Feedback" panelClass="feedback-modal-panel" on:close={() => dispatch('close')}>
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

    <footer class="feedback-footer">
      <label
        class="feedback-diagnostics"
        on:pointerenter={handleDiagnosticsPointer}
        on:pointermove={handleDiagnosticsPointer}
        on:pointerleave={hideTooltip}
        on:focusin={handleDiagnosticsFocus}
        on:focusout={hideTooltip}
      >
        <input
          type="checkbox"
          bind:checked={includeDiagnostics}
          disabled={submitting}
          aria-describedby="feedback-diagnostics-tooltip"
        />
        <span>Include diagnostics</span>
      </label>

      <div class="modal-actions feedback-actions">
        <button type="button" class="secondary-action" disabled={submitting} on:click={() => dispatch('close')}>Cancel</button>
        <button type="submit" class="primary-action" disabled={!canSubmit}>Send</button>
      </div>
    </footer>
  </form>
</AppModal>

<div
  id="feedback-diagnostics-tooltip"
  bind:this={tooltipElement}
  class:feedback-tooltip-visible={tooltipVisible}
  class="feedback-tooltip"
  role="tooltip"
  aria-hidden={!tooltipVisible}
  style={`left: ${tooltipX}px; top: ${tooltipY}px;`}
>
  {config.diagnostics_description}
</div>

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

  .feedback-field span {
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

  .feedback-footer {
    align-items: center;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    justify-content: space-between;
    min-width: 0;
    row-gap: 0.75rem;
  }

  .feedback-diagnostics {
    align-items: center;
    color: var(--text-primary);
    display: flex;
    gap: 0.55rem;
    min-width: 0;
    width: fit-content;
  }

  .feedback-actions {
    flex: 0 0 auto;
    gap: 0.75rem;
    margin-left: auto;
  }

  .feedback-diagnostics input {
    flex: 0 0 auto;
  }

  .feedback-diagnostics span {
    overflow-wrap: anywhere;
  }

  .feedback-tooltip {
    background: #18181b;
    border: 1px solid var(--panel-border);
    border-radius: 0.5rem;
    box-shadow: 0 16px 40px rgba(0, 0, 0, 0.38);
    color: var(--text-secondary);
    font-size: 0.9rem;
    line-height: 1.45;
    max-width: min(34rem, calc(100vw - 64px));
    opacity: 0;
    padding: 0.65rem 0.75rem;
    pointer-events: none;
    position: fixed;
    transition: opacity 120ms ease;
    visibility: hidden;
    width: max-content;
    z-index: 2000;
  }

  .feedback-tooltip-visible {
    opacity: 1;
    visibility: visible;
  }

  @media (max-width: 680px) {
    .feedback-form {
      min-width: 0;
      width: calc(100vw - 48px);
    }
  }

  @media (max-width: 480px) {
    :global(.feedback-modal-panel) {
      max-width: calc(100vw - 24px);
    }

    :global(.feedback-modal-panel .modal-body) {
      padding: 0.75rem;
    }

    .feedback-form {
      max-width: none;
      width: 100%;
    }

    .feedback-footer {
      flex-wrap: nowrap;
      gap: 0.5rem;
    }

    .feedback-diagnostics {
      font-size: 0.875rem;
      gap: 0.4rem;
      white-space: nowrap;
    }

    .feedback-actions {
      gap: 0.4rem;
    }

    .feedback-actions :global(.primary-action),
    .feedback-actions :global(.secondary-action) {
      padding: 0.45rem 0.55rem;
    }
  }

  @media (max-width: 360px) {
    :global(.feedback-modal-panel .modal-body) {
      padding: 0.5rem;
    }

    .feedback-diagnostics {
      font-size: 0.8125rem;
      gap: 0.3rem;
    }

    .feedback-actions {
      gap: 0.3rem;
    }

    .feedback-actions :global(.primary-action),
    .feedback-actions :global(.secondary-action) {
      padding: 0.35rem 0.45rem;
    }
  }
</style>
