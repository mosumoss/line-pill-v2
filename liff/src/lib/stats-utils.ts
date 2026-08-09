import type { Serving } from './api';

export function adherenceRate(servings: Serving[]): number | null {
	const pushed = servings.filter((s) => s.pushed_at !== null);
	if (pushed.length === 0) return null;
	const taken = pushed.filter((s) => s.taken_at !== null).length;
	return Math.round((taken / pushed.length) * 100);
}

function prevDay(dateStr: string): string {
	const [y, m, d] = dateStr.split('-').map(Number);
	const dt = new Date(y, m - 1, d - 1);
	return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
}

export function currentStreak(servings: Serving[], refDate: string): number {
	const takenDates = new Set(
		servings.filter((s) => s.taken_at !== null).map((s) => s.scheduled_date),
	);

	let streak = 0;
	let cursor = refDate;

	while (takenDates.has(cursor)) {
		streak++;
		cursor = prevDay(cursor);
	}

	return streak;
}

export function takenCount(servings: Serving[]): number {
	return servings.filter((s) => s.taken_at !== null).length;
}

export interface DayBar {
	date: string;
	taken: number;
	total: number;
}

export function dailyChart(servings: Serving[], days: number): DayBar[] {
	const today = new Date();
	const result: DayBar[] = [];

	for (let i = days - 1; i >= 0; i--) {
		const dt = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
		const dateStr = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
		const dayServings = servings.filter((s) => s.scheduled_date === dateStr);
		const pushed = dayServings.filter((s) => s.pushed_at !== null);
		result.push({
			date: dateStr,
			taken: pushed.filter((s) => s.taken_at !== null).length,
			total: pushed.length,
		});
	}

	return result;
}

// ---------- ヒートマップ用 ----------

export type DayStatus = 'full' | 'partial' | 'missed' | 'empty';

export interface HeatmapCell {
	date: string;
	dayOfWeek: number; // 0=日, 6=土
	status: DayStatus;
}

/**
 * 日別の服薬状況をステータス化する。
 * - full:    その日の全サーブ taken
 * - partial: 一部 taken (朝夜両方ある人で片方のみ)
 * - missed:  予定あり (serving 行あり) なのに 0 taken
 * - empty:   予定なし
 */
function dayStatus(servings: Serving[]): DayStatus {
	if (servings.length === 0) return 'empty';
	const taken = servings.filter((s) => s.taken_at !== null).length;
	if (taken === 0) return 'missed';
	if (taken === servings.length) return 'full';
	return 'partial';
}

/**
 * 過去 N 日分のヒートマップセルを「日付昇順」で返す。
 * UI 側で週単位に並べ替えれば GitHub 風のグリッドになる。
 */
export function buildHeatmap(servings: Serving[], days: number): HeatmapCell[] {
	const today = new Date();
	const cells: HeatmapCell[] = [];
	for (let i = days - 1; i >= 0; i--) {
		const dt = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
		const dateStr = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
		const dayServings = servings.filter((s) => s.scheduled_date === dateStr);
		cells.push({
			date: dateStr,
			dayOfWeek: dt.getDay(),
			status: dayStatus(dayServings),
		});
	}
	return cells;
}

/**
 * heatmap セル配列を週ごとにグループ化する。
 * 戻り値は週の配列で、各週は 7 要素 (日〜土、欠ける日は null)。
 * 最古の日が含まれる週から並ぶ。
 */
export function groupByWeek(cells: HeatmapCell[]): (HeatmapCell | null)[][] {
	if (cells.length === 0) return [];
	const weeks: (HeatmapCell | null)[][] = [];
	let currentWeek: (HeatmapCell | null)[] = new Array(7).fill(null);
	// 最初の週: 先頭セルの曜日まで null パディング
	const firstDow = cells[0].dayOfWeek;
	for (const cell of cells) {
		currentWeek[cell.dayOfWeek] = cell;
		if (cell.dayOfWeek === 6) {
			weeks.push(currentWeek);
			currentWeek = new Array(7).fill(null);
		}
	}
	// 最後の週が完了していなければ push
	if (currentWeek.some((c) => c !== null)) {
		weeks.push(currentWeek);
	}
	// 最初の週の冒頭 null は既に埋まっているので OK
	void firstDow;
	return weeks;
}
