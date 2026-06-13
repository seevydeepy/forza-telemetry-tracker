<script lang="ts">
  import type { ToastMessage } from './types';

  export let toasts: ToastMessage[] = [];
  export let dismiss: (id: number) => void;
</script>

<div class="toast-stack" aria-live="polite" aria-label="Status notifications">
  {#each toasts as toast}
    <article class={`toast toast-${toast.level}`} role={toast.level === 'error' ? 'alert' : 'status'}>
      <span>{toast.message}</span>
      {#if toast.sticky}
        <button
          class="toast-close"
          aria-label="Dismiss notification"
          title="Dismiss notification"
          on:click={() => dismiss(toast.id)}
        >
          ×
        </button>
      {/if}
    </article>
  {/each}
</div>
