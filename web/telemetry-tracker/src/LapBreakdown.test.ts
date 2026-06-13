import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import LapBreakdown from './LapBreakdown.svelte';
import type { AnalysisSummary, ReferenceLap } from './types';

const summary: AnalysisSummary = {
  packet_count: 3,
  top_speed_mps: 45.678,
  average_speed_mps: 32.809,
  peak_combined_slip: 0.4567,
  limiter_samples: 2,
  bottoming_events: 1,
  start_sequence: 10,
  end_sequence: 12,
  lap_time_ms: 96_234
};

const referenceLap: ReferenceLap = {
  lap_id: 'ref-lap',
  session_id: 'ref-session',
  lap_time_ms: 95_000,
  lap_duration_ms: 95_000,
  source: 'session_best',
  summary: {
    packet_count: 2,
    top_speed_mps: 22.222,
    average_speed_mps: 17.167,
    peak_combined_slip: 0.1111,
    limiter_samples: 0,
    bottoming_events: 0,
    start_sequence: 1,
    end_sequence: 2,
    lap_time_ms: 95_000,
    lap_duration_ms: 95_000
  }
};

describe('LapBreakdown', () => {
  it('shows split labels for all comparable fields when referenceLap is provided', () => {
    render(LapBreakdown, {
      props: {
        summary,
        referenceLap,
        unitSystem: 'imperial'
      }
    });

    // Lap time split: 96_234 - 95_000 = +1_234ms = +1.234s
    const lapTimeSplit = screen.getByLabelText('Lap time split: +1.234');
    expect(lapTimeSplit).toBeInTheDocument();
    expect(lapTimeSplit).toHaveClass('worse');
    expect(lapTimeSplit).toHaveClass('split-badge');

    // Top speed split: 45.678 - 22.222 = +23.456 mps → +52.5 imperial
    const topSpeedSplit = screen.getByLabelText('Top speed split: +52.5');
    expect(topSpeedSplit).toBeInTheDocument();
    expect(topSpeedSplit).toHaveClass('better');
    expect(topSpeedSplit).toHaveClass('split-badge');

    // Average speed split: 32.809 - 17.167 = +15.642 mps → +35.0 imperial
    const avgSpeedSplit = screen.getByLabelText('Average speed split: +35.0');
    expect(avgSpeedSplit).toBeInTheDocument();
    expect(avgSpeedSplit).toHaveClass('better');

    // Peak slip split: 0.4567 - 0.1111 = +0.3456
    const peakSlipSplit = screen.getByLabelText('Peak slip split: +0.3456');
    expect(peakSlipSplit).toBeInTheDocument();
    expect(peakSlipSplit).toHaveClass('worse');

    // Limiter split: 2 - 0 = +2
    const limiterSplit = screen.getByLabelText('Limiter samples split: +2');
    expect(limiterSplit).toBeInTheDocument();
    expect(limiterSplit).toHaveClass('worse');

    // Bottoming split: 1 - 0 = +1
    const bottomingSplit = screen.getByLabelText('Bottoming events split: +1');
    expect(bottomingSplit).toBeInTheDocument();
    expect(bottomingSplit).toHaveClass('worse');
  });

  it('does not show split labels without a referenceLap', () => {
    render(LapBreakdown, {
      props: {
        summary,
        referenceLap: null,
        unitSystem: 'imperial'
      }
    });

    expect(screen.queryByLabelText(/split:/)).not.toBeInTheDocument();
  });

  it('does not show split labels or Lap time row when selectedRange is set', () => {
    render(LapBreakdown, {
      props: {
        summary,
        referenceLap,
        unitSystem: 'imperial',
        selectedRange: { startSequence: 11, endSequence: 12 }
      }
    });

    expect(screen.queryByLabelText(/split:/)).not.toBeInTheDocument();
    expect(screen.queryByText('Lap time')).not.toBeInTheDocument();
  });

  it('uses metric speed factors for split labels', () => {
    render(LapBreakdown, {
      props: {
        summary,
        referenceLap,
        unitSystem: 'metric'
      }
    });

    // Top speed: 23.456 * 3.6 = 84.4416 → +84.4
    expect(screen.getByLabelText('Top speed split: +84.4')).toBeInTheDocument();

    // Average speed: 15.642 * 3.6 = 56.3112 → +56.3
    expect(screen.getByLabelText('Average speed split: +56.3')).toBeInTheDocument();
  });

  it('shows better class for negative lap time split when current is faster', () => {
    const fasterSummary: AnalysisSummary = { ...summary, lap_time_ms: 94_000 };
    render(LapBreakdown, {
      props: {
        summary: fasterSummary,
        referenceLap,
        unitSystem: 'imperial'
      }
    });

    // 94_000 - 95_000 = -1_000ms = -1.000s → better
    const lapTimeSplit = screen.getByLabelText('Lap time split: -1.000');
    expect(lapTimeSplit).toBeInTheDocument();
    expect(lapTimeSplit).toHaveClass('better');
  });

  it('shows neutral class when current matches reference', () => {
    const matchingRef: ReferenceLap = {
      ...referenceLap,
      summary: { ...referenceLap.summary, top_speed_mps: 45.678 } as AnalysisSummary
    };
    render(LapBreakdown, {
      props: {
        summary,
        referenceLap: matchingRef,
        unitSystem: 'imperial'
      }
    });

    // 45.678 - 45.678 = 0 → neutral (no + sign for zero)
    expect(screen.getByLabelText('Top speed split: 0.0')).toHaveClass('neutral');
  });
});
