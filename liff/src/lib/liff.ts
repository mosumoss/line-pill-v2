/**
 * LIFF SDK 初期化・認証ヘルパー。
 *
 * LINE WebView 内で動作し、自動ログイン → ID token を提供する。
 * VITE_LIFF_MOCK=true のとき mock モードで動作 (開発・テスト用)。
 */
import type { Liff } from '@line/liff';

const LIFF_ID = import.meta.env.VITE_LIFF_ID as string;
const IS_MOCK = import.meta.env.VITE_LIFF_MOCK === 'true';

let _liff: Liff | null = null;
let _initialized = false;

async function getLiff(): Promise<Liff> {
	if (_liff) return _liff;
	const mod = await import('@line/liff');
	_liff = mod.default;
	return _liff;
}

export async function initLiff(): Promise<void> {
	if (_initialized) return;
	if (IS_MOCK) {
		_initialized = true;
		return;
	}
	const liff = await getLiff();
	await liff.init({ liffId: LIFF_ID });
	_initialized = true;
	if (!liff.isLoggedIn()) {
		liff.login();
	}
}

export async function getIdToken(): Promise<string> {
	if (IS_MOCK) {
		return import.meta.env.VITE_MOCK_ID_TOKEN ?? 'mock-id-token';
	}
	if (!_initialized) await initLiff();
	const liff = await getLiff();
	const token = liff.getIDToken();
	if (!token) throw new Error('LIFF ID token is not available. Ensure liff.init() has completed.');
	return token;
}

export async function getProfile() {
	if (IS_MOCK) {
		return { userId: 'Umock001', displayName: 'Mock User', pictureUrl: undefined };
	}
	const liff = await getLiff();
	return liff.getProfile();
}

export function closeLiff(): void {
	if (IS_MOCK) return;
	getLiff().then((liff) => liff.closeWindow());
}

/** テスト用: 初期化状態をリセット */
export function _resetForTest(): void {
	_initialized = false;
	_liff = null;
}
