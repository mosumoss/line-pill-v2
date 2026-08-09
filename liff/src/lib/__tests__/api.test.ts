/**
 * lib/api.ts のユニットテスト。
 * fetch をモックして API クライアントの動作を検証する。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../api';

// LIFF モジュールをモック (ID token を直接返す)
vi.mock('../liff', () => ({
	getIdToken: vi.fn().mockResolvedValue('test-id-token-xyz'),
}));

const API_BASE = 'http://localhost:8000';

// 環境変数
vi.stubEnv('VITE_API_BASE', API_BASE);

// fetchモック
function mockFetch(status: number, body: unknown): void {
	global.fetch = vi.fn().mockResolvedValue({
		ok: status >= 200 && status < 300,
		status,
		json: () => Promise.resolve(body),
		statusText: status === 200 ? 'OK' : 'Error',
	} as Response);
}

beforeEach(() => {
	vi.clearAllMocks();
});

// ---------- /api/me ----------

describe('api.me', () => {
	it('returns user on 200', async () => {
		const fakeUser = { id: 1, line_user_id: 'U_001', display_name: null, role: 'user' };
		mockFetch(200, fakeUser);

		const result = await api.me();
		expect(result.id).toBe(1);
		expect(result.line_user_id).toBe('U_001');
	});

	it('sends Authorization header with Bearer token', async () => {
		mockFetch(200, { id: 1, line_user_id: 'U_001', display_name: null, role: 'user' });

		await api.me();

		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('/api/me'),
			expect.objectContaining({
				headers: expect.objectContaining({
					Authorization: 'Bearer test-id-token-xyz',
				}),
			}),
		);
	});

	it('throws ApiError on 401', async () => {
		mockFetch(401, { detail: 'Invalid token' });

		await expect(api.me()).rejects.toBeInstanceOf(ApiError);
	});

	it('ApiError contains status code', async () => {
		mockFetch(404, { detail: 'Not found' });

		try {
			await api.me();
		} catch (e) {
			expect(e).toBeInstanceOf(ApiError);
			expect((e as ApiError).status).toBe(404);
		}
	});
});

// ---------- /api/settings ----------

describe('api.getSettings', () => {
	it('returns settings on 200', async () => {
		const fakeSettings = {
			morning_time: '07:30',
			evening_time: '22:00',
			evening_enabled: true,
			timezone: 'Asia/Tokyo',
		};
		mockFetch(200, fakeSettings);

		const result = await api.getSettings();
		expect(result.morning_time).toBe('07:30');
		expect(result.evening_enabled).toBe(true);
	});
});

describe('api.updateSettings', () => {
	it('sends PATCH with partial settings', async () => {
		const updated = { morning_time: '08:00', evening_time: '22:00', evening_enabled: true, timezone: 'Asia/Tokyo' };
		mockFetch(200, updated);

		const result = await api.updateSettings({ morning_time: '08:00' });
		expect(result.morning_time).toBe('08:00');

		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('/api/settings'),
			expect.objectContaining({ method: 'PATCH' }),
		);
	});
});

// ---------- /api/medications ----------

describe('api.listMedications', () => {
	it('returns preset medications', async () => {
		const fakeMeds = [
			{ id: 1, name: 'ミノキシジル外用', kind: 'topical', is_preset: true },
			{ id: 2, name: 'フィナステリド', kind: 'oral', is_preset: true },
		];
		mockFetch(200, fakeMeds);

		const result = await api.listMedications();
		expect(result).toHaveLength(2);
		expect(result[0].name).toBe('ミノキシジル外用');
	});
});

// ---------- /api/user-medications ----------

describe('api.listUserMedications', () => {
	it('appends slot query param', async () => {
		mockFetch(200, []);

		await api.listUserMedications('morning');

		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('slot=morning'),
			expect.anything(),
		);
	});
});

describe('api.addUserMedication', () => {
	it('sends POST with medication_id and slot', async () => {
		mockFetch(201, { id: 1, medication_id: 2, slot: 'morning' });

		const result = await api.addUserMedication(2, 'morning');
		expect(result.medication_id).toBe(2);
		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('/api/user-medications'),
			expect.objectContaining({ method: 'POST' }),
		);
	});
});

// ---------- /api/today ----------

describe('api.today', () => {
	it('returns morning and evening servings', async () => {
		const fakeToday = {
			morning: { id: 1, scheduled_date: '2026-05-06', slot: 'morning', taken_at: null, pushed_at: null },
			evening: { id: 2, scheduled_date: '2026-05-06', slot: 'evening', taken_at: null, pushed_at: null },
		};
		mockFetch(200, fakeToday);

		const result = await api.today();
		expect(result.morning.slot).toBe('morning');
		expect(result.evening.slot).toBe('evening');
		expect(result.morning.taken_at).toBeNull();
	});
});

describe('api.takeMed', () => {
	it('sends POST to servings/:id/take', async () => {
		const fakeTaken = { id: 1, scheduled_date: '2026-05-06', slot: 'morning', taken_at: '2026-05-06T07:45:00', pushed_at: '2026-05-06T07:30:00' };
		mockFetch(200, fakeTaken);

		const result = await api.takeMed(1);
		expect(result.taken_at).not.toBeNull();
		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('/api/servings/1/take'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('throws ApiError 409 when already taken', async () => {
		mockFetch(409, { detail: 'Already taken' });

		await expect(api.takeMed(1)).rejects.toBeInstanceOf(ApiError);
		try {
			await api.takeMed(1);
		} catch (e) {
			expect((e as ApiError).status).toBe(409);
		}
	});
});

// ---------- /api/servings ----------

describe('api.listServings', () => {
	it('sends from_date and to_date params', async () => {
		mockFetch(200, []);

		await api.listServings('2026-05-01', '2026-05-07');

		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('from_date=2026-05-01'),
			expect.anything(),
		);
		expect(global.fetch).toHaveBeenCalledWith(
			expect.stringContaining('to_date=2026-05-07'),
			expect.anything(),
		);
	});
});

// ---------- ApiError ----------

describe('ApiError', () => {
	it('is instance of Error', () => {
		const err = new ApiError(404, 'Not found');
		expect(err).toBeInstanceOf(Error);
	});

	it('has correct name', () => {
		const err = new ApiError(500, 'Server error');
		expect(err.name).toBe('ApiError');
	});
});
