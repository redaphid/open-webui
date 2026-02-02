<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { tools as toolsStore, toolServers } from '$lib/stores';

	import Textarea from '$lib/components/common/Textarea.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Collapsible from '$lib/components/common/Collapsible.svelte';

	export let onSubmit: Function;
	export let edit = false;
	export let template = null;

	const i18n = getContext('i18n');

	let loading = false;

	let name = '';
	let description = '';
	let system_prompt = '';
	let tool_ids: string[] = [];
	let feature_ids: string[] = [];

	// Build tool options from stores
	$: customTools = ($toolsStore ?? []).map((t) => ({
		id: t.id,
		name: t.name,
		description: t.meta?.description ?? ''
	}));

	$: serverTools = ($toolServers ?? []).map((server) => ({
		id: `direct_server:${server.url}`,
		name: server.openapi?.info?.title ?? server.url,
		description: server.openapi?.info?.description ?? '',
		specs: server.specs ?? []
	}));

	$: allTools = [...customTools, ...serverTools];

	const featureOptions = [
		{ id: 'web_search', name: 'Web Search', description: 'Enable web searching' },
		{ id: 'image_generation', name: 'Image Generation', description: 'Enable image generation' },
		{ id: 'code_interpreter', name: 'Code Interpreter', description: 'Enable code execution' }
	];

	const submitHandler = async () => {
		if (!name.trim()) {
			toast.error($i18n.t('Template name is required'));
			return;
		}

		loading = true;

		await onSubmit({
			name: name.trim(),
			description: description.trim() || null,
			system_prompt: system_prompt.trim() || null,
			tool_ids: tool_ids.length > 0 ? tool_ids : null,
			feature_ids: feature_ids.length > 0 ? feature_ids : null
		});

		loading = false;
	};

	const toggleTool = (toolId: string) => {
		if (tool_ids.includes(toolId)) {
			tool_ids = tool_ids.filter((id) => id !== toolId);
		} else {
			tool_ids = [...tool_ids, toolId];
		}
	};

	const toggleFeature = (featureId: string) => {
		if (feature_ids.includes(featureId)) {
			feature_ids = feature_ids.filter((id) => id !== featureId);
		} else {
			feature_ids = [...feature_ids, featureId];
		}
	};

	onMount(async () => {
		if (template) {
			name = template.name ?? '';
			description = template.description ?? '';
			system_prompt = template.system_prompt ?? '';
			tool_ids = template.tool_ids ?? [];
			feature_ids = template.feature_ids ?? [];
		}
	});
</script>

<div class="w-full max-h-full flex justify-center">
	<form
		class="flex flex-col w-full mb-10"
		on:submit|preventDefault={() => {
			submitHandler();
		}}
	>
		<div class="my-2">
			<div class="flex flex-col w-full gap-1">
				<input
					class="text-2xl font-medium w-full bg-transparent outline-hidden"
					placeholder={$i18n.t('Template Name')}
					bind:value={name}
					required
				/>
				<input
					class="text-sm text-gray-500 w-full bg-transparent outline-hidden"
					placeholder={$i18n.t('Description (optional)')}
					bind:value={description}
				/>
			</div>
		</div>

		<div class="my-4">
			<div class="flex w-full justify-between mb-2">
				<div class="self-center text-sm font-medium">{$i18n.t('System Prompt')}</div>
			</div>

			<div>
				<Textarea
					className="text-sm w-full bg-gray-50 dark:bg-gray-850 rounded-xl p-3 outline-hidden overflow-y-hidden resize-none"
					placeholder={$i18n.t('Enter a system prompt for this template...')}
					bind:value={system_prompt}
					rows={4}
				/>
			</div>
			<div class="text-xs text-gray-400 dark:text-gray-500 mt-1">
				{$i18n.t('This prompt will be used as the system message when starting a chat with this template.')}
			</div>
		</div>

		<div class="my-4">
			<div class="flex w-full justify-between mb-2">
				<div class="self-center text-sm font-medium">{$i18n.t('Default Tools')}</div>
			</div>

			{#if allTools.length > 0}
				<div class="space-y-2">
					{#if customTools.length > 0}
						<div class="text-xs text-gray-500 mb-1">{$i18n.t('Custom Tools')}</div>
						<div class="flex flex-wrap gap-2">
							{#each customTools as tool}
								<button
									type="button"
									class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition {tool_ids.includes(
										tool.id
									)
										? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
										: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
									on:click={() => toggleTool(tool.id)}
								>
									<Checkbox
										state={tool_ids.includes(tool.id) ? 'checked' : 'unchecked'}
										on:change={() => toggleTool(tool.id)}
									/>
									<Tooltip content={tool.description || tool.id}>
										<span class="capitalize">{tool.name}</span>
									</Tooltip>
								</button>
							{/each}
						</div>
					{/if}

					{#if serverTools.length > 0}
						<div class="text-xs text-gray-500 mb-1 mt-3">{$i18n.t('Tool Servers (MCP)')}</div>
						<div class="space-y-2">
							{#each serverTools as server}
								<Collapsible buttonClassName="w-full" chevron>
									<button
										type="button"
										class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition w-full text-left {tool_ids.includes(
											server.id
										)
											? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
											: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
										on:click|stopPropagation={() => toggleTool(server.id)}
									>
										<Checkbox
											state={tool_ids.includes(server.id) ? 'checked' : 'unchecked'}
											on:change={() => toggleTool(server.id)}
										/>
										<div class="flex flex-col">
											<span class="font-medium">{server.name}</span>
											{#if server.description}
												<span class="text-xs text-gray-500 line-clamp-1">{server.description}</span>
											{/if}
										</div>
									</button>

									<div slot="content" class="mt-1 ml-8 space-y-1">
										{#each server.specs ?? [] as spec}
											<div class="text-xs text-gray-500 py-1 px-2 bg-gray-50 dark:bg-gray-850 rounded">
												<span class="font-medium">{spec.name}</span>
												{#if spec.description}
													- {spec.description}
												{/if}
											</div>
										{/each}
									</div>
								</Collapsible>
							{/each}
						</div>
					{/if}
				</div>
			{:else}
				<div class="text-sm text-gray-500 py-4 text-center">
					{$i18n.t('No tools available. Add tools or connect tool servers first.')}
				</div>
			{/if}
		</div>

		<div class="my-4">
			<div class="flex w-full justify-between mb-2">
				<div class="self-center text-sm font-medium">{$i18n.t('Default Features')}</div>
			</div>

			<div class="flex flex-wrap gap-2">
				{#each featureOptions as feature}
					<button
						type="button"
						class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition {feature_ids.includes(
							feature.id
						)
							? 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300'
							: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}"
						on:click={() => toggleFeature(feature.id)}
					>
						<Checkbox
							state={feature_ids.includes(feature.id) ? 'checked' : 'unchecked'}
							on:change={() => toggleFeature(feature.id)}
						/>
						<Tooltip content={feature.description}>
							<span>{feature.name}</span>
						</Tooltip>
					</button>
				{/each}
			</div>
		</div>

		<div class="my-4 flex justify-end pb-20">
			<button
				class="text-sm w-full lg:w-fit px-4 py-2 transition rounded-xl {loading
					? 'cursor-not-allowed bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
					: 'bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black'} flex w-full justify-center"
				type="submit"
				disabled={loading}
			>
				<div class="self-center font-medium">
					{edit ? $i18n.t('Save') : $i18n.t('Create Template')}
				</div>
				{#if loading}
					<div class="ml-1.5 self-center">
						<Spinner />
					</div>
				{/if}
			</button>
		</div>
	</form>
</div>
