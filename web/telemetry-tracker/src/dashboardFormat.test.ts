import { describe, expect, it } from 'vitest';
import {
  formatBoost,
  formatDegrees,
  formatFuel,
  formatInputPercent,
  formatPower,
  formatRpm,
  formatSpeed,
  formatTemperature,
  formatTime,
  formatTorque
} from './dashboardFormat';

describe('dashboardFormat', () => {
  it('formats missing values consistently', () => {
    expect(formatSpeed(null, 'imperial')).toBe('—');
    expect(formatRpm(undefined)).toBe('—');
  });

  it('formats speed for the selected unit system', () => {
    expect(formatSpeed(44.704, 'imperial')).toBe('100 mph');
    expect(formatSpeed(27.7778, 'metric')).toBe('100 km/h');
  });

  it('formats common dashboard quantities', () => {
    expect(formatRpm(7250)).toBe('7,250 rpm');
    expect(formatInputPercent(128)).toBe('50%');
    expect(formatDegrees(Math.PI / 2)).toBe('90°');
    expect(formatBoost(1.234)).toBe('1.23 bar');
    expect(formatTemperature(91.6)).toBe('92°C');
    expect(formatTime(72.345)).toBe('1:12.345');
    expect(formatFuel(0.625)).toBe('62.5%');
    expect(formatPower(372_850)).toBe('500 hp');
    expect(formatTorque(500)).toBe('369 lb-ft');
  });
});
