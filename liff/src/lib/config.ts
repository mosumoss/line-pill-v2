let _apiBase: string | null = null;

export async function loadConfig(): Promise<void> {
	if (_apiBase !== null) return;
	// キャッシュバスター: LINE WebView は config.json を強くキャッシュするため
	const url = `/config.json?t=${Date.now()}`;
	const res = await fetch(url, { cache: 'no-store' });
	if (!res.ok) {
		throw new Error(`config.json fetch failed: ${res.status}`);
	}
	const data = await res.json();
	if (!data.apiBase) {
		throw new Error('config.json: apiBase missing');
	}
	_apiBase = data.apiBase;
}

export function getApiBase(): string {
	return _apiBase ?? import.meta.env.VITE_API_BASE ?? '';
}
