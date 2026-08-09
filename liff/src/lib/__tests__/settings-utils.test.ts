/**
 * lib/settings-utils.ts のユニットテスト。
 */
import { describe, expect, it } from 'vitest';
import { isValidHHMM, sanitizeSettings } from '../settings-utils';

describe('isValidHHMM', () => {
	it('accepts valid times', () => {
		expect(isValidHHMM('07:30')).toBe(true);
		expect(isValidHHMM('00:00')).toBe(true);
		expect(isValidHHMM('23:59')).toBe(true);
	});

	it('rejects invalid formats', () => {
		expect(isValidHHMM('7:30')).toBe(false);
		expect(isValidHHMM('8am')).toBe(false);
		expect(isValidHHMM('25:00')).toBe(false);
		expect(isValidHHMM('')).toBe(false);
		expect(isValidHHMM('07:60')).toBe(false);
	});
});

describe('sanitizeSettings', () => {
	it('returns only changed fields compared to original', () => {
		const original = { morning_time: '07:30', evening_time: '22:00', evening_enabled: true, timezone: 'Asia/Tokyo' };
		const edited   = { morning_time: '08:00', evening_time: '22:00', evening_enabled: true, timezone: 'Asia/Tokyo' };
		expect(sanitizeSettings(original, edited)).toEqual({ morning_time: '08:00' });
	});

	it('returns empty object when nothing changed', () => {
		const s = { morning_time: '07:30', evening_time: '22:00', evening_enabled: true, timezone: 'Asia/Tokyo' };
		expect(sanitizeSettings(s, s)).toEqual({});
	});

	it('includes boolean change', () => {
		const original = { morning_time: '07:30', evening_time: '22:00', evening_enabled: true,  timezone: 'Asia/Tokyo' };
		const edited   = { morning_time: '07:30', evening_time: '22:00', evening_enabled: false, timezone: 'Asia/Tokyo' };
		expect(sanitizeSettings(original, edited)).toEqual({ evening_enabled: false });
	});

	it('rejects invalid time format', () => {
		const original = { morning_time: '07:30', evening_time: '22:00', evening_enabled: true, timezone: 'Asia/Tokyo' };
		const edited   = { morning_time: 'bad',   evening_time: '22:00', evening_enabled: true, timezone: 'Asia/Tokyo' };
		expect(() => sanitizeSettings(original, edited)).toThrow(/HH:MM/);
	});
});
