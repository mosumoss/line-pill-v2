<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type Serving } from '$lib/api';
	import {
		adherenceRate,
		currentStreak,
		takenCount,
		buildHeatmap,
		groupByWeek,
	} from '$lib/stats-utils';

	const PERIODS = [
		{ label: '7日', days: 7 },
		{ label: '30日', days: 30 },
		{ label: '90日', days: 90 },
	] as const;

	let period = $state<(typeof PERIODS)[number]>(PERIODS[2]); // デフォルト90日でヒートマップが映える
	let servings = $state<Serving[]>([]);
	let loading = $state(true);
	const todayStr = new Date().toLocaleDateString('sv', { timeZone: 'Asia/Tokyo' });

	const rate = $derived(adherenceRate(servings));
	const streak = $derived(currentStreak(servings, todayStr));
	const taken = $derived(takenCount(servings));
	const heatmapWeeks = $derived(groupByWeek(buildHeatmap(servings, period.days)));

	const DOW_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

	onMount(() => loadStats());

	async function loadStats() {
		loading = true;
		const to = new Date();
		const from = new Date(to);
		from.setDate(from.getDate() - period.days + 1);
		const toStr = to.toLocaleDateString('sv', { timeZone: 'Asia/Tokyo' });
		const fromStr = from.toLocaleDateString('sv', { timeZone: 'Asia/Tokyo' });
		try {
			servings = await api.listServings(fromStr, toStr);
		} finally {
			loading = false;
		}
	}

	async function changePeriod(p: (typeof PERIODS)[number]) {
		period = p;
		await loadStats();
	}
</script>

<div class="stats">
	<h1>統計</h1>

	<div class="period-tabs">
		{#each PERIODS as p}
			<button class="period-btn" class:active={period.days === p.days} onclick={() => changePeriod(p)}>
				{p.label}
			</button>
		{/each}
	</div>

	{#if loading}
		<p class="loading">読み込み中...</p>
	{:else}
		<div class="metrics">
			<div class="metric-card">
				<div class="metric-value">{rate !== null ? `${rate}%` : '—'}</div>
				<div class="metric-label">服薬率</div>
				{#if rate !== null}
					<div class="ring-track" style="--pct: {rate}"></div>
				{/if}
			</div>

			<div class="metric-card">
				<div class="metric-value">{streak} <small>日</small></div>
				<div class="metric-label">連続記録</div>
			</div>

			<div class="metric-card">
				<div class="metric-value">{taken}</div>
				<div class="metric-label">服用回数 ({period.label})</div>
			</div>
		</div>

		<!-- 服薬ヒートマップ -->
		<div class="chart-card">
			<h2>服薬カレンダーマップ</h2>
			<div class="heatmap-wrap">
				<div class="heatmap-dow">
					{#each DOW_LABELS as d, i}
						<span class:visible={i % 2 === 1}>{i % 2 === 1 ? d : ''}</span>
					{/each}
				</div>
				<div class="heatmap-grid">
					{#each heatmapWeeks as week}
						<div class="heatmap-week">
							{#each week as cell}
								{#if cell}
									<div
										class="heatmap-cell {cell.status}"
										class:today={cell.date === todayStr}
										title="{cell.date}: {cell.status === 'full' ? '服用済み' : cell.status === 'partial' ? '一部服用' : cell.status === 'missed' ? '未服用' : '予定なし'}"
									></div>
								{:else}
									<div class="heatmap-cell placeholder"></div>
								{/if}
							{/each}
						</div>
					{/each}
				</div>
			</div>
			<div class="legend">
				<div class="legend-item"><span class="dot empty"></span>予定なし</div>
				<div class="legend-item"><span class="dot missed"></span>未服用</div>
				<div class="legend-item"><span class="dot partial"></span>一部</div>
				<div class="legend-item"><span class="dot full"></span>服用済み</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.stats { padding: 1.5rem 1rem; }

	h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 1.25rem; }

	.period-tabs {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.25rem;
	}

	.period-btn {
		flex: 1;
		padding: 0.5rem;
		border: 1px solid #e0e0e0;
		border-radius: 20px;
		background: #fff;
		font-size: 0.85rem;
		cursor: pointer;
	}

	.period-btn.active {
		background: #06c755;
		color: #fff;
		border-color: #06c755;
	}

	.metrics {
		display: flex;
		gap: 0.75rem;
		margin-bottom: 1rem;
		flex-wrap: wrap;
	}

	.metric-card {
		flex: 1;
		min-width: 90px;
		background: #fff;
		border-radius: 12px;
		padding: 1rem;
		text-align: center;
		box-shadow: 0 1px 4px rgba(0,0,0,.08);
	}

	.metric-value {
		font-size: 1.8rem;
		font-weight: 700;
		color: #06c755;
		line-height: 1;
		margin-bottom: 0.25rem;
	}

	.metric-value small { font-size: 1rem; }

	.metric-label { font-size: 0.75rem; color: #9e9e9e; }

	.ring-track {
		width: 50px;
		height: 50px;
		margin: 0.5rem auto 0;
		border-radius: 50%;
		background: conic-gradient(#06c755 calc(var(--pct) * 1%), #e0e0e0 0);
	}

	.loading { text-align: center; padding: 2rem; color: #9e9e9e; }

	/* --- ヒートマップ --- */
	.chart-card {
		background: #fff;
		border-radius: 12px;
		padding: 1rem;
		box-shadow: 0 1px 4px rgba(0,0,0,.08);
		margin-bottom: 1rem;
	}

	h2 { font-size: 0.9rem; font-weight: 600; color: #616161; margin-bottom: 0.75rem; }

	.heatmap-wrap {
		display: flex;
		gap: 6px;
		overflow-x: auto;
		padding-bottom: 4px;
	}

	.heatmap-dow {
		display: grid;
		grid-template-rows: repeat(7, 1fr);
		gap: 3px;
		font-size: 0.6rem;
		color: #9e9e9e;
		flex-shrink: 0;
	}
	.heatmap-dow span {
		height: 14px;
		display: flex;
		align-items: center;
		visibility: hidden;
	}
	.heatmap-dow span.visible { visibility: visible; }

	.heatmap-grid {
		display: flex;
		gap: 3px;
	}

	.heatmap-week {
		display: grid;
		grid-template-rows: repeat(7, 1fr);
		gap: 3px;
	}

	.heatmap-cell {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		background: #ebedf0;
	}
	.heatmap-cell.placeholder { background: transparent; }
	.heatmap-cell.empty   { background: #ebedf0; }
	.heatmap-cell.missed  { background: #ffcdd2; }
	.heatmap-cell.partial { background: #a5d6a7; }
	.heatmap-cell.full    { background: #06c755; }
	.heatmap-cell.today {
		outline: 2px solid #1976d2;
		outline-offset: 1px;
	}

	.legend {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-top: 0.75rem;
		font-size: 0.7rem;
		color: #757575;
	}
	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	.legend-item .dot {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 2px;
	}
	.legend-item .dot.empty   { background: #ebedf0; }
	.legend-item .dot.missed  { background: #ffcdd2; }
	.legend-item .dot.partial { background: #a5d6a7; }
	.legend-item .dot.full    { background: #06c755; }
</style>
