import { app } from '@splunk/splunk-utils/config';
import { getDefaultFetchInit } from '@splunk/splunk-utils/fetch';
import { createRESTURL } from '@splunk/splunk-utils/url';

const APP = 'data_dictionary_for_splunk';
const API_PREFIX = 'data_dictionary';

function url(endpoint) {
    const normalized = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
    return createRESTURL(`${API_PREFIX}/${normalized}`, { app: APP });
}

async function fetchJson(endpoint, options = {}) {
    const init = getDefaultFetchInit();
    const res = await fetch(url(endpoint), { ...init, ...options });
    if (!res.ok) {
        const text = await res.text();
        let body;
        try {
            body = JSON.parse(text);
        } catch {
            body = { error: text || res.statusText };
        }
        throw new Error(body.error || res.statusText || 'Request failed');
    }
    return res.json();
}

export async function ping() {
    return fetchJson('ping');
}

/**
 * Current user's Data Dictionary permissions. Server endpoints enforce the same
 * capability; this only drives whether the UI shows edit controls.
 * @returns {Promise<{username: string, can_edit: boolean, capability: string, roles: string[]}>}
 */
export async function getPermissions() {
    return fetchJson('permissions');
}

export async function getDiscoveryIndexes() {
    return fetchJson('discovery/indexes');
}

export async function getDiscoverySourcetypes() {
    return fetchJson('discovery/sourcetypes');
}

export async function getDiscoveryCatalog() {
    return fetchJson('discovery/catalog');
}

export async function getMetadataList() {
    return fetchJson('metadata');
}

export async function getMetadata(key) {
    return fetchJson(`metadata/${encodeURIComponent(key)}`);
}

/**
 * Fetch option list for dropdowns. Use macro= or lookup= for macro/list name.
 * @param {('macro'|'lookup')} type
 * @param {string} name - e.g. 'operation_contacts_list' or 'pii_levels'
 * @returns {Promise<string[]>}
 */
export async function getOptions(type, name) {
    const params = new URLSearchParams({ [type]: name });
    const data = await fetchJson(`options?${params.toString()}`);
    return Array.isArray(data.options) ? data.options : [];
}

export async function triggerCatalogBuild() {
    return fetchJson('build-catalog', { method: 'POST' });
}

/**
 * Admin-managed metadata field definitions (standard + custom).
 * @returns {Promise<Array<{_key, label, type, options?, options_source?, standard, hidden, order}>>}
 */
export async function getFieldDefs() {
    const data = await fetchJson('field-defs');
    return Array.isArray(data.field_defs) ? data.field_defs : [];
}

export async function upsertFieldDef(key, body) {
    const init = getDefaultFetchInit();
    const res = await fetch(url(`field-defs/${encodeURIComponent(key)}`), {
        ...init,
        method: 'POST',
        headers: { ...init.headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const text = await res.text();
        let data;
        try { data = JSON.parse(text); } catch { data = { error: text }; }
        throw new Error(data.error || res.statusText);
    }
    return res.json();
}

export async function deleteFieldDef(key) {
    const init = getDefaultFetchInit();
    const res = await fetch(url(`field-defs/${encodeURIComponent(key)}`), { ...init, method: 'DELETE' });
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
}

export async function upsertMetadata(key, body) {
    const init = getDefaultFetchInit();
    const res = await fetch(url(`metadata/${encodeURIComponent(key)}`), {
        ...init,
        method: 'POST',
        headers: {
            ...init.headers,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ _key: key, ...body }),
    });
    if (!res.ok) {
        const text = await res.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch {
            data = { error: text };
        }
        throw new Error(data.error || res.statusText);
    }
    return res.json();
}
