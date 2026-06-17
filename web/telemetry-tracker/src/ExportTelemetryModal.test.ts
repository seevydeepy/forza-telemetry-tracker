import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ExportTelemetryModal from './ExportTelemetryModal.svelte';
import type { TelemetryExportDefaults, TelemetryExportJob } from './types';

const defaultsFixture: TelemetryExportDefaults = {
  output_dir: 'C:\\Users\\driver\\Documents\\Forza exports',
  filename_prefix: 'forza-telemetry',
  estimate: {
    raw_packet_count: 2,
    raw_byte_count: 2048,
    curated_sample_count: 2,
    session_count: 1,
    lap_count: 1
  }
};

const completedJob: TelemetryExportJob = {
  id: 'export-completed-1',
  kind: 'curated_csv',
  label: 'Curated CSV export',
  status: 'completed',
  status_text: 'Export completed',
  progress: 1,
  output_dir: defaultsFixture.output_dir,
  filename_prefix: defaultsFixture.filename_prefix,
  output_files: [
    {
      path: 'C:\\Users\\driver\\Documents\\Forza exports\\forza-telemetry-curated.csv',
      filename: 'forza-telemetry-curated.csv',
      size_bytes: 2048
    }
  ],
  total_size_bytes: 2048,
  row_count: 2,
  created_at_ms: 1710000000000,
  started_at_ms: 1710000001000,
  completed_at_ms: 1710000002000,
  duration_ms: 1000,
  error: null,
  can_cancel: false
};

const runningJob: TelemetryExportJob = {
  ...completedJob,
  id: 'export-running-1',
  kind: 'raw_binary',
  label: 'Raw binary export',
  status: 'running',
  status_text: 'Writing raw packet package',
  progress: 0.5,
  output_files: [],
  total_size_bytes: 0,
  row_count: 0,
  completed_at_ms: null,
  duration_ms: null,
  can_cancel: true
};

function renderExportModal(props: Partial<{ defaults: TelemetryExportDefaults | null; jobs: TelemetryExportJob[] }> = {}) {
  const close = vi.fn();
  const onExport = vi.fn();
  const refreshjobs = vi.fn();
  const canceljob = vi.fn();
  const result = render(ExportTelemetryModal, {
    props: {
      defaults: defaultsFixture,
      jobs: [],
      ...props
    },
    events: {
      close,
      export: onExport,
      refreshjobs,
      canceljob
    }
  });

  return { close, onExport, refreshjobs, canceljob, ...result };
}

describe('ExportTelemetryModal', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders export defaults, estimates, and export actions', () => {
    renderExportModal();

    expect(screen.getByRole('dialog', { name: 'Export telemetry' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Output folder' })).toHaveValue(defaultsFixture.output_dir);
    expect(screen.getByRole('textbox', { name: 'File name prefix' })).toHaveValue(defaultsFixture.filename_prefix);
    expect(screen.getByText(/2 raw packets/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export raw binary package' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export raw CSV' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Export curated CSV' })).toBeInTheDocument();
  });

  it('moves export guidance into title and jobs help popovers', async () => {
    renderExportModal();
    const dialog = screen.getByRole('dialog', { name: 'Export telemetry' });
    const titleHelpButton = within(dialog).getByRole('button', { name: 'Telemetry export help' });

    expect(dialog.querySelector('.modal-title-row')).toContainElement(titleHelpButton);
    expect(within(dialog).queryByText(/Exports dump the full telemetry database/i)).not.toBeInTheDocument();
    await fireEvent.click(titleHelpButton);
    const titleHelp = within(dialog).getByRole('dialog', { name: 'Telemetry export help' });
    expect(titleHelp).toHaveTextContent(/Exports dump the full telemetry database/i);
    expect(titleHelp).toHaveTextContent(/Choose an output folder and file name prefix/i);
    await fireEvent.pointerDown(document.body);
    expect(within(dialog).queryByRole('dialog', { name: 'Telemetry export help' })).not.toBeInTheDocument();

    const jobsHelpButton = within(dialog).getByRole('button', { name: 'Export jobs help' });
    expect(jobsHelpButton.closest('.section-title-row')).toContainElement(jobsHelpButton);
    await fireEvent.click(jobsHelpButton);
    expect(within(dialog).getByRole('dialog', { name: 'Export jobs help' })).toHaveTextContent(/Jobs stay here until the tracker closes/i);
  });

  it('restores the default exports folder after a manual edit', async () => {
    renderExportModal();

    const outputFolder = screen.getByRole('textbox', { name: 'Output folder' });
    await fireEvent.input(outputFolder, { target: { value: 'D:\\temporary\\exports' } });
    expect(outputFolder).toHaveValue('D:\\temporary\\exports');

    await fireEvent.click(screen.getByRole('button', { name: 'Use default exports folder' }));

    expect(outputFolder).toHaveValue(defaultsFixture.output_dir);
  });

  it('uses the native export folder picker when available', async () => {
    const choose_export_folder = vi.fn(async () => 'E:\\Telemetry Exports');
    vi.stubGlobal('pywebview', { api: { choose_export_folder } });
    renderExportModal();

    const outputFolder = screen.getByRole('textbox', { name: 'Output folder' });
    const browseButton = screen.getByRole('button', { name: 'Browse' });
    expect(outputFolder.closest('.file-picker-row')).toContainElement(browseButton);

    await fireEvent.click(browseButton);

    expect(choose_export_folder).toHaveBeenCalledWith(defaultsFixture.output_dir);
    expect(outputFolder).toHaveValue('E:\\Telemetry Exports');
  });

  it('dispatches curated CSV exports with the chosen folder and prefix', async () => {
    const { onExport } = renderExportModal();

    await fireEvent.input(screen.getByRole('textbox', { name: 'Output folder' }), { target: { value: '  D:\\telemetry  ' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'File name prefix' }), { target: { value: '  rivals-night  ' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Export curated CSV' }));

    expect(onExport).toHaveBeenCalledTimes(1);
    expect(onExport.mock.calls[0][0].detail).toEqual({
      kind: 'curated_csv',
      output_dir: 'D:\\telemetry',
      filename_prefix: 'rivals-night'
    });
  });

  it('renders null defaults with disabled export actions', () => {
    renderExportModal({ defaults: null });

    expect(screen.getByRole('textbox', { name: 'Output folder' })).toHaveValue('');
    expect(screen.getByRole('textbox', { name: 'File name prefix' })).toHaveValue('');
    expect(screen.getByText('Export estimate unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use default exports folder' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export raw binary package' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export raw CSV' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export curated CSV' })).toBeDisabled();
  });

  it('disables exports when the output folder is cleared or whitespace', async () => {
    const { onExport } = renderExportModal();

    const outputFolder = screen.getByRole('textbox', { name: 'Output folder' });
    await fireEvent.input(outputFolder, { target: { value: '   ' } });

    expect(screen.getByRole('button', { name: 'Export raw binary package' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export raw CSV' })).toBeDisabled();
    const curatedButton = screen.getByRole('button', { name: 'Export curated CSV' });
    expect(curatedButton).toBeDisabled();
    await fireEvent.click(curatedButton);
    expect(onExport).not.toHaveBeenCalled();
  });

  it('does not clobber user edits when refreshed defaults change', async () => {
    const { rerender } = renderExportModal();

    await fireEvent.input(screen.getByRole('textbox', { name: 'Output folder' }), { target: { value: 'D:\\custom\\exports' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'File name prefix' }), { target: { value: 'custom-prefix' } });

    await rerender({
      defaults: {
        ...defaultsFixture,
        output_dir: 'E:\\new-defaults',
        filename_prefix: 'new-default-prefix'
      },
      jobs: []
    });

    expect(screen.getByRole('textbox', { name: 'Output folder' })).toHaveValue('D:\\custom\\exports');
    expect(screen.getByRole('textbox', { name: 'File name prefix' })).toHaveValue('custom-prefix');
  });

  it('updates untouched fields when refreshed defaults change', async () => {
    const { rerender } = renderExportModal();

    await fireEvent.input(screen.getByRole('textbox', { name: 'Output folder' }), { target: { value: 'D:\\custom\\exports' } });

    await rerender({
      defaults: {
        ...defaultsFixture,
        output_dir: 'E:\\new-defaults',
        filename_prefix: 'new-default-prefix'
      },
      jobs: []
    });

    expect(screen.getByRole('textbox', { name: 'Output folder' })).toHaveValue('D:\\custom\\exports');
    expect(screen.getByRole('textbox', { name: 'File name prefix' })).toHaveValue('new-default-prefix');
  });

  it('renders completed job details with the completed status tone', () => {
    const { container } = renderExportModal({ jobs: [completedJob] });

    const card = container.querySelector('[data-status-tone="completed"]');
    expect(card).toBeInTheDocument();
    const jobCard = card as HTMLElement;
    expect(within(jobCard).getByText('forza-telemetry-curated.csv')).toBeInTheDocument();
    expect(within(jobCard).getAllByText('2,048 bytes').length).toBeGreaterThan(0);
    expect(within(jobCard).getAllByText('2 rows').length).toBeGreaterThan(0);
    expect(within(jobCard).getByText('1.0s')).toBeInTheDocument();
    expect(within(jobCard).getByText('C:\\Users\\driver\\Documents\\Forza exports\\forza-telemetry-curated.csv')).toBeInTheDocument();
  });

  it('renders sanitized failed job errors', () => {
    const failedJob: TelemetryExportJob = {
      ...completedJob,
      id: 'export-failed-1',
      status: 'failed',
      status_text: 'Telemetry export failed.',
      output_files: [],
      total_size_bytes: 0,
      row_count: 0,
      completed_at_ms: 1710000002000,
      duration_ms: 1000,
      error: 'Telemetry export failed. Check the application logs for details.'
    };
    renderExportModal({ jobs: [failedJob] });

    expect(screen.getByText('Error: Telemetry export failed. Check the application logs for details.')).toBeInTheDocument();
    expect(screen.queryByText(/No recorded telemetry is available to export/i)).not.toBeInTheDocument();
  });

  it('dispatches cancellation for a running job', async () => {
    const { canceljob } = renderExportModal({ jobs: [runningJob] });

    await fireEvent.click(screen.getByRole('button', { name: 'Cancel job' }));

    expect(canceljob).toHaveBeenCalledTimes(1);
    expect(canceljob.mock.calls[0][0].detail).toEqual({ jobId: 'export-running-1' });
  });

  it('dispatches refresh requests and renders the empty job state', async () => {
    const { refreshjobs } = renderExportModal({ jobs: [] });

    expect(screen.getByText('No export jobs are currently queued, running, or completed.')).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(refreshjobs).toHaveBeenCalledTimes(1);
  });
});
