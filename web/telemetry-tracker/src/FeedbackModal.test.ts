import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import FeedbackModal from './FeedbackModal.svelte';
import type { FeedbackConfig, FeedbackReportInput } from './types';

const feedbackConfig: FeedbackConfig = {
  enabled: true,
  categories: [
    'Bug',
    'Data Out setup',
    'Telemetry recording',
    'Map or route visualisation',
    'Import or export',
    'Performance',
    'UI or UX',
    'Other'
  ],
  max_description_length: 4000,
  diagnostics_default: true,
  diagnostics_description:
    'Diagnostics may include app version, platform, listener/capture status, local database/log sizes, row counts, and recent sanitized app log lines. They do not include raw telemetry packets, session databases, map cache files, game files, screenshots, exports, or personal data of any kind.'
};

function renderFeedbackModal() {
  return render(FeedbackModal, { props: { config: feedbackConfig } });
}

describe('FeedbackModal', () => {
  it('renders the send feedback dialog, categories, diagnostics tooltip, and default-on toggle', () => {
    renderFeedbackModal();

    const dialog = screen.getByRole('dialog', { name: 'Send Feedback' });
    const category = within(dialog).getByLabelText('Category');
    expect(category).toBeInTheDocument();
    for (const option of feedbackConfig.categories) {
      expect(within(category).getByRole('option', { name: option })).toBeInTheDocument();
    }
    const diagnosticsCheckbox = within(dialog).getByRole('checkbox', { name: 'Include diagnostics' });
    expect(diagnosticsCheckbox).toBeChecked();
    const tooltip = within(dialog).getByRole('tooltip', { hidden: true });
    expect(diagnosticsCheckbox).toHaveAttribute('aria-describedby', tooltip.id);
    expect(diagnosticsCheckbox.closest('.feedback-diagnostics-row')).toContainElement(tooltip);
    expect(tooltip).toHaveClass('feedback-tooltip');
    expect(tooltip).toHaveTextContent(feedbackConfig.diagnostics_description);
    expect(within(dialog).queryByText(/sending/i)).not.toBeInTheDocument();
  });

  it('changes the description placeholder by category', async () => {
    renderFeedbackModal();

    const dialog = screen.getByRole('dialog', { name: 'Send Feedback' });
    const category = within(dialog).getByLabelText('Category');
    const description = within(dialog).getByLabelText('Description');

    expect(description).toHaveAttribute(
      'placeholder',
      'What went wrong, and what were you doing just before it happened?'
    );
    await fireEvent.change(category, { target: { value: 'Data Out setup' } });
    expect(description).toHaveAttribute(
      'placeholder',
      'What step of the Forza Data Out setup is confusing or failing?'
    );
    await fireEvent.change(category, { target: { value: 'Other' } });
    expect(description).toHaveAttribute('placeholder', 'What would you like to tell us?');
  });

  it('disables send until the trimmed description has at least three characters', async () => {
    renderFeedbackModal();

    const dialog = screen.getByRole('dialog', { name: 'Send Feedback' });
    const send = within(dialog).getByRole('button', { name: 'Send' });
    const description = within(dialog).getByLabelText('Description');

    expect(send).toBeDisabled();
    await fireEvent.input(description, { target: { value: '  no  ' } });
    expect(send).toBeDisabled();
    await fireEvent.input(description, { target: { value: '  yes  ' } });
    expect(send).toBeEnabled();
  });

  it('dispatches submit with the expected feedback payload', async () => {
    const submit = vi.fn();
    render(FeedbackModal, {
      props: {
        config: feedbackConfig
      },
      events: {
        submit: (event: CustomEvent<FeedbackReportInput>) => submit(event.detail)
      }
    } as never);

    const dialog = screen.getByRole('dialog', { name: 'Send Feedback' });
    await fireEvent.change(within(dialog).getByLabelText('Category'), { target: { value: 'Other' } });
    await fireEvent.input(within(dialog).getByLabelText('Description'), {
      target: { value: '  I want to share a note.  ' }
    });
    await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Include diagnostics' }));
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Send' }));

    expect(submit).toHaveBeenCalledWith({
      category: 'Other',
      description: 'I want to share a note.',
      include_diagnostics: false,
      source: 'desktop-app'
    });
  });
});
