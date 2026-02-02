<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { templates } from '$lib/stores';
	import { onMount, getContext } from 'svelte';

	const i18n = getContext('i18n');

	import { getTemplateById, getTemplates, updateTemplate } from '$lib/apis/templates';
	import { page } from '$app/stores';

	import TemplateEditor from '$lib/components/workspace/Templates/TemplateEditor.svelte';

	let template = null;

	const onSubmit = async (_template) => {
		const id = $page.url.searchParams.get('id');
		const res = await updateTemplate(localStorage.token, id, _template).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Template updated successfully'));
			await templates.set(await getTemplates(localStorage.token));
			await goto('/workspace/templates');
		}
	};

	onMount(async () => {
		const id = $page.url.searchParams.get('id');
		if (id) {
			const _template = await getTemplateById(localStorage.token, id).catch((error) => {
				toast.error(`${error}`);
				return null;
			});

			if (_template) {
				template = _template;
			} else {
				goto('/workspace/templates');
			}
		} else {
			goto('/workspace/templates');
		}
	});
</script>

{#if template}
	<TemplateEditor {template} {onSubmit} edit />
{/if}
