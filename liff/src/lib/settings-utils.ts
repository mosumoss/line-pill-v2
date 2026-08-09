/**
 * 設定画面のバリデーション・差分計算ユーティリティ。
 */
import type { Settings } from './api';

const HHMM_RE = /^\d{2}:\d{2}$/;

/** HH:MM 形式かつ有効な時刻かチェック。 */
export function isValidHHMM(value: string): boolean {
	if (!HHMM_RE.test(value)) return false;
	const [h, m] = value.split(':').map(Number);
	return h >= 0 && h <= 23 && m >= 0 && m <= 59;
}

/**
 * original と edited を比較し、変更のあったフィールドだけを返す。
 * 時刻フィールドが不正な場合は Error をスローする。
 */
export function sanitizeSettings(
	original: Settings,
	edited: Settings,
): Partial<Settings> {
	// バリデーション先行
	for (const key of ['morning_time', 'evening_time'] as const) {
		if (edited[key] !== original[key] && !isValidHHMM(edited[key])) {
			throw new Error(`Invalid time format "${edited[key]}": expected HH:MM`);
		}
	}

	const diff: Partial<Settings> = {};
	for (const _key of Object.keys(original) as (keyof Settings)[]) {
		if (edited[_key] !== original[_key]) {
			(diff as Record<string, unknown>)[_key] = edited[_key];
		}
	}
	return diff;
}
