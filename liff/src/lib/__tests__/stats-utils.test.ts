/**
 * lib/stats-utils.ts のユニットテスト。
 */
import { describe, expect, it } from 'vitest';
import { adherenceRate, currentStreak, takenCount } from '../stats-utils';
import type { Serving } from '../api';

function makeServing(date: string, slot: 'morning' | 'evening', taken: boolean): Serving {
	return {
		id: Math.random(),
		scheduled_date: date,
		slot,
		taken_at: taken ? `${date}T07:45:00` : null,
		pushed_at: `${date}T07:30:00`,
	};
}

// ---------- adherenceRate ----------

describe('adherenceRate', () => {
	it('returns 100 when all pushed servings are taken', () => {
		const servings = [
			makeServing('2026-05-01', 'morning', true),
			makeServing('2026-05-02', 'morning', true),
		];
		expect(adherenceRate(servings)).toBe(100);
	});

	it('returns 50 when half taken', () => {
		const servings = [
			makeServing('2026-05-01', 'morning', true),
			makeServing('2026-05-02', 'morning', false),
		];
		expect(adherenceRate(servings)).toBe(50);
	});

	it('returns null when no pushed servings', () => {
		const servings: Serving[] = [
			{ id: 1, scheduled_date: '2026-05-01', slot: 'morning', taken_at: null, pushed_at: null },
		];
		expect(adherenceRate(servings)).toBeNull();
	});

	it('returns null for empty array', () => {
		expect(adherenceRate([])).toBeNull();
	});

	it('ignores servings without pushed_at', () => {
		const servings: Serving[] = [
			makeServing('2026-05-01', 'morning', true),
			{ id: 99, scheduled_date: '2026-05-02', slot: 'morning', taken_at: null, pushed_at: null },
		];
		expect(adherenceRate(servings)).toBe(100);
	});
});

// ---------- currentStreak ----------

describe('currentStreak', () => {
	it('returns 0 for no taken servings', () => {
		const servings = [makeServing('2026-05-01', 'morning', false)];
		expect(currentStreak(servings, '2026-05-06')).toBe(0);
	});

	it('counts consecutive taken days ending on reference date', () => {
		const servings = [
			makeServing('2026-05-04', 'morning', true),
			makeServing('2026-05-05', 'morning', true),
			makeServing('2026-05-06', 'morning', true),
		];
		expect(currentStreak(servings, '2026-05-06')).toBe(3);
	});

	it('breaks streak on missing day', () => {
		const servings = [
			makeServing('2026-05-03', 'morning', true),
			// 2026-05-04 なし (gap)
			makeServing('2026-05-05', 'morning', true),
			makeServing('2026-05-06', 'morning', true),
		];
		expect(currentStreak(servings, '2026-05-06')).toBe(2);
	});
});

// ---------- takenCount ----------

describe('takenCount', () => {
	it('returns count of taken servings', () => {
		const servings = [
			makeServing('2026-05-01', 'morning', true),
			makeServing('2026-05-01', 'evening', false),
			makeServing('2026-05-02', 'morning', true),
		];
		expect(takenCount(servings)).toBe(2);
	});

	it('returns 0 when none taken', () => {
		const servings = [makeServing('2026-05-01', 'morning', false)];
		expect(takenCount(servings)).toBe(0);
	});

	it('returns 0 for empty array', () => {
		expect(takenCount([])).toBe(0);
	});
});
