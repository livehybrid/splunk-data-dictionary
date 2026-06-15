import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Button from '@splunk/react-ui/Button';
import ComboBox from '@splunk/react-ui/ComboBox';
import ControlGroup from '@splunk/react-ui/ControlGroup';
import Heading from '@splunk/react-ui/Heading';
import Message from '@splunk/react-ui/Message';
import Modal from '@splunk/react-ui/Modal';
import P from '@splunk/react-ui/Paragraph';
import Select from '@splunk/react-ui/Select';
import Switch from '@splunk/react-ui/Switch';
import Table from '@splunk/react-ui/Table';
import Text from '@splunk/react-ui/Text';
import Tooltip from '@splunk/react-ui/Tooltip';
import WaitSpinner from '@splunk/react-ui/WaitSpinner';
import Magnifier from '@splunk/react-icons/Magnifier';
import Pencil from '@splunk/react-icons/Pencil';
import {
    getDiscoveryCatalog,
    getMetadata,
    getMetadataList,
    getOptions,
    ping,
    triggerCatalogBuild,
    upsertMetadata,
} from './api';

// Field definitions for the metadata edit/view form.
// - optionsSource: pull suggestions from a Splunk macro or lookup (free-text still allowed).
// - options: a fixed list rendered as a strict dropdown (e.g. a Yes/No boolean).
const METADATA_FIELDS = [
    { id: 'data_owner', label: 'Data Owner', optionsSource: { type: 'macro', name: 'data_owner_list' } },
    { id: 'data_category', label: 'Data Category' },
    { id: 'pii_status', label: 'PII Status', options: ['Yes', 'No'] },
    { id: 'export_classification', label: 'Export Classification', optionsSource: { type: 'lookup', name: 'export_classification_options' } },
    { id: 'service_owner', label: 'Service Owner', optionsSource: { type: 'macro', name: 'data_owner_list' } },
    { id: 'security_owner', label: 'Security Owner', optionsSource: { type: 'macro', name: 'data_owner_list' } },
    { id: 'escalation_contacts', label: 'Escalation Contacts', optionsSource: { type: 'macro', name: 'operation_contacts_list' } },
];

const TABLE_COLUMN_OPTIONS = [
    { id: 'index', label: 'Index' },
    { id: 'sourcetype', label: 'Sourcetype' },
    { id: 'data_owner', label: 'Data Owner' },
    { id: 'data_category', label: 'Data Category' },
    { id: 'pii_status', label: 'PII Status' },
    { id: 'export_classification', label: 'Export Classification' },
    { id: 'service_owner', label: 'Service Owner' },
    { id: 'security_owner', label: 'Security Owner' },
    { id: 'escalation_contacts', label: 'Escalation Contacts' },
];

const DEFAULT_VISIBLE_COLUMNS = ['index', 'sourcetype', 'data_owner', 'pii_status', 'export_classification'];

function rowKey(index, sourcetype) {
    return `index_sourcetype:${index || ''}:${sourcetype || ''}`;
}

// Index names cannot contain ':', but sourcetypes can (e.g. cisco:asa), so split
// on the FIRST ':' after the prefix: everything after it is the sourcetype.
function parseRowKey(key) {
    const prefix = 'index_sourcetype:';
    const rest = key && key.startsWith(prefix) ? key.slice(prefix.length) : key || '';
    const i = rest.indexOf(':');
    if (i < 0) return { index: rest, sourcetype: '' };
    return { index: rest.slice(0, i), sourcetype: rest.slice(i + 1) };
}

function hasMetadata(meta) {
    if (!meta) return false;
    return METADATA_FIELDS.some((f) => meta[f.id] && String(meta[f.id]).trim());
}

// Strip bookkeeping/_key fields — keep only the governance fields the user edits.
// (upsertMetadata sets _key per target, and the backend stamps updated_by/at.)
function metadataPayload(doc) {
    const out = {};
    METADATA_FIELDS.forEach((f) => {
        if (doc[f.id] !== undefined) out[f.id] = doc[f.id];
    });
    return out;
}

export default function DataDictionaryHome() {
    const [connected, setConnected] = useState(null);
    const [error, setError] = useState(null);
    const [catalog, setCatalog] = useState([]);
    const [catalogMessage, setCatalogMessage] = useState(null);
    const [metadataList, setMetadataList] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedKey, setSelectedKey] = useState(null);
    const [metadataModalMode, setMetadataModalMode] = useState('edit');
    const [editDoc, setEditDoc] = useState({});
    const [saving, setSaving] = useState(false);
    const [applyScope, setApplyScope] = useState('row');

    // Parse initial filters from URL query parameters (e.g. ?index=foo&sourcetype=bar)
    const initialUrlParams = useMemo(() => new URLSearchParams(window.location.search), []);
    const [filterIndex, setFilterIndex] = useState(initialUrlParams.get('index') || '');
    const [filterSourcetype, setFilterSourcetype] = useState(initialUrlParams.get('sourcetype') || '');

    const [filterText, setFilterText] = useState('');
    const [sortBy, setSortBy] = useState('index');
    const [sortAsc, setSortAsc] = useState(true);
    const [unprocessedOnly, setUnprocessedOnly] = useState(false);
    const [visibleTableColumns, setVisibleTableColumns] = useState(DEFAULT_VISIBLE_COLUMNS);
    const [columnModalOpen, setColumnModalOpen] = useState(false);
    const [columnModalSelections, setColumnModalSelections] = useState([]);
    const [optionsCache, setOptionsCache] = useState({});
    const [triggering, setTriggering] = useState(false);
    const editButtonRef = useRef(null);
    const columnButtonRef = useRef(null);

    const load = useCallback(async () => {
        setError(null);
        setLoading(true);
        try {
            await ping();
            setConnected(true);
            const [catalogRes, metaRes] = await Promise.all([
                getDiscoveryCatalog(),
                getMetadataList(),
            ]);
            setCatalog(catalogRes.catalog || []);
            setCatalogMessage(catalogRes.message || null);
            setMetadataList(metaRes.metadata || []);
        } catch (e) {
            setConnected(false);
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Load option lists when edit modal opens (for macro/lookup-backed dropdown fields)
    useEffect(() => {
        if (!selectedKey) {
            setOptionsCache({});
            return undefined;
        }
        const sources = [];
        METADATA_FIELDS.forEach((f) => {
            if (f.optionsSource) {
                const key = `${f.optionsSource.type}:${f.optionsSource.name}`;
                if (!sources.some((s) => s.key === key)) sources.push({ key, ...f.optionsSource });
            }
        });
        let cancelled = false;
        Promise.all(
            sources.map(({ key, type, name }) =>
                getOptions(type, name).then((opts) => (cancelled ? null : { key, opts }))
            )
        ).then((results) => {
            if (cancelled) return;
            const next = {};
            results.forEach((r) => {
                if (r) next[r.key] = r.opts;
            });
            setOptionsCache(next);
        });
        return () => { cancelled = true; };
    }, [selectedKey]);

    const metaByKey = useMemo(
        () => Object.fromEntries((metadataList || []).map((m) => [m._key, m])),
        [metadataList],
    );

    // Distinct values already entered for each field, across all saved metadata.
    // Used to suggest existing values in the edit dropdowns (no macro/lookup needed).
    const distinctValuesByField = useMemo(() => {
        const map = {};
        METADATA_FIELDS.forEach((f) => { map[f.id] = new Set(); });
        (metadataList || []).forEach((doc) => {
            METADATA_FIELDS.forEach((f) => {
                const v = doc[f.id];
                if (v != null && String(v).trim()) map[f.id].add(String(v).trim());
            });
        });
        return map;
    }, [metadataList]);

    const catalogRows = useMemo(() => {
        const rows = (catalog || []).map((r) => {
            const index = r.index ?? r.Index ?? '';
            const sourcetype = r.sourcetype ?? r.Sourcetype ?? '';
            return {
                index,
                sourcetype,
                frozenTimePeriodInSecs: r.frozenTimePeriodInSecs ?? '',
                key: rowKey(index, sourcetype),
            };
        });
        return rows;
    }, [catalog]);

    const filteredRows = useMemo(() => {
        let out = catalogRows;
        if (filterIndex) {
            out = out.filter((r) => r.index === filterIndex);
        }
        if (filterSourcetype) {
            out = out.filter((r) => r.sourcetype === filterSourcetype);
        }
        if (filterText.trim()) {
            const t = filterText.trim().toLowerCase();
            out = out.filter(
                (r) =>
                    String(r.index).toLowerCase().includes(t) ||
                    String(r.sourcetype).toLowerCase().includes(t),
            );
        }
        if (unprocessedOnly) {
            out = out.filter((row) => !hasMetadata(metaByKey[row.key]));
        }
        const order = sortAsc ? 1 : -1;
        out = [...out].sort((a, b) => {
            const va = a[sortBy] ?? '';
            const vb = b[sortBy] ?? '';
            return order * String(va).localeCompare(String(vb));
        });
        return out;
    }, [catalogRows, filterIndex, filterSourcetype, filterText, sortBy, sortAsc, unprocessedOnly, metaByKey]);

    const indexOptions = useMemo(() => {
        const set = new Set(catalogRows.map((r) => r.index).filter(Boolean));
        return Array.from(set).sort();
    }, [catalogRows]);

    const sourcetypeOptions = useMemo(() => {
        const rows = filterIndex
            ? catalogRows.filter((r) => r.index === filterIndex)
            : catalogRows;
        const set = new Set(rows.map((r) => r.sourcetype).filter(Boolean));
        return Array.from(set).sort();
    }, [catalogRows, filterIndex]);

    // When index filter or options change, clear sourcetype if it's no longer valid
    useEffect(() => {
        if (filterSourcetype && !sourcetypeOptions.includes(filterSourcetype)) {
            setFilterSourcetype('');
        }
    }, [filterIndex, sourcetypeOptions, filterSourcetype]);

    // Index + per-index counts for the "apply to" scope selector in the edit modal.
    const editIndex = useMemo(() => (selectedKey ? parseRowKey(selectedKey).index : ''), [selectedKey]);
    const indexAllCount = useMemo(
        () => catalogRows.filter((r) => r.index === editIndex).length,
        [catalogRows, editIndex],
    );
    const indexUnsetCount = useMemo(
        () => catalogRows.filter(
            (r) => r.index === editIndex && (r.key === selectedKey || !hasMetadata(metaByKey[r.key])),
        ).length,
        [catalogRows, editIndex, selectedKey, metaByKey],
    );

    const openMetadata = useCallback(async (key, mode, event) => {
        if (event?.currentTarget) {
            editButtonRef.current = event.currentTarget;
        }
        setSelectedKey(key);
        setMetadataModalMode(mode);
        setApplyScope('row');
        try {
            const doc = await getMetadata(key);
            setEditDoc(doc && typeof doc === 'object' ? doc : { _key: key });
        } catch {
            setEditDoc({ _key: key });
        }
    }, []);

    const openEdit = useCallback((key, event) => openMetadata(key, 'edit', event), [openMetadata]);
    const openView = useCallback((key, event) => openMetadata(key, 'view', event), [openMetadata]);

    const closeEdit = useCallback(() => {
        setSelectedKey(null);
        setMetadataModalMode('edit');
        setEditDoc({});
        setApplyScope('row');
    }, []);

    const openColumnModal = useCallback(() => {
        setColumnModalSelections([...visibleTableColumns]);
        setColumnModalOpen(true);
    }, [visibleTableColumns]);

    const closeColumnModal = useCallback(() => {
        setColumnModalOpen(false);
    }, []);

    const saveColumnModal = useCallback(() => {
        setVisibleTableColumns(columnModalSelections.length ? columnModalSelections : DEFAULT_VISIBLE_COLUMNS);
        setColumnModalOpen(false);
    }, [columnModalSelections]);

    const toggleColumnModalSelection = useCallback((id) => {
        setColumnModalSelections((prev) =>
            prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id].sort((a, b) => {
                const ai = TABLE_COLUMN_OPTIONS.findIndex((c) => c.id === a);
                const bi = TABLE_COLUMN_OPTIONS.findIndex((c) => c.id === b);
                return ai - bi;
            })
        );
    }, []);

    const handleSave = useCallback(async () => {
        if (!selectedKey) return;
        setSaving(true);
        try {
            const payload = metadataPayload(editDoc);
            const { index } = parseRowKey(selectedKey);
            let keys = [selectedKey];
            if (applyScope === 'all') {
                keys = catalogRows.filter((r) => r.index === index).map((r) => r.key);
            } else if (applyScope === 'unset') {
                keys = catalogRows
                    .filter((r) => r.index === index && (r.key === selectedKey || !hasMetadata(metaByKey[r.key])))
                    .map((r) => r.key);
            }
            keys = Array.from(new Set(keys));
            // Sequential writes — kinder to the KV store than a burst of parallel POSTs.
            // eslint-disable-next-line no-restricted-syntax
            for (const k of keys) {
                // eslint-disable-next-line no-await-in-loop
                await upsertMetadata(k, payload);
            }
            await load();
            closeEdit();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setSaving(false);
        }
    }, [selectedKey, editDoc, applyScope, catalogRows, metaByKey, load, closeEdit]);

    const toggleSort = useCallback((col) => {
        setSortBy((prev) => (prev === col ? prev : col));
        setSortAsc((prev) => (col === sortBy ? !prev : true));
    }, [sortBy]);

    const handleTriggerCatalog = useCallback(async () => {
        setTriggering(true);
        try {
            await triggerCatalogBuild();
            // Give the saved search time to write the lookup, then refresh.
            setTimeout(() => {
                load();
            }, 3000);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setTriggering(false);
        }
    }, [load]);

    const saveLabel = useMemo(() => {
        if (saving) return 'Saving…';
        if (applyScope === 'all') return `Save to all (${indexAllCount})`;
        if (applyScope === 'unset') return `Save to un-set (${indexUnsetCount})`;
        return 'Save';
    }, [saving, applyScope, indexAllCount, indexUnsetCount]);

    return (
        <div style={{ padding: 24 }}>
            <Heading level={2} style={{ marginBottom: 8 }}>Data Dictionary</Heading>
            <P style={{ marginBottom: 24 }}>
                Browse and manage metadata for index and sourcetype pairs. Catalog is built from a lookup populated by the Data Dictionary catalog saved search.
            </P>

            {loading && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <WaitSpinner size="medium" />
                    <Text>Loading…</Text>
                </div>
            )}
            {error && (
                <Message type="error" onRequestClose={() => setError(null)} style={{ marginBottom: 16 }}>
                    {error}
                </Message>
            )}

            {!loading && connected && (
                <>
                    <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
                        <Button
                            appearance="primary"
                            onClick={load}
                            label="Refresh catalog and metadata"
                        />
                        <Button
                            appearance="secondary"
                            onClick={handleTriggerCatalog}
                            disabled={triggering}
                            label={triggering ? 'Running...' : 'Run catalog search'}
                        />
                        <Switch
                            selected={unprocessedOnly}
                            onClick={(e, { selected }) => setUnprocessedOnly(!selected)}
                        >
                            View unprocessed only
                        </Switch>
                    </div>

                    {catalogMessage && catalogRows.length === 0 && (
                        <Message type="info" style={{ marginBottom: 16 }}>
                            {catalogMessage}
                        </Message>
                    )}

                    {catalogRows.length > 0 && (
                        <>
                            <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
                                <ControlGroup label="Index" labelPosition="left" controlsLayout="none" style={{ minWidth: 140 }}>
                                    <Select
                                        filter
                                        value={filterIndex}
                                        onChange={(e, { value }) => setFilterIndex(value)}
                                        style={{ width: '100%' }}
                                    >
                                        <Select.Option label="All" value="" />
                                        {indexOptions.map((idx) => (
                                            <Select.Option key={idx} label={idx} value={idx} />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <ControlGroup label="Sourcetype" labelPosition="left" controlsLayout="none" style={{ minWidth: 140 }}>
                                    <Select
                                        filter
                                        value={filterSourcetype}
                                        onChange={(e, { value }) => setFilterSourcetype(value)}
                                        style={{ width: '100%' }}
                                    >
                                        <Select.Option label="All" value="" />
                                        {sourcetypeOptions.map((st) => (
                                            <Select.Option key={st} label={st} value={st} />
                                        ))}
                                    </Select>
                                </ControlGroup>
                                <ControlGroup
                                    label="Search"
                                    labelPosition="left"
                                    controlsLayout="none"
                                    style={{ minWidth: 200 }}
                                >
                                    <Text
                                        value={filterText}
                                        onChange={(e, { value }) => setFilterText(value ?? '')}
                                        style={{ width: '100%' }}
                                    />
                                </ControlGroup>
                                <Button
                                    ref={columnButtonRef}
                                    appearance="secondary"
                                    label="Choose columns"
                                    onClick={openColumnModal}
                                    style={{ flex: '0 0 auto', whiteSpace: 'nowrap' }}
                                />
                            </div>

                            <Table stripeRows>
                                <Table.Head>
                                    {visibleTableColumns.map((colId) => {
                                        const col = TABLE_COLUMN_OPTIONS.find((c) => c.id === colId);
                                        if (!col) return null;
                                        if (colId === 'index' || colId === 'sourcetype') {
                                            return (
                                                <Table.HeadCell
                                                    key={colId}
                                                    sortDir={sortBy === colId ? (sortAsc ? 'asc' : 'desc') : 'none'}
                                                    sortKey={colId}
                                                    onSort={(e, { sortKey }) => sortKey && toggleSort(sortKey)}
                                                >
                                                    {col.label}
                                                </Table.HeadCell>
                                            );
                                        }
                                        return <Table.HeadCell key={colId}>{col.label}</Table.HeadCell>;
                                    })}
                                    <Table.HeadCell>Actions</Table.HeadCell>
                                </Table.Head>
                                <Table.Body>
                                    {filteredRows.length === 0 ? (
                                        <Table.Row>
                                            <Table.Cell colSpan={visibleTableColumns.length + 1}>
                                                <Text>No rows match the current filters.</Text>
                                            </Table.Cell>
                                        </Table.Row>
                                    ) : (
                                        filteredRows.map((row) => {
                                            const meta = metaByKey[row.key];
                                            return (
                                                <Table.Row key={row.key} data={row}>
                                                    {visibleTableColumns.map((colId) => (
                                                        <Table.Cell key={colId}>
                                                            {colId === 'index' || colId === 'sourcetype'
                                                                ? row[colId]
                                                                : (meta?.[colId] ?? '—')}
                                                        </Table.Cell>
                                                    ))}
                                                    <Table.Cell>
                                                        <div style={{ display: 'flex', gap: 4 }}>
                                                            <Tooltip content="View metadata">
                                                                <Button
                                                                    appearance="secondary"
                                                                    icon={<Magnifier />}
                                                                    aria-label={`View metadata for ${row.sourcetype}`}
                                                                    onClick={(e) => openView(row.key, e)}
                                                                />
                                                            </Tooltip>
                                                            <Tooltip content="Edit metadata">
                                                                <Button
                                                                    appearance="secondary"
                                                                    icon={<Pencil />}
                                                                    aria-label={`Edit metadata for ${row.sourcetype}`}
                                                                    onClick={(e) => openEdit(row.key, e)}
                                                                />
                                                            </Tooltip>
                                                        </div>
                                                    </Table.Cell>
                                                </Table.Row>
                                            );
                                        })
                                    )}
                                </Table.Body>
                            </Table>
                        </>
                    )}

                    {catalogRows.length === 0 && !catalogMessage && connected && !loading && (
                        <Message type="info" style={{ marginTop: 16 }}>
                            Catalog is empty. Run or schedule the Data Dictionary catalog saved search to populate the lookup.
                        </Message>
                    )}
                </>
            )}

            <Modal
                open={!!selectedKey}
                onRequestClose={closeEdit}
                returnFocus={editButtonRef}
                closeOnClickAway={false}
                divider="both"
            >
                <Modal.Header
                    title={
                        metadataModalMode === 'view'
                            ? `View metadata: ${selectedKey || ''}`
                            : `Edit metadata: ${selectedKey || ''}`
                    }
                    onRequestClose={closeEdit}
                />
                <Modal.Body style={{ minWidth: 400 }}>
                    {METADATA_FIELDS.map((f) => {
                        const value = editDoc[f.id] ?? '';
                        if (metadataModalMode === 'view') {
                            return (
                                <ControlGroup
                                    key={f.id}
                                    label={f.label}
                                    style={{ marginBottom: 16 }}
                                    controlsLayout="fill"
                                >
                                    <P>{value || '—'}</P>
                                </ControlGroup>
                            );
                        }
                        // Fixed-option fields (e.g. PII Status Yes/No) — strict dropdown.
                        if (f.options) {
                            const opts = [...f.options];
                            if (value && !opts.includes(value)) opts.push(value);
                            return (
                                <ControlGroup
                                    key={f.id}
                                    label={f.label}
                                    style={{ marginBottom: 16 }}
                                    controlsLayout="fill"
                                >
                                    <Select
                                        value={value}
                                        onChange={(e, { value: v }) =>
                                            setEditDoc((prev) => ({ ...prev, [f.id]: v ?? '' }))
                                        }
                                        style={{ width: '100%' }}
                                    >
                                        <Select.Option label="—" value="" />
                                        {opts.map((opt) => (
                                            <Select.Option key={opt} label={opt} value={opt} />
                                        ))}
                                    </Select>
                                </ControlGroup>
                            );
                        }
                        // Free-text fields with suggestions: macro/lookup options + values
                        // already used for this field across the estate.
                        const cacheKey = f.optionsSource && `${f.optionsSource.type}:${f.optionsSource.name}`;
                        const sourceOpts = (cacheKey && optionsCache[cacheKey]) || [];
                        const distinctOpts = Array.from(distinctValuesByField[f.id] || []);
                        const optionSet = new Set([...sourceOpts, ...distinctOpts]);
                        if (value && !optionSet.has(value)) optionSet.add(value);
                        const optionsList = Array.from(optionSet).sort((a, b) => a.localeCompare(b));
                        return (
                            <ControlGroup
                                key={f.id}
                                label={f.label}
                                style={{ marginBottom: 16 }}
                                controlsLayout="fill"
                            >
                                <ComboBox
                                    value={value}
                                    onChange={(e, { value: v }) =>
                                        setEditDoc((prev) => ({ ...prev, [f.id]: v ?? '' }))
                                    }
                                    style={{ width: '100%' }}
                                >
                                    {optionsList.map((opt) => (
                                        <ComboBox.Option key={opt} value={opt} />
                                    ))}
                                </ComboBox>
                            </ControlGroup>
                        );
                    })}

                    {metadataModalMode !== 'view' && (
                        <ControlGroup
                            label="Apply to"
                            help={
                                applyScope === 'all'
                                    ? `Overwrites metadata on all ${indexAllCount} sourcetypes in index "${editIndex}".`
                                    : applyScope === 'unset'
                                        ? `Fills in this row plus every sourcetype in index "${editIndex}" that has no metadata yet (${indexUnsetCount}).`
                                        : 'Saves these values to this sourcetype only.'
                            }
                            style={{ marginBottom: 4, marginTop: 8 }}
                            controlsLayout="fill"
                        >
                            <Select
                                value={applyScope}
                                onChange={(e, { value: v }) => setApplyScope(v)}
                                style={{ width: '100%' }}
                            >
                                <Select.Option label="This sourcetype only" value="row" />
                                <Select.Option
                                    label={`All sourcetypes in "${editIndex}" (${indexAllCount})`}
                                    value="all"
                                />
                                <Select.Option
                                    label={`Only un-set sourcetypes in "${editIndex}" (${indexUnsetCount})`}
                                    value="unset"
                                />
                            </Select>
                        </ControlGroup>
                    )}
                </Modal.Body>
                <Modal.Footer>
                    {metadataModalMode === 'view' ? (
                        <Button appearance="secondary" label="Close" onClick={closeEdit} />
                    ) : (
                        <>
                            <Button
                                appearance="secondary"
                                label="Cancel"
                                onClick={closeEdit}
                                disabled={saving}
                            />
                            <Button
                                appearance="primary"
                                label={saveLabel}
                                onClick={handleSave}
                                disabled={saving}
                            />
                        </>
                    )}
                </Modal.Footer>
            </Modal>

            <Modal
                open={columnModalOpen}
                onRequestClose={closeColumnModal}
                returnFocus={columnButtonRef}
                closeOnClickAway={false}
                divider="both"
            >
                <Modal.Header
                    title="Choose table columns"
                    onRequestClose={closeColumnModal}
                />
                <Modal.Body style={{ minWidth: 320 }}>
                    {TABLE_COLUMN_OPTIONS.map((col) => (
                        <Switch
                            key={col.id}
                            selected={columnModalSelections.includes(col.id)}
                            onClick={() => toggleColumnModalSelection(col.id)}
                            style={{ marginBottom: 12, display: 'block' }}
                        >
                            {col.label}
                        </Switch>
                    ))}
                </Modal.Body>
                <Modal.Footer>
                    <Button
                        appearance="secondary"
                        label="Cancel"
                        onClick={closeColumnModal}
                    />
                    <Button
                        appearance="primary"
                        label="Apply"
                        onClick={saveColumnModal}
                    />
                </Modal.Footer>
            </Modal>
        </div>
    );
}
