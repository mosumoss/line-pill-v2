<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type TodaySlot, ApiError } from '$lib/api';
	import { appState } from '$lib/stores.svelte';

	let morning = $state<TodaySlot | null>(null);
	let evening = $state<TodaySlot | null>(null);
	let takingMorning = $state(false);
	let takingEvening = $state(false);
	let message = $state<{ text: string; type: 'success' | 'error' } | null>(null);

	const hasMorning = $derived(morning !== null);
	const hasEvening = $derived(evening !== null);
	const hasNothing = $derived(!hasMorning && !hasEvening);

	onMount(async () => {
		try {
			const today = await api.today();
			morning = today.morning;
			evening = today.evening;
		} catch {
			// レイアウトでエラー処理済みのためここでは無視
		}
	});

	async function handleTake(slot: 'morning' | 'evening') {
		const target = slot === 'morning' ? morning : evening;
		if (!target) return;

		if (slot === 'morning') takingMorning = true;
		else takingEvening = true;

		try {
			const updated = await api.takeMed(target.serving.id);
			if (slot === 'morning') morning = { ...target, serving: updated };
			else evening = { ...target, serving: updated };
			message = { text: `${slot === 'morning' ? '朝' : '夜'}の薬を記録しました 🎉`, type: 'success' };
		} catch (e) {
			if (e instanceof ApiError && e.status === 409) {
				message = { text: '既に記録済みです', type: 'error' };
			} else {
				message = { text: '記録に失敗しました', type: 'error' };
			}
		} finally {
			if (slot === 'morning') takingMorning = false;
			else takingEvening = false;
			setTimeout(() => (message = null), 3000);
		}
	}

	function btnLabel(slot: TodaySlot | null, kind: 'morning' | 'evening', taking: boolean): string {
		if (taking) return '記録中...';
		if (!slot) return '';
		if (slot.serving.taken_at) return '✅ 服用済み';
		return `💊 ${kind === 'morning' ? '朝' : '夜'}の薬を飲む`;
	}
</script>

<div class="today">
	<header>
		<h1>今日の服薬</h1>
		{#if appState.user?.display_name}
			<p class="greeting">{appState.user.display_name} さん</p>
		{/if}
	</header>

	{#if message}
		<div class="toast" class:success={message.type === 'success'} class:error={message.type === 'error'} role="status">
			{message.text}
		</div>
	{/if}

	{#if hasNothing}
		<div class="empty-state">
			<p>💡 まだ薬が登録されていません</p>
			<p class="empty-sub">設定画面から薬を選んで朝/夜のどちらかに登録してください。</p>
			<a href="/settings" class="empty-cta">設定へ</a>
		</div>
	{:else}
		<div class="cards">
			{#if morning}
				<div class="card" class:taken={morning.serving.taken_at}>
					<div class="card-header">
						<span class="slot-icon">🌅</span>
						<span class="slot-name">朝</span>
						{#if appState.settings?.morning_time}
							<span class="slot-time">{appState.settings.morning_time}</span>
						{/if}
					</div>
					<div class="med-list">
						{#each morning.medications as name}
							<span class="med-chip">{name}</span>
						{/each}
					</div>
					<button
						class="take-btn"
						disabled={!!morning.serving.taken_at || takingMorning}
						onclick={() => handleTake('morning')}
						aria-label="朝の薬を記録"
					>
						{btnLabel(morning, 'morning', takingMorning)}
					</button>
				</div>
			{/if}

			{#if evening}
				<div class="card" class:taken={evening.serving.taken_at}>
					<div class="card-header">
						<span class="slot-icon">🌙</span>
						<span class="slot-name">夜</span>
						{#if appState.settings?.evening_time}
							<span class="slot-time">{appState.settings.evening_time}</span>
						{/if}
					</div>
					<div class="med-list">
						{#each evening.medications as name}
							<span class="med-chip">{name}</span>
						{/each}
					</div>
					<button
						class="take-btn"
						disabled={!!evening.serving.taken_at || takingEvening}
						onclick={() => handleTake('evening')}
						aria-label="夜の薬を記録"
					>
						{btnLabel(evening, 'evening', takingEvening)}
					</button>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.today { padding: 1.5rem 1rem; }

	header { margin-bottom: 1.5rem; }

	h1 { font-size: 1.4rem; font-weight: 700; }

	.greeting { font-size: 0.9rem; color: #757575; margin-top: 0.25rem; }

	.toast {
		padding: 0.75rem 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
		font-size: 0.9rem;
		text-align: center;
	}
	.toast.success { background: #e8f5e9; color: #2e7d32; }
	.toast.error   { background: #ffebee; color: #c62828; }

	.cards { display: flex; flex-direction: column; gap: 1rem; }

	.card {
		background: #fff;
		border-radius: 12px;
		padding: 1.25rem;
		box-shadow: 0 1px 4px rgba(0,0,0,.08);
		transition: opacity 0.2s;
	}
	.card.taken { opacity: 0.6; }

	.card-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
	.slot-icon { font-size: 1.4rem; }
	.slot-name { font-size: 1.1rem; font-weight: 600; }
	.slot-time { margin-left: auto; font-size: 0.85rem; color: #9e9e9e; }

	.med-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 1rem;
	}
	.med-chip {
		display: inline-block;
		padding: 0.25rem 0.6rem;
		background: #f1f8e9;
		color: #33691e;
		border-radius: 12px;
		font-size: 0.8rem;
	}

	.take-btn {
		width: 100%;
		padding: 0.875rem;
		border: none;
		border-radius: 8px;
		background: #06c755;
		color: #fff;
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		transition: opacity 0.15s;
	}
	.take-btn:disabled { background: #bdbdbd; cursor: not-allowed; }

	.empty-state {
		background: #fff;
		border-radius: 12px;
		padding: 2rem 1.5rem;
		text-align: center;
		box-shadow: 0 1px 4px rgba(0,0,0,.08);
	}
	.empty-state p { margin-bottom: 0.5rem; }
	.empty-sub { font-size: 0.85rem; color: #757575; margin-bottom: 1.25rem !important; }
	.empty-cta {
		display: inline-block;
		padding: 0.6rem 1.5rem;
		background: #06c755;
		color: #fff;
		border-radius: 8px;
		text-decoration: none;
		font-size: 0.9rem;
		font-weight: 600;
	}
</style>
