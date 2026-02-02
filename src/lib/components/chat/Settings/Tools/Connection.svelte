<script lang="ts">
	import { getContext, tick } from 'svelte';
	const i18n = getContext('i18n');

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import AddToolServerModal from '$lib/components/AddToolServerModal.svelte';
	import WrenchAlt from '$lib/components/icons/WrenchAlt.svelte';

	export let onDelete = () => {};
	export let onSubmit = () => {};

	export let connection = null;
	export let direct = false;

	let showConfigModal = false;
	let showDeleteConfirmDialog = false;
</script>

<AddToolServerModal
	edit
	{direct}
	bind:show={showConfigModal}
	{connection}
	onDelete={() => {
		showDeleteConfirmDialog = true;
	}}
	onSubmit={(c) => {
		connection = c;
		onSubmit(c);
	}}
/>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		onDelete();
		showConfigModal = false;
	}}
/>

<div class="flex w-full gap-2 items-center">
	<Tooltip className="w-full relative" content={''} placement="top-start">
		<div class="flex w-full">
			<div
				class="flex-1 relative flex gap-1.5 items-center {!(connection?.config?.enable ?? true)
					? 'opacity-50'
					: ''}"
			>
				<Tooltip content={connection?.type === 'mcp' ? $i18n.t('MCP') : $i18n.t('OpenAPI')}>
					<WrenchAlt />
				</Tooltip>

				<span
					class="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0 {connection?.type === 'mcp'
						? 'bg-purple-500/20 text-purple-700 dark:text-purple-300'
						: 'bg-blue-500/20 text-blue-700 dark:text-blue-300'}"
				>
					{connection?.type === 'mcp' ? 'MCP' : 'OpenAPI'}
				</span>

				{#if connection?.info?.name}
					<div class="capitalize outline-hidden w-full bg-transparent truncate">
						{connection?.info?.name ?? connection?.url}
						<span class="text-gray-500">{connection?.info?.id ?? ''}</span>
					</div>
				{:else}
					<div class="truncate">
						{connection?.url}
					</div>
				{/if}

				{#if connection?.auth_type && connection.auth_type !== 'none'}
					<span class="text-[10px] text-gray-400 dark:text-gray-500 shrink-0">
						{connection.auth_type === 'bearer'
							? $i18n.t('Bearer')
							: connection.auth_type === 'session'
								? $i18n.t('Session')
								: connection.auth_type === 'system_oauth'
									? $i18n.t('OAuth')
									: connection.auth_type === 'oauth_2.1'
										? $i18n.t('OAuth 2.1')
										: connection.auth_type}
					</span>
				{/if}
			</div>
		</div>
	</Tooltip>

	<div class="flex gap-1">
		<Tooltip content={$i18n.t('Configure')} className="self-start">
			<button
				class="self-center p-1 bg-transparent hover:bg-gray-100 dark:bg-gray-900 dark:hover:bg-gray-850 rounded-lg transition"
				on:click={() => {
					showConfigModal = true;
				}}
				type="button"
			>
				<Cog6 />
			</button>
		</Tooltip>
	</div>
</div>
