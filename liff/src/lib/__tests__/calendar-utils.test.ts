/**
 * lib/calendar-utils.ts のユニットテスト。
 */
import { describe, expect, it } from 'vitest';
import {
	buildServingMap,
	cellStatus,
	dayServings,
	formatLocalTime,
	monthRange,
} from '../calendar-utils';
import type { Serving } from '../api';

// ---------- テストデータ ----------

function makeServing(overrides: Partial<Serving> = {}): Serving {
	return {
		id: 1,
		scheduled_date: '2026-05-06',
		slot: 'morning',
		taken_at: null,
		pushed_at: null,
		...overrides,
	};
}

const MORNING_TAKEN = makeServing({ id: 1, slot: 'morning', taken_at: '2026-05-06T07:45:00', pushed_at: '2026-05-06T07:30:00' });
const MORNING_PUSHED = makeServing({ id: 2, slot: 'morning', pushed_at: '2026-05-06T07:30:00' });
const EVENING_TAKEN = makeServing({ id: 3, slot: 'evening', taken_at: '2026-05-06T22:10:00', pushed_at: '2026-05-06T22:00:00' });
const EVENING_PUSHED = makeServing({ id: 4, slot: 'evening', pushed_at: '2026-05-06T22:00:00' });

// ---------- buildServingMap ----------

describe('buildServingMap', () => {
	it('indexes servings by date and slot', () => {
		const map = buildServingMap([MORNING_TAKEN, EVENING_PUSHED]);
		expect(map['2026-05-06']['morning']).toEqual(MORNING_TAKEN);
		expect(map['2026-05-06']['evening']).toEqual(EVENING_PUSHED);
	});

	it('returns empty map for empty array', () => {
		expect(buildServingMap([])).toEqual({});
	});

	it('handles multiple dates', () => {
		const s2 = makeServing({ id: 5, scheduled_date: '2026-05-07', slot: 'morning' });
		const map = buildServingMap([MORNING_TAKEN, s2]);
		expect(Object.keys(map)).toHaveLength(2);
	});
});

// ---------- cellStatus ----------

describe('cellStatus', () => {
	it('returns "both" when morning and evening are taken', () => {
		const map = buildServingMap([MORNING_TAKEN, EVENING_TAKEN]);
		expect(cellStatus(map, '2026-05-06')).toBe('both');
	});

	it('returns "partial" when only morning is taken', () => {
		const map = buildServingMap([MORNING_TAKEN, EVENING_PUSHED]);
		expect(cellStatus(map, '2026-05-06')).toBe('partial');
	});

	it('returns "partial" when only evening is taken', () => {
		const map = buildServingMap([MORNING_PUSHED, EVENING_TAKEN]);
		expect(cellStatus(map, '2026-05-06')).toBe('partial');
	});

	it('returns "pushed" when pushed but not taken', () => {
		const map = buildServingMap([MORNING_PUSHED]);
		expect(cellStatus(map, '2026-05-06')).toBe('pushed');
	});

	it('returns "none" when no servings', () => {
		const map = buildServingMap([]);
		expect(cellStatus(map, '2026-05-06')).toBe('none');
	});

	it('returns "none" for date not in map', () => {
		const map = buildServingMap([MORNING_TAKEN]);
		expect(cellStatus(map, '2026-05-07')).toBe('none');
	});
});

// ---------- dayServings ----------

describe('dayServings', () => {
	it('returns morning and evening servings for a date', () => {
		const map = buildServingMap([MORNING_TAKEN, EVENING_PUSHED]);
		const result = dayServings(map, '2026-05-06');
		expect(result.morning).toEqual(MORNING_TAKEN);
		expect(result.evening).toEqual(EVENING_PUSHED);
	});

	it('returns null for missing slot', () => {
		const map = buildServingMap([MORNING_TAKEN]);
		const result = dayServings(map, '2026-05-06');
		expect(result.morning).toEqual(MORNING_TAKEN);
		expect(result.evening).toBeNull();
	});

	it('returns both null for unknown date', () => {
		const map = buildServingMap([]);
		const result = dayServings(map, '2026-05-06');
		expect(result.morning).toBeNull();
		expect(result.evening).toBeNull();
	});
});

// ---------- formatLocalTime ----------

describe('formatLocalTime', () => {
	it('returns HH:MM from ISO string', () => {
		const result = formatLocalTime('2026-05-06T07:45:00');
		// システムのタイムゾーンに依存しないよう HH:MM 形式かだけ確認
		expect(result).toMatch(/^\d{2}:\d{2}$/);
	});

	it('returns null for null input', () => {
		expect(formatLocalTime(null)).toBeNull();
	});

	it('returns null for empty string', () => {
		expect(formatLocalTime('')).toBeNull();
	});
});

// ---------- monthRange ----------

describe('monthRange', () => {
	it('returns first and last day of month', () => {
		const { from, to } = monthRange(2026, 5);
		expect(from).toBe('2026-05-01');
		expect(to).toBe('2026-05-31');
	});

	it('handles February in non-leap year', () => {
		const { from, to } = monthRange(2025, 2);
		expect(from).toBe('2025-02-01');
		expect(to).toBe('2025-02-28');
	});

	it('handles February in leap year', () => {
		const { from, to } = monthRange(2024, 2);
		expect(from).toBe('2024-02-01');
		expect(to).toBe('2024-02-29');
	});

	it('handles December', () => {
		const { from, to } = monthRange(2026, 12);
		expect(from).toBe('2026-12-01');
		expect(to).toBe('2026-12-31');
	});
});
