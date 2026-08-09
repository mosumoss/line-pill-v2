<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Serving } from '$lib/api';
	import { appState } from '$lib/stores.svelte';
	import {
		buildServingMap,
		cellStatus,
		dayServings,
		formatLocalTime,
		monthRange,
		todayJST,
		type ServingMap,
	} from '$lib/calendar-utils';

	// JST で今日の日付を取得 (LINE WebView がUTCで動く環境に備えて明示)
	const todayStr = todayJST();
	const [todayY, todayM] = todayStr.split('-').map(Number);

	let year = $state(todayY);
	let month = $state(todayM);

	let servings = $state<Serving[]>([]);
	let loading = $state(true);
	let servingMap = $state<ServingMap>({});

	// ドロワー: 開いた瞬間は今日の情報を表示
	let drawerDate = $state<string | null>(todayStr);
	const drawerServings = $derived(drawerDate ? dayServings(servingMap, drawerDate) : null);
	// 表示する slot 行のリスト (serving が存在するものだけ)
	const drawerRows = $derived(
		drawerServings
			? [
					{ slot: 'morning', label: '朝 🌅', serving: drawerServings.morning },
					{ slot: 'evening', label: '夜 🌙', serving: drawerServings.evening },
				].filter((r): r is { slot: string; label: string; serving: Serving } => r.serving !== null)
			: [],
	);

	const monthStr = $derived(`${year}-${String(month).padStart(2, '0')}`);
	const daysInMonth = $derived(new Date(year, month, 0).getDate());
	const firstDayOfWeek = $derived(new Date(year, month - 1, 1).getDay());
	const isCurrentMonth = $derived(year === todayY && month === todayM);

	onMount(loadServings);

	async function loadServings() {
		loading = true;
		// 月が変わったら drawer を閉じるが、現在月なら今日に設定
		drawerDate = isCurrentMonth ? todayStr : null;
		try {
			const { from, to } = monthRange(year, month);
			servings = await api.listServings(from, to);
			servingMap = buildServingMap(servings);
		} finally {
			loading = false;
		}
	}

	function prevMonth() {
		if (month === 1) { year--; month = 12; } else month--;
		loadServings();
	}

	function nextMonth() {
		if (month === 12) { year++; month = 1; } else month++;
		loadServings();
	}

	function tapCell(dateStr: string) {
		drawerDate = drawerDate === dateStr ? null : dateStr;
	}

	function formatDate(dateStr: string) {
		const d = new Date(dateStr + 'T00:00:00');
		return `${d.getMonth() + 1}月${d.getDate()}日`;
	}

	const STATUS_ICON: Record<string, string> = {
		both: '✅',
		partial: '△',
		pushed: '📨',
		none: '',
	};
</script>

<div class="calendar">
	<header>
		<button onclick={prevMonth} aria-label="前月">‹</button>
		<h1>{year}年 {month}月</h1>
		<button onclick={nextMonth} aria-label="翌月">›</button>
	</header>

	<div class="weekdays">
		{#each ['日','月','火','水','木','金','土'] as d}
			<span>{d}</span>
		{/each}
	</div>

	{#if loading}
		<p class="loading">読み込み中...</p>
	{:else}
		<div class="grid">
			{#each Array(firstDayOfWeek) as _}
				<div class="cell empty"></div>
			{/each}
			{#each Array(daysInMonth) as _, i}
				{@const day = i + 1}
				{@const dateStr = `${monthStr}-${String(day).padStart(2, '0')}`}
				{@const st = cellStatus(servingMap, dateStr)}
				<button
					class="cell"
					class:both={st === 'both'}
					class:partial={st === 'partial'}
					class:today-cell={dateStr === todayStr}
					class:selected={drawerDate === dateStr}
					onclick={() => tapCell(dateStr)}
					aria-label="{day}日 {st}"
					aria-expanded={drawerDate === dateStr}
				>
					<span class="day-num">{day}</span>
					{#if STATUS_ICON[st]}
						<span class="dot" aria-hidden="true">{STATUS_ICON[st]}</span>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>

<!-- 日タップ ドロワー -->
{#if drawerDate && drawerServings}
	<div class="drawer" role="region" aria-label="{formatDate(drawerDate)}の服薬詳細">
		<div class="drawer-header">
			<span class="drawer-title">{formatDate(drawerDate)}</span>
			<button class="close-btn" onclick={() => (drawerDate = null)} aria-label="閉じる">✕</button>
		</div>

		{#if drawerRows.length === 0}
			<div class="drawer-row">
				<div class="drawer-status"><span class="badge none">— この日の服薬予定はありません</span></div>
			</div>
		{:else}
			{#each drawerRows as row}
				<div class="drawer-row">
					<div class="drawer-slot-label">{row.label}</div>
					<div class="drawer-status">
						{#if row.serving.taken_at}
							<span class="badge taken">✅ 服用済み</span>
							<span class="time">{formatLocalTime(row.serving.taken_at)}</span>
						{:else if row.serving.pushed_at}
							<span class="badge pushed">📨 通知済み・未服用</span>
						{:else}
							<span class="badge miss">— 記録なし</span>
						{/if}
					</div>
					{#if row.serving.pushed_at}
						<div class="drawer-sub">通知: {formatLocalTime(row.serving.pushed_at)}</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
{/if}

<style>
	.calendar { padding: 1rem; padding-bottom: 0; }

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}
	header button {
		border: none; background: none;
		font-size: 1.5rem; cursor: pointer;
		padding: 0.25rem 0.5rem; color: #06c755;
	}
	h1 { font-size: 1.1rem; font-weight: 700; }

	.weekdays {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		text-align: center;
		font-size: 0.72rem;
		color: #9e9e9e;
		margin-bottom: 0.25rem;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		gap: 2px;
	}

	.cell {
		aspect-ratio: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 3px;
		border-radius: 6px;
		font-size: 0.8rem;
		background: #fff;
		border: 1px solid transparent;
		cursor: pointer;
		padding: 0;
		transition: background 0.1s;
	}
	.cell.empty { background: transparent; border: none; cursor: default; }
	.cell.today-cell { border-color: #06c755; }
	.cell.both { background: #e8f5e9; }
	.cell.partial { background: #fff8e1; }
	.cell.selected { border-color: #1976d2; background: #e3f2fd; }

	.day-num { font-size: 0.72rem; line-height: 1; }
	.dot { font-size: 0.85rem; line-height: 1; }

	.loading { text-align: center; padding: 2rem; color: #9e9e9e; }

	/* ---- ドロワー ---- */
	.drawer {
		position: sticky;
		bottom: calc(64px + env(safe-area-inset-bottom));
		background: #fff;
		border-top: 1px solid #e0e0e0;
		border-radius: 16px 16px 0 0;
		padding: 1rem;
		box-shadow: 0 -4px 12px rgba(0,0,0,.1);
		margin-top: 0.5rem;
	}

	.drawer-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}
	.drawer-title { font-weight: 700; font-size: 1rem; }
	.close-btn {
		border: none; background: none;
		font-size: 1rem; cursor: pointer; color: #9e9e9e;
	}

	.drawer-row {
		padding: 0.625rem 0;
		border-bottom: 1px solid #f5f5f5;
	}
	.drawer-row:last-child { border-bottom: none; }

	.drawer-slot-label { font-size: 0.85rem; font-weight: 600; margin-bottom: 0.25rem; }

	.drawer-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.badge {
		font-size: 0.8rem;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}
	.badge.taken  { background: #e8f5e9; color: #2e7d32; }
	.badge.pushed { background: #fff3e0; color: #e65100; }
	.badge.miss   { background: #ffebee; color: #c62828; }
	.badge.none   { background: #f5f5f5; color: #9e9e9e; }
	.badge.off    { background: #f5f5f5; color: #bdbdbd; }

	.time { font-size: 0.85rem; color: #424242; font-weight: 600; }

	.drawer-sub { font-size: 0.75rem; color: #9e9e9e; margin-top: 0.2rem; }
</style>
