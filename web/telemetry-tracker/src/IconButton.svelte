<script lang="ts">
  import Icon, { type IconName } from './Icon.svelte';

  export let icon: IconName;
  export let label: string;
  export let title = label;
  export let pressed: boolean | null = null;
  export let disabled = false;
  export let kind: 'default' | 'primary' | 'danger' = 'default';
  export let type: 'button' | 'submit' | 'reset' = 'button';
  export let className = '';
  export let onClick: ((event: MouseEvent) => void) | null = null;
</script>

<button {type} class={`app-icon-button app-icon-button-${kind} ${className}`.trim()} aria-label={label} aria-pressed={pressed === null ? undefined : pressed} title={title} disabled={disabled} on:click={(event) => onClick?.(event)}>
  <Icon name={icon} />
  <slot />
</button>
