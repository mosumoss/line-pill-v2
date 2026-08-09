<script lang="ts">
	import { api, type Medication, type UserMedication } from '$lib/api';
	import { appState } from '$lib/stores.svelte';
	import { onMount } from 'svelte';

	let presets = $state<Medication[]>([]);
	let morningMeds = $state<UserMedication[]>([]);
	let eveningMeds = $state<UserMedication[]>([]);

	let saving = $state(false);
	let message = $state<string | null>(null);

	// 通知時刻
	let morningTime = $state(appState.settings?.morning_time ?? '07:30');
	let eveningTime = $state(appState.settings?.evening_time ?? '22:00');
	let eveningEnabled = $state(appState.settings?.evening_enabled ?? true);

	// リマインダー設定
	let reminderMode = $state<'off' | 'interval' | 'fixed'>(appState.settings?.reminder_mode ?? 'off');
	let reminderIntervalHours = $state<number>(appState.settings?.reminder_interval_hours || 4);
	// 指定時刻モードは1つの HH:MM のみ受け付ける UI に簡略化（複数欲しくなったら CSV 入力可）
	let reminderTime = $state<string>(
		(appState.settings?.reminder_times ?? '').split(',')[0]?.trim() || '22:00',
	);

	onMount(async () => {
		[presets, morningMeds, eveningMeds] = await Promise.all([
			api.listMedications(),
			api.listUserMedications('morning'),
			api.listUserMedications('evening'),
		]);
	});

	async function saveSettings() {
		saving = true;
		try {
			const payload = {
				morning_time: morningTime,
				evening_time: eveningTime,
				evening_enabled: eveningEnabled,
				reminder_mode: reminderMode,
				reminder_interval_hours: reminderMode === 'interval' ? reminderIntervalHours : 0,
				reminder_times: reminderMode === 'fixed' ? reminderTime : '',
			} as const;
			const updated = await api.updateSettings(payload);
			appState.settings = updated;
			message = '設定を保存しました';
		} catch {
			message = '保存に失敗しました';
		} finally {
			saving = false;
			setTimeout(() => (message = null), 3000);
		}
	}

	function isMorningMed(medId: number) {
		return morningMeds.some((m) => m.medication_id === medId);
	}

	function isEveningMed(medId: number) {
		return eveningMeds.some((m) => m.medication_id === medId);
	}

	async function toggleMed(medId: number, slot: 'morning' | 'evening', enabled: boolean) {
		if (enabled) {
			await api.addUserMedication(medId, slot);
		} else {
			await api.removeUserMedication(medId, slot);
		}
		if (slot === 'morning') morningMeds = await api.listUserMedications('morning');
		else eveningMeds = await api.listUserMedications('evening');
	}
</script>

<div class="settings">
	<h1>設定</h1>

	{#if message}
		<div class="toast" role="status">{message}</div>
	{/if}

	<!-- 通知時刻 -->
	<section>
		<h2>通知時刻</h2>
		<div class="field">
			<label for="morning-time">朝</label>
			<input id="morning-time" type="time" bind:value={morningTime} />
		</div>
		<div class="field">
			<label for="evening-toggle">夜の通知</label>
			<input id="evening-toggle" type="checkbox" bind:checked={eveningEnabled} />
		</div>
		{#if eveningEnabled}
			<div class="field">
				<label for="evening-time">夜</label>
				<input id="evening-time" type="time" bind:value={eveningTime} />
			</div>
		{/if}
	</section>

	<!-- リマインダー -->
	<section>
		<h2>リマインダー</h2>
		<p class="section-hint">通知を見落としていた場合、再度お知らせします。</p>

		<label class="radio-row">
			<input type="radio" name="reminder-mode" value="off" bind:group={reminderMode} />
			<span>使わない</span>
		</label>

		<label class="radio-row">
			<input type="radio" name="reminder-mode" value="interval" bind:group={reminderMode} />
			<span class="radio-label-with-input">
				<span>未服用なら</span>
				<input
					type="number"
					min="1"
					max="24"
					bind:value={reminderIntervalHours}
					disabled={reminderMode !== 'interval'}
					aria-label="リマインダー間隔（時間）"
				/>
				<span>時間おきに通知</span>
			</span>
		</label>

		<label class="radio-row">
			<input type="radio" name="reminder-mode" value="fixed" bind:group={reminderMode} />
			<span class="radio-label-with-input">
				<span>未服用なら</span>
				<input
					type="time"
					bind:value={reminderTime}
					disabled={reminderMode !== 'fixed'}
					aria-label="リマインダー時刻"
				/>
				<span>に通知</span>
			</span>
		</label>
	</section>

	<!-- 保存ボタン -->
	<button class="save-btn" onclick={saveSettings} disabled={saving}>
		{saving ? '保存中...' : '保存する'}
	</button>

	<!-- 薬の選択 -->
	<section>
		<h2>薬の登録</h2>
		<div class="med-list">
			{#each presets as med}
				<div class="med-row">
					<span class="med-name">{med.name}</span>
					<label>
						<input
							type="checkbox"
							checked={isMorningMed(med.id)}
							onchange={(e) => toggleMed(med.id, 'morning', (e.target as HTMLInputElement).checked)}
						/>
						朝
					</label>
					{#if eveningEnabled}
						<label>
							<input
								type="checkbox"
								checked={isEveningMed(med.id)}
								onchange={(e) => toggleMed(med.id, 'evening', (e.target as HTMLInputElement).checked)}
							/>
							夜
						</label>
					{/if}
				</div>
			{/each}
		</div>
	</section>
</div>

<style>
	.settings { padding: 1.5rem 1rem; }

	h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 1.5rem; }

	section {
		background: #fff;
		border-radius: 12px;
		padding: 1.25rem;
		margin-bottom: 1rem;
		box-shadow: 0 1px 4px rgba(0,0,0,.08);
	}

	h2 { font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; color: #424242; }

	.section-hint { font-size: 0.78rem; color: #9e9e9e; margin-bottom: 0.75rem; }

	.field {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0;
		border-bottom: 1px solid #f5f5f5;
	}

	.field label { font-size: 0.95rem; }

	.field input[type="time"] {
		border: 1px solid #e0e0e0;
		border-radius: 6px;
		padding: 0.4rem 0.6rem;
		font-size: 0.95rem;
	}

	.radio-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0;
		font-size: 0.9rem;
		cursor: pointer;
	}
	.radio-row input[type="radio"] {
		margin: 0;
		accent-color: #06c755;
	}
	.radio-label-with-input {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
	}
	.radio-label-with-input input[type="number"] {
		width: 3.5rem;
		border: 1px solid #e0e0e0;
		border-radius: 6px;
		padding: 0.3rem 0.5rem;
		font-size: 0.9rem;
		text-align: center;
	}
	.radio-label-with-input input[type="time"] {
		border: 1px solid #e0e0e0;
		border-radius: 6px;
		padding: 0.3rem 0.5rem;
		font-size: 0.9rem;
	}
	.radio-label-with-input input:disabled {
		background: #f5f5f5;
		color: #bdbdbd;
	}

	.save-btn {
		display: block;
		width: 100%;
		margin: 0 0 1rem;
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		background: #06c755;
		color: #fff;
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
	}

	.save-btn:disabled { background: #bdbdbd; }

	.toast {
		background: #e8f5e9;
		color: #2e7d32;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
		text-align: center;
	}

	.med-list { display: flex; flex-direction: column; gap: 0.75rem; }

	.med-row {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.med-name { flex: 1; font-size: 0.95rem; }

	.med-row label {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.85rem;
		color: #616161;
	}
</style>
