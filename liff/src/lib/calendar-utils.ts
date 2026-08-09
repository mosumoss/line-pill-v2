/**
 * カレンダー画面のピュア計算ユーティリティ。
 * 副作用なし・DOM不依存のため Vitest でテスト可能。
 */
import type { Serving } from './api';

export type ServingMap = Record<string, Record<string, Serving>>;
export type CellStatus = 'both' | 'partial' | 'pushed' | 'none';

export interface DayServings {
	morning: Serving | null;
	evening: Serving | null;
}

/** servings 配列を { date → { slot → Serving } } にインデックス化する。 */
export function buildServingMap(servings: Serving[]): ServingMap {
	const map: ServingMap = {};
	for (const s of servings) {
		if (!map[s.scheduled_date]) map[s.scheduled_date] = {};
		map[s.scheduled_date][s.slot] = s;
	}
	return map;
}

/** 日付セルの表示ステータスを返す。
 *
 * 判定ロジック: その日に存在する serving 行（朝のみ・夜のみ・両方）を見て
 * - すべて服用済み → 'both' (○)
 * - 一部のみ服用 → 'partial' (△)
 * - 通知のみ未服用 → 'pushed'
 * - 行なし → 'none'
 *
 * 例: 朝の薬しか登録していないユーザーは、朝が taken_at されれば 'both' になる。
 */
export function cellStatus(map: ServingMap, dateStr: string): CellStatus {
	const day = map[dateStr];
	if (!day) return 'none';
	const slots = Object.values(day);
	if (slots.length === 0) return 'none';
	const allTaken = slots.every((s) => s.taken_at !== null);
	const anyTaken = slots.some((s) => s.taken_at !== null);
	const anyPushed = slots.some((s) => s.pushed_at !== null);
	if (allTaken) return 'both';
	if (anyTaken) return 'partial';
	if (anyPushed) return 'pushed';
	return 'none';
}

/** 特定日の朝/夜 Serving を返す (存在しなければ null)。 */
export function dayServings(map: ServingMap, dateStr: string): DayServings {
	const day = map[dateStr] ?? {};
	return {
		morning: day['morning'] ?? null,
		evening: day['evening'] ?? null,
	};
}

/**
 * SQLite が保存する "YYYY-MM-DD HH:MM:SS" は UTC を想定している。
 * このまま new Date() に渡すとブラウザ実装によりローカル時刻と誤解釈される
 * ので、明示的に UTC として解釈させる。
 */
function parseAsUTC(iso: string): Date {
	// 既に T 区切り + タイムゾーン情報を含む場合はそのまま
	if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso)) {
		return new Date(iso);
	}
	// "YYYY-MM-DD HH:MM:SS" や "YYYY-MM-DDTHH:MM:SS" を UTC として解釈
	const normalized = iso.replace(' ', 'T') + 'Z';
	return new Date(normalized);
}

/**
 * 日時文字列を JST の "HH:MM" にフォーマットする。
 * null / 空文字は null を返す。
 */
export function formatLocalTime(iso: string | null | undefined): string | null {
	if (!iso) return null;
	const d = parseAsUTC(iso);
	if (isNaN(d.getTime())) return null;
	return d.toLocaleTimeString('ja-JP', {
		hour: '2-digit',
		minute: '2-digit',
		hour12: false,
		timeZone: 'Asia/Tokyo',
	});
}

/** JST での今日の日付文字列 (YYYY-MM-DD) を返す。 */
export function todayJST(): string {
	return new Date().toLocaleDateString('sv', { timeZone: 'Asia/Tokyo' });
}

/** 月の from/to 日付文字列 (YYYY-MM-DD) を返す。 */
export function monthRange(year: number, month: number): { from: string; to: string } {
	const pad = (n: number) => String(n).padStart(2, '0');
	const lastDay = new Date(year, month, 0).getDate();
	return {
		from: `${year}-${pad(month)}-01`,
		to: `${year}-${pad(month)}-${pad(lastDay)}`,
	};
}
