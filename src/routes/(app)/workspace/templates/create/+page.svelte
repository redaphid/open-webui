<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';
	import { templates } from '$lib/stores';
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');

	import { createTemplate, getTemplates } from '$lib/apis/templates';
	import TemplateEditor from '$lib/components/workspace/Templates/TemplateEditor.svelte';

	const onSubmit = async (template) => {
		const res = await createTemplate(localStorage.token, template).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Template created successfully'));

			await templates.set(await getTemplates(localStorage.token));
			await goto('/workspace/templates');
		}
	};
</script>

<TemplateEditor {onSubmit} />
