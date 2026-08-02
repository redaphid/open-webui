<script lang="ts">
	import { getContext, tick } from 'svelte';
	const i18n = getContext('i18n');

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import AddToolServerModal from '$lib/components/AddToolServerModal.svelte';
	import WrenchAlt from '$lib/components/icons/WrenchAlt.svelte';

	export let onDelete = () => {};
	export let onSubmit = () => {};

	export let connection = null;
	export let direct = false;

	let showConfigModal = false;
</script>

<AddToolServerModal
	edit
	{direct}
	bind:show={showConfigModal}
	{connection}
	onDelete={() => {
		onDelete();
		showConfigModal = false;
	}}
	onSubmit={(c) => {
		connection = c;
		onSubmit(c);
	}}
/>

<div class="flex w-full items-center gap-3 text-xs text-gray-600 dark:text-gray-400">
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
					<div class="w-full bg-transparent capitalize outline-hidden truncate">
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
										: connection.auth_type === 'oauth_2.1_static'
											? $i18n.t('OAuth 2.1 (Static)')
											: connection.auth_type}
					</span>
				{/if}
			</div>
		</div>
	</Tooltip>

	<div class="flex shrink-0 items-center gap-1">
		<Tooltip content={$i18n.t('Configure')} className="self-start">
			<button
				class="flex size-6 items-center justify-center rounded-lg text-gray-400 transition-colors hover:text-gray-700 dark:text-gray-600 dark:hover:text-gray-300"
				on:click={() => {
					showConfigModal = true;
				}}
				type="button"
			>
				<Cog6 />
			</button>
		</Tooltip>

		<Tooltip
			content={(connection?.config?.enable ?? true) ? $i18n.t('Enabled') : $i18n.t('Disabled')}
		>
			<Switch
				state={connection?.config?.enable ?? true}
				on:change={() => {
					if (!connection.config) connection.config = {};
					connection.config.enable = !(connection?.config?.enable ?? true);
					onSubmit(connection);
				}}
			/>
		</Tooltip>
	</div>
</div>
