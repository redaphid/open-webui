<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { onMount, getContext } from 'svelte';
	import { WEBUI_NAME, templates as _templates, user } from '$lib/stores';

	import { getTemplates, deleteTemplate } from '$lib/apis/templates';

	import EllipsisHorizontal from '../icons/EllipsisHorizontal.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import XMark from '../icons/XMark.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import Wrench from '../icons/Wrench.svelte';
	import TemplateMenu from './Templates/TemplateMenu.svelte';

	let shiftKey = false;

	const i18n = getContext('i18n');
	let loaded = false;

	let query = '';
	let templates = [];

	let showDeleteConfirm = false;
	let deleteTemplateItem = null;

	let filteredItems = [];

	$: if (templates && query !== undefined) {
		setFilteredItems();
	}

	const setFilteredItems = () => {
		filteredItems = templates.filter((t) => {
			if (query === '') return true;
			const lowerQuery = query.toLowerCase();
			return (
				(t.name || '').toLowerCase().includes(lowerQuery) ||
				(t.description || '').toLowerCase().includes(lowerQuery)
			);
		});
	};

	const deleteHandler = async (template) => {
		const res = await deleteTemplate(localStorage.token, template.id).catch((err) => {
			toast.error(err);
			return false;
		});

		if (res) {
			toast.success($i18n.t(`Deleted {{name}}`, { name: template.name }));
		}

		await init();
	};

	const init = async () => {
		templates = await getTemplates(localStorage.token);
		await _templates.set(templates);
	};

	onMount(async () => {
		await init();
		loaded = true;

		const onKeyDown = (event) => {
			if (event.key === 'Shift') {
				shiftKey = true;
			}
		};

		const onKeyUp = (event) => {
			if (event.key === 'Shift') {
				shiftKey = false;
			}
		};

		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur', onBlur);

		return () => {
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur', onBlur);
		};
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Templates')} | {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete template?')}
		on:confirm={() => {
			deleteHandler(deleteTemplateItem);
		}}
	>
		<div class=" text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="font-medium">{deleteTemplateItem?.name}</span>.
		</div>
	</DeleteConfirmDialog>

	<div class="flex flex-col gap-1 px-1 mt-1.5 mb-3">
		<div class="flex justify-between items-center">
			<div class="flex items-center md:self-center text-xl font-medium px-0.5 gap-2 shrink-0">
				<div>
					{$i18n.t('Templates')}
				</div>

				<div class="text-lg font-medium text-gray-500 dark:text-gray-500">
					{filteredItems.length}
				</div>
			</div>

			<div class="flex w-full justify-end gap-1.5">
				<a
					class=" px-2 py-1.5 rounded-xl bg-black text-white dark:bg-white dark:text-black transition font-medium text-sm flex items-center"
					href="/workspace/templates/create"
				>
					<Plus className="size-3" strokeWidth="2.5" />

					<div class=" hidden md:block md:ml-1 text-xs">{$i18n.t('New Template')}</div>
				</a>
			</div>
		</div>
	</div>

	<div
		class="py-2 bg-white dark:bg-gray-900 rounded-3xl border border-gray-100/30 dark:border-gray-850/30"
	>
		<div class=" flex w-full space-x-2 py-0.5 px-3.5 pb-2">
			<div class="flex flex-1">
				<div class=" self-center ml-1 mr-3">
					<Search className="size-3.5" />
				</div>
				<input
					class=" w-full text-sm pr-4 py-1 rounded-r-xl outline-hidden bg-transparent"
					bind:value={query}
					placeholder={$i18n.t('Search Templates')}
				/>

				{#if query}
					<div class="self-center pl-1.5 translate-y-[0.5px] rounded-l-xl bg-transparent">
						<button
							class="p-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900 transition"
							on:click={() => {
								query = '';
							}}
						>
							<XMark className="size-3" strokeWidth="2" />
						</button>
					</div>
				{/if}
			</div>
		</div>

		{#if (filteredItems ?? []).length !== 0}
			<div class="gap-2 grid my-2 px-3 lg:grid-cols-2">
				{#each filteredItems as template}
					<a
						class=" flex space-x-4 cursor-pointer text-left w-full px-3 py-2.5 dark:hover:bg-gray-850/50 hover:bg-gray-50 transition rounded-2xl"
						href={`/workspace/templates/edit?id=${encodeURIComponent(template.id)}`}
					>
						<div class="flex items-center justify-center w-10 h-10 rounded-full bg-gray-100 dark:bg-gray-800">
							<Wrench className="size-5 text-gray-500" />
						</div>
						<div class=" flex flex-col flex-1 cursor-pointer w-full">
							<div class="flex items-center justify-between w-full">
								<div class="flex items-center gap-2">
									<div class="font-medium line-clamp-1">{template.name}</div>
								</div>
							</div>

							{#if template.description}
								<div class="text-xs text-gray-500 line-clamp-1">
									{template.description}
								</div>
							{/if}

							<div class="flex gap-2 mt-1">
								{#if template.tool_ids?.length}
									<div class="text-xs text-gray-400">
										{template.tool_ids.length} {$i18n.t('tools')}
									</div>
								{/if}
								{#if template.system_prompt}
									<div class="text-xs text-gray-400">
										{$i18n.t('Custom prompt')}
									</div>
								{/if}
							</div>
						</div>
						<div class="flex flex-row gap-0.5 self-center">
							{#if shiftKey}
								<Tooltip content={$i18n.t('Delete')}>
									<button
										class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
										type="button"
										on:click|preventDefault={() => {
											deleteHandler(template);
										}}
									>
										<GarbageBin />
									</button>
								</Tooltip>
							{:else}
								<TemplateMenu
									deleteHandler={async () => {
										deleteTemplateItem = template;
										showDeleteConfirm = true;
									}}
									onClose={() => {}}
								>
									<button
										class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
										type="button"
									>
										<EllipsisHorizontal className="size-5" />
									</button>
								</TemplateMenu>
							{/if}
						</div>
					</a>
				{/each}
			</div>
		{:else}
			<div class=" w-full h-full flex flex-col justify-center items-center my-16 mb-24">
				<div class="max-w-md text-center">
					<div class=" text-3xl mb-3">
						<Wrench className="size-12 mx-auto text-gray-300 dark:text-gray-600" />
					</div>
					<div class=" text-lg font-medium mb-1">{$i18n.t('No templates found')}</div>
					<div class=" text-gray-500 text-center text-xs">
						{$i18n.t('Create a template to quickly start chats with pre-configured tools and prompts.')}
					</div>
				</div>
			</div>
		{/if}
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
