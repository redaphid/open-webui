<script lang="ts">
	import { getContext } from 'svelte';
	import { toolServers, tools, showControls, showActiveTools } from '$lib/stores';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Wrench from '$lib/components/icons/Wrench.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';

	const i18n = getContext('i18n');

	export let selectedToolIds: string[] = [];

	// Get selected custom tools
	$: selectedTools = ($tools ?? []).filter((tool) => selectedToolIds.includes(tool.id));

	// Get selected tool servers (those with direct_server: prefix)
	$: selectedServerIds = selectedToolIds
		.filter((id) => id.startsWith('direct_server:'))
		.map((id) => id.replace('direct_server:', ''));

	$: selectedServers = ($toolServers ?? []).filter((server) =>
		selectedServerIds.includes(server.url)
	);

	// Count total available tools
	$: totalToolCount =
		selectedTools.length +
		selectedServers.reduce((acc, server) => acc + (server.specs?.length ?? 0), 0);
</script>

<div class="h-full w-full flex flex-col">
	<div
		class="flex justify-between items-center py-3 px-4 border-b border-gray-100 dark:border-gray-800"
	>
		<div class="flex items-center gap-2">
			<Wrench className="size-5" />
			<span class="text-lg font-medium">{$i18n.t('Active Tools')}</span>
			{#if totalToolCount > 0}
				<span
					class="text-xs bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 px-2 py-0.5 rounded-full"
				>
					{totalToolCount}
				</span>
			{/if}
		</div>

		<button
			class="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition"
			on:click={() => {
				showControls.set(false);
				showActiveTools.set(false);
			}}
		>
			<XMark className="size-4" />
		</button>
	</div>

	<div class="flex-1 overflow-y-auto p-4 space-y-4">
		{#if totalToolCount === 0}
			<div class="text-center py-8 text-gray-500">
				<Wrench className="size-12 mx-auto mb-3 opacity-30" />
				<p class="text-sm">{$i18n.t('No tools selected')}</p>
				<p class="text-xs mt-1">{$i18n.t('Select tools from the input toolbar to use them')}</p>
			</div>
		{:else}
			{#if selectedTools.length > 0}
				<div>
					<h3 class="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
						{$i18n.t('Custom Tools')}
					</h3>
					<div class="space-y-2">
						{#each selectedTools as tool}
							<div
								class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700"
							>
								<div class="flex items-start gap-2">
									<div
										class="w-2 h-2 mt-1.5 rounded-full bg-green-500 flex-shrink-0"
										title={$i18n.t('Ready')}
									/>
									<div class="flex-1 min-w-0">
										<div class="font-medium text-sm truncate">{tool.name}</div>
										{#if tool.meta?.description}
											<div class="text-xs text-gray-500 mt-0.5 line-clamp-2">
												{tool.meta.description}
											</div>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			{#if selectedServers.length > 0}
				<div>
					<h3 class="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
						{$i18n.t('Tool Servers')}
					</h3>
					<div class="space-y-2">
						{#each selectedServers as server}
							<Collapsible buttonClassName="w-full" chevron>
								<div
									class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700"
								>
									<div class="flex items-start gap-2">
										<div
											class="w-2 h-2 mt-1.5 rounded-full bg-green-500 flex-shrink-0"
											title={$i18n.t('Connected')}
										/>
										<div class="flex-1 min-w-0">
											<div class="font-medium text-sm truncate">
												{server.openapi?.info?.title ?? server.url}
											</div>
											{#if server.openapi?.info?.description}
												<div class="text-xs text-gray-500 mt-0.5 line-clamp-2">
													{server.openapi.info.description}
												</div>
											{/if}
											<div class="text-xs text-gray-400 mt-1 truncate">
												{server.specs?.length ?? 0} tools available
											</div>
										</div>
									</div>
								</div>

								<div slot="content" class="mt-2 ml-4 space-y-1">
									{#each server.specs ?? [] as spec}
										<div
											class="p-2 bg-white dark:bg-gray-850 rounded border border-gray-100 dark:border-gray-700"
										>
											<div class="text-xs font-medium">{spec.name}</div>
											{#if spec.description}
												<div class="text-xs text-gray-500 mt-0.5">{spec.description}</div>
											{/if}
										</div>
									{/each}
								</div>
							</Collapsible>
						{/each}
					</div>
				</div>
			{/if}
		{/if}
	</div>
</div>
