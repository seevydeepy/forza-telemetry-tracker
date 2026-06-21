<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import IconButton from './IconButton.svelte';

  export let title: string;
  export let ariaLabel: string | null = null;
  export let closeLabel: string | null = null;
  export let labelledById = `modal-title-${Math.random().toString(36).slice(2)}`;
  export let panelClass = '';

  const dispatch = createEventDispatcher<{ close: void }>();
  const FOCUSABLE_SELECTOR = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])'
  ].join(',');

  let panel: HTMLDivElement;

  function close() {
    dispatch('close');
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      close();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }

    if (event.key === 'Tab') {
      trapFocus(event);
    }
  }

  function focusableElements(): HTMLElement[] {
    if (!panel) return [];
    return Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
      (element) =>
        element.tabIndex >= 0 &&
        !element.hidden &&
        !element.hasAttribute('disabled') &&
        element.getAttribute('aria-hidden') !== 'true' &&
        !element.closest('[hidden],[inert],[aria-hidden="true"]')
    );
  }

  function trapFocus(event: KeyboardEvent) {
    const focusable = focusableElements();
    if (focusable.length === 0) {
      event.preventDefault();
      panel?.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;

    if (!panel?.contains(active)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
      return;
    }

    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
      return;
    }

    if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  onMount(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    void tick().then(() => panel?.focus());
    return () => previous?.focus();
  });
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="modal-backdrop" role="presentation" on:click={handleBackdropClick}>
  <div
    bind:this={panel}
    class={`modal-panel${panelClass ? ` ${panelClass}` : ''}`}
    role="dialog"
    aria-modal="true"
    aria-label={ariaLabel ?? undefined}
    aria-labelledby={ariaLabel ? undefined : labelledById}
    tabindex="-1"
  >
    <header class="modal-header">
      <div class="modal-title-row">
        <h2 id={labelledById}>{title}</h2>
        <slot name="titleAccessory" />
      </div>
      <IconButton icon="close" label={closeLabel ?? `Close ${title}`} title={closeLabel ?? `Close ${title}`} onClick={close} />
    </header>
    <div class="modal-body">
      <slot />
    </div>
  </div>
</div>
