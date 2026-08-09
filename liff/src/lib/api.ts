/**
 * FastAPI バックエンドへの API クライアント。
 *
 * 全リクエストに Authorization: Bearer <id_token> を付与。
 * エラー時は ApiError をスローする。
 */
import { getIdToken } from './liff';
import { getApiBase } from './config';

// ---------- エラークラス ----------

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		message: string,
	) {
		super(message);
		this.name = 'ApiError';
	}
}

// ---------- 型定義 ----------

export interface User {
	id: number;
	line_user_id: string;
	display_name: string | null;
	role: string;
}

export interface Settings {
	morning_time: string;
	evening_time: string;
	evening_enabled: boolean;
	timezone: string;
	reminder_mode: 'off' | 'interval' | 'fixed';
	reminder_interval_hours: number;
	reminder_times: string; // CSV "HH:MM,HH:MM"
}

export interface Medication {
	id: number;
	name: string;
	kind: string;
	is_preset: boolean;
}

export interface UserMedication {
	id: number;
	medication_id: number;
	slot: string;
}

export interface Serving {
	id: number;
	scheduled_date: string;
	slot: string;
	taken_at: string | null;
	pushed_at: string | null;
}

export interface TodaySlot {
	serving: Serving;
	medications: string[];
}

export interface TodayResponse {
	morning: TodaySlot | null;
	evening: TodaySlot | null;
}

// ---------- 内部ヘルパー ----------

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
	const token = await getIdToken();
	const response = await fetch(`${getApiBase()}${path}`, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`,
			...(options.headers as Record<string, string> | undefined),
		},
	});

	if (!response.ok) {
		const body = await response.json().catch(() => ({ detail: response.statusText }));
		throw new ApiError(response.status, (body as { detail?: string }).detail ?? 'Unknown error');
	}

	// 204 No Content
	if (response.status === 204) return undefined as T;
	return response.json() as Promise<T>;
}

// ---------- 公開 API ----------

export const api = {
	// ユーザー
	me: () => request<User>('/api/me'),

	// 設定
	getSettings: () => request<Settings>('/api/settings'),
	updateSettings: (data: Partial<Settings>) =>
		request<Settings>('/api/settings', {
			method: 'PATCH',
			body: JSON.stringify(data),
		}),

	// 薬マスタ
	listMedications: () => request<Medication[]>('/api/medications'),

	// ユーザー薬
	listUserMedications: (slot: 'morning' | 'evening') =>
		request<UserMedication[]>(`/api/user-medications?slot=${slot}`),
	addUserMedication: (medication_id: number, slot: 'morning' | 'evening') =>
		request<UserMedication>('/api/user-medications', {
			method: 'POST',
			body: JSON.stringify({ medication_id, slot }),
		}),
	removeUserMedication: (medication_id: number, slot: 'morning' | 'evening') =>
		request<void>(`/api/user-medications/${medication_id}?slot=${slot}`, {
			method: 'DELETE',
		}),

	// 今日の服薬
	today: () => request<TodayResponse>('/api/today'),
	takeMed: (serving_id: number) =>
		request<Serving>(`/api/servings/${serving_id}/take`, { method: 'POST' }),

	// 服薬履歴
	listServings: (from_date: string, to_date: string) =>
		request<Serving[]>(`/api/servings?from_date=${from_date}&to_date=${to_date}`),
};
