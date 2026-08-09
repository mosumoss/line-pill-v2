<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import { initLiff } from '$lib/liff';
	import { loadConfig, getApiBase } from '$lib/config';
	import { appState } from '$lib/stores.svelte';

	let { children } = $props();
	let errorStep = $state<string>('');
	let errorDetail = $state<string>('');

	const tabs = [
		{ href: '/', label: '今日', icon: '💊' },
		{ href: '/calendar', label: 'カレンダー', icon: '📅' },
		{ href: '/settings', label: '設定', icon: '⚙️' },
		{ href: '/stats', label: '統計', icon: '📊' },
	];

	onMount(async () => {
		try {
			errorStep = 'config.json読込';
			await loadConfig();
			errorStep = 'LIFF初期化';
			await initLiff();
			errorStep = 'API疎通 (/api/me, /api/settings)';
			const [user, settings] = await Promise.all([api.me(), api.getSettings()]);
			appState.user = user;
			appState.settings = settings;
		} catch (e) {
			appState.error = e instanceof Error ? e.message : 'Unknown error';
			errorDetail = `step=${errorStep}\napiBase=${getApiBase() || '(empty)'}\nerr=${appState.error}`;
		} finally {
			appState.isLoading = false;
		}
	});

	function reload() {
		// キャッシュ含めてリロード
		location.reload();
	}
</script>

<div class="app">
	{#if appState.isLoading}
		<div class="loading" aria-label="読み込み中">
			<span>読み込み中...</span>
		</div>
	{:else if appState.error}
		<div class="error" role="alert">
			<p class="err-title">⚠️ エラー</p>
			<pre class="err-detail">{errorDetail}</pre>
			<button class="reload-btn" onclick={reload}>再試行</button>
		</div>
	{:else}
		{#if appState.deepLinkMessage}
			<div class="deeplink-toast" role="status">{appState.deepLinkMessage}</div>
		{/if}
		<main class="content">
			{@render children()}
		</main>

		<nav class="bottom-nav" aria-label="メインナビゲーション">
			{#each tabs as tab}
				<a
					href={tab.href}
					class="tab"
					class:active={$page.url.pathname === tab.href}
					aria-current={$page.url.pathname === tab.href ? 'page' : undefined}
				>
					<span class="tab-icon" aria-hidden="true">{tab.icon}</span>
					<span class="tab-label">{tab.label}</span>
				</a>
			{/each}
		</nav>
	{/if}
</div>

<style>
	:global(*) {
		box-sizing: border-box;
		margin: 0;
		padding: 0;
	}

	:global(body) {
		font-family: -apple-system, 'Hiragino Sans', sans-serif;
		background: #f5f5f5;
		color: #333;
		min-height: 100dvh;
	}

	.app {
		display: flex;
		flex-direction: column;
		min-height: 100dvh;
		max-width: 480px;
		margin: 0 auto;
	}

	.loading,
	.error {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100dvh;
		padding: 2rem;
		text-align: center;
	}

	.error {
		color: #e53935;
		flex-direction: column;
		gap: 1rem;
		padding: 1.5rem;
	}

	.err-title { font-weight: 700; font-size: 1.1rem; }

	.err-detail {
		font-family: ui-monospace, 'Menlo', monospace;
		font-size: 0.75rem;
		background: #fff3f3;
		border: 1px solid #ffcdd2;
		padding: 0.75rem;
		border-radius: 8px;
		max-width: 100%;
		white-space: pre-wrap;
		word-break: break-all;
		text-align: left;
		color: #424242;
	}

	.reload-btn {
		padding: 0.6rem 1.5rem;
		background: #06c755;
		color: #fff;
		border: none;
		border-radius: 8px;
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
	}

	.content {
		flex: 1;
		overflow-y: auto;
		padding-bottom: calc(64px + env(safe-area-inset-bottom));
	}

	.bottom-nav {
		position: fixed;
		bottom: 0;
		left: 50%;
		transform: translateX(-50%);
		width: 100%;
		max-width: 480px;
		display: flex;
		background: #fff;
		border-top: 1px solid #e0e0e0;
		height: calc(64px + env(safe-area-inset-bottom));
		padding-bottom: env(safe-area-inset-bottom);
	}

	.tab {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-decoration: none;
		color: #9e9e9e;
		font-size: 11px;
		gap: 2px;
		transition: color 0.15s;
	}

	.tab.active {
		color: #06c755; /* LINE green */
	}

	.tab-icon {
		font-size: 22px;
		line-height: 1;
	}

	.deeplink-toast {
		position: fixed;
		top: env(safe-area-inset-top, 0);
		left: 50%;
		transform: translateX(-50%);
		margin-top: 1rem;
		padding: 0.75rem 1.25rem;
		background: #06c755;
		color: #fff;
		border-radius: 24px;
		font-size: 0.9rem;
		font-weight: 600;
		box-shadow: 0 4px 12px rgba(0,0,0,.15);
		z-index: 100;
		max-width: calc(100% - 2rem);
		text-align: center;
	}
</style>
