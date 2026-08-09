/**
 * アプリグローバル状態 (Svelte 5 runes — class fields)。
 *
 * クラスフィールドで $state を宣言するのが Svelte 5 の正しいパターン。
 * コンポーネントから `import { appState } from '$lib/stores.svelte'` で使う。
 */
import type { Settings, User } from './api';

class AppState {
	user: User | null = $state(null);
	settings: Settings | null = $state(null);
	isLoading: boolean = $state(true);
	error: string | null = $state(null);
	deepLinkMessage: string | null = $state(null);

	get isReady(): boolean {
		return !this.isLoading && this.user !== null;
	}

	reset(): void {
		this.user = null;
		this.settings = null;
		this.isLoading = true;
		this.error = null;
		this.deepLinkMessage = null;
	}
}

export const appState = new AppState();
