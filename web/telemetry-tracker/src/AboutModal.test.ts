import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AboutModal from './AboutModal.svelte';
import type { AppAboutPayload, AppUpdateCheckResponse } from './types';

const aboutPayload: AppAboutPayload = {
  name: 'Forza Telemetry Tracker',
  version: '1.0.0',
  release_date: '2026-06-13',
  git_sha: 'abcdef123456',
  channel: 'stable',
  repository: 'owner/repo',
  packaged: true,
  updates: {
    supported: true,
    release_access: 'public'
  }
};

const updateAvailable: AppUpdateCheckResponse = {
  status: 'update_available',
  current_version: '1.0.0',
  latest_version: '1.1.0',
  release_url: 'https://github.example/releases/v1.1.0',
  published_at: '2026-06-13T12:00:00Z',
  asset_name: 'ForzaTelemetryTrackerSetup-v1.1.0-x64.exe',
  message: 'Update 1.1.0 is available.'
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status });
}

function renderAboutModal() {
  return render(AboutModal);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('AboutModal', () => {
  it('loads and displays installed release metadata and update readiness', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(aboutPayload)));

    renderAboutModal();

    const dialog = await screen.findByRole('dialog', { name: 'About' });
    expect(await within(dialog).findByText('Forza Telemetry Tracker')).toBeInTheDocument();
    expect(within(dialog).getByText('Installed version 1.0.0')).toBeInTheDocument();
    expect(within(dialog).getByText('stable')).toBeInTheDocument();
    expect(within(dialog).getByText('owner/repo')).toBeInTheDocument();
    expect(within(dialog).getByText('Public GitHub Releases')).toBeInTheDocument();
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    const supportLink = within(dialog).getByRole('link', { name: 'Support SeevyDeepy on Ko-fi' });
    expect(supportLink).toHaveAttribute('href', 'https://ko-fi.com/Z4I021C66X');
    expect(supportLink).toHaveAttribute('target', '_blank');
    expect(supportLink).toHaveAttribute('rel', 'noreferrer');
    expect(within(supportLink).getByAltText('Buy Me a Coffee at ko-fi.com')).toHaveAttribute(
      'src',
      'https://storage.ko-fi.com/cdn/kofi3.png?v=6'
    );
    expect(within(dialog).getByRole('button', { name: 'Check for updates' })).toBeInTheDocument();
  });

  it('replaces check with a GitHub release link when a newer release is available', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url === '/api/app/about') return jsonResponse(aboutPayload);
      if (url === '/api/app/update/check') {
        expect(init?.method).toBe('POST');
        return jsonResponse(updateAvailable);
      }
      return jsonResponse({}, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderAboutModal();

    await fireEvent.click(await screen.findByRole('button', { name: 'Check for updates' }));
    const releaseLink = await screen.findByRole('link', { name: 'Open release 1.1.0' });

    expect(screen.queryByRole('button', { name: 'Check for updates' })).not.toBeInTheDocument();
    expect(releaseLink).toHaveAttribute('href', updateAvailable.release_url);
    expect(releaseLink).toHaveAttribute('target', '_blank');
    expect(screen.getByText('Download and run the installer from GitHub Releases when you are ready.')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/install'))).toBe(false);
  });

  it('does not render credential setup for public releases', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url === '/api/app/about') return jsonResponse(aboutPayload);
      return jsonResponse({}, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderAboutModal();

    const dialog = await screen.findByRole('dialog', { name: 'About' });
    await within(dialog).findByText('Public GitHub Releases');

    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith('/api/app/update/token', expect.anything());
  });
});
