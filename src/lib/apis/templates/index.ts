import { WEBUI_API_BASE_URL } from '$lib/constants';

export type Template = {
	id: string;
	user_id: string;
	name: string;
	description: string | null;
	system_prompt: string | null;
	tool_ids: string[] | null;
	feature_ids: string[] | null;
	created_at: number;
	updated_at: number;
};

export type TemplateForm = {
	name: string;
	description?: string | null;
	system_prompt?: string | null;
	tool_ids?: string[] | null;
	feature_ids?: string[] | null;
};

export const getTemplates = async (token: string = ''): Promise<Template[]> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/templates/`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return [];
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getTemplateById = async (token: string, id: string): Promise<Template | null> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/templates/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createTemplate = async (token: string, template: TemplateForm): Promise<Template | null> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/templates/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(template)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateTemplate = async (
	token: string,
	id: string,
	template: TemplateForm
): Promise<Template | null> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/templates/${id}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(template)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteTemplate = async (token: string, id: string): Promise<boolean> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/templates/${id}/delete`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return false;
		});

	if (error) {
		throw error;
	}

	return res;
};
