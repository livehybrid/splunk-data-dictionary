import React, { useCallback, useEffect, useState } from 'react';
import Button from '@splunk/react-ui/Button';
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
import Pencil from '@splunk/react-icons/Pencil';
import TrashCanCross from '@splunk/react-icons/TrashCanCross';
import { getFieldDefs, upsertFieldDef, deleteFieldDef, getPermissions } from '../home/api';

const EMPTY = { _key: '', label: '', type: 'select', options: '', order: '', hidden: false };

function slugify(s) {
    return String(s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

export default function FieldsAdmin() {
    const [defs, setDefs] = useState([]);
    const [canEdit, setCanEdit] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingExisting, setEditingExisting] = useState(false);
    const [form, setForm] = useState(EMPTY);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        setError(null);
        setLoading(true);
        try {
            const [defsRes, perms] = await Promise.all([
                getFieldDefs(),
                getPermissions().catch(() => ({ can_edit: false })),
            ]);
            setDefs(defsRes);
            setCanEdit(!!perms.can_edit);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const openNew = useCallback(() => {
        setForm(EMPTY);
        setEditingExisting(false);
        setModalOpen(true);
    }, []);

    const openEdit = useCallback((def) => {
        setForm({
            _key: def._key,
            label: def.label || '',
            type: def.type || 'select',
            options: Array.isArray(def.options) ? def.options.join(', ') : '',
            order: def.order ?? '',
            hidden: !!def.hidden,
            standard: !!def.standard,
            optionsSource: def.options_source,
        });
        setEditingExisting(true);
        setModalOpen(true);
    }, []);

    const setField = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const handleSave = useCallback(async () => {
        const key = editingExisting ? form._key : slugify(form._key || form.label);
        if (!key) { setError('A field id (or label) is required.'); return; }
        setSaving(true);
        try {
            const body = {
                label: form.label || key,
                type: form.type,
                hidden: !!form.hidden,
                standard: !!form.standard,
            };
            if (form.order !== '' && form.order != null) body.order = Number(form.order);
            if (form.type === 'select') {
                const opts = String(form.options || '').split(',').map((s) => s.trim()).filter(Boolean);
                if (opts.length) body.options = opts;
            }
            await upsertFieldDef(key, body);
            setModalOpen(false);
            await load();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setSaving(false);
        }
    }, [form, editingExisting, load]);

    const handleDelete = useCallback(async (def) => {
        // eslint-disable-next-line no-alert
        if (!window.confirm(`Remove field "${def.label || def._key}"?`)) return;
        try {
            await deleteFieldDef(def._key);
            await load();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [load]);

    return (
        <div style={{ padding: 24 }}>
            <Heading level={2} style={{ marginBottom: 8 }}>Data Dictionary - Fields</Heading>
            <P style={{ marginBottom: 16, maxWidth: 820 }}>
                Manage the governance metadata fields shown in the catalogue editor. Standard fields
                ship with the app; add your own custom fields above them. Field types are
                <strong> Select</strong> (a customisable, value-suggesting dropdown) and
                <strong> Boolean</strong> (Yes/No).
            </P>

            {error && (
                <Message type="error" onRequestClose={() => setError(null)} style={{ marginBottom: 16 }}>
                    {error}
                </Message>
            )}

            {!loading && !canEdit && (
                <Message type="info" style={{ marginBottom: 16 }}>
                    You have read-only access. Ask an administrator to grant the
                    &quot;edit_data_dictionary&quot; capability to your role to manage fields.
                </Message>
            )}

            {canEdit && (
                <Button appearance="primary" label="Add field" onClick={openNew} style={{ marginBottom: 16 }} />
            )}

            {loading ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <WaitSpinner size="medium" /><Text>Loading…</Text>
                </div>
            ) : (
                <Table stripeRows>
                    <Table.Head>
                        <Table.HeadCell>Order</Table.HeadCell>
                        <Table.HeadCell>Label</Table.HeadCell>
                        <Table.HeadCell>Field id</Table.HeadCell>
                        <Table.HeadCell>Type</Table.HeadCell>
                        <Table.HeadCell>Options</Table.HeadCell>
                        <Table.HeadCell>Standard</Table.HeadCell>
                        <Table.HeadCell>Hidden</Table.HeadCell>
                        {canEdit && <Table.HeadCell>Actions</Table.HeadCell>}
                    </Table.Head>
                    <Table.Body>
                        {defs.map((d) => (
                            <Table.Row key={d._key}>
                                <Table.Cell>{d.order ?? '-'}</Table.Cell>
                                <Table.Cell>{d.label}</Table.Cell>
                                <Table.Cell>{d._key}</Table.Cell>
                                <Table.Cell>{d.type}</Table.Cell>
                                <Table.Cell>
                                    {Array.isArray(d.options) && d.options.length
                                        ? d.options.join(', ')
                                        : d.options_source
                                            ? `(${d.options_source.type}: ${d.options_source.name})`
                                            : '-'}
                                </Table.Cell>
                                <Table.Cell>{d.standard ? 'Yes' : 'No'}</Table.Cell>
                                <Table.Cell>{d.hidden ? 'Yes' : 'No'}</Table.Cell>
                                {canEdit && (
                                    <Table.Cell>
                                        <div style={{ display: 'flex', gap: 4 }}>
                                            <Tooltip content="Edit field">
                                                <Button appearance="secondary" icon={<Pencil />} onClick={() => openEdit(d)} aria-label={`Edit ${d._key}`} />
                                            </Tooltip>
                                            <Tooltip content={d.standard ? 'Reset to default' : 'Delete field'}>
                                                <Button appearance="secondary" icon={<TrashCanCross />} onClick={() => handleDelete(d)} aria-label={`Delete ${d._key}`} />
                                            </Tooltip>
                                        </div>
                                    </Table.Cell>
                                )}
                            </Table.Row>
                        ))}
                    </Table.Body>
                </Table>
            )}

            <Modal open={modalOpen} onRequestClose={() => setModalOpen(false)} closeOnClickAway={false} divider="both">
                <Modal.Header title={editingExisting ? `Edit field: ${form._key}` : 'Add field'} onRequestClose={() => setModalOpen(false)} />
                <Modal.Body style={{ minWidth: 420 }}>
                    {!editingExisting && (
                        <ControlGroup label="Field id" help="Lowercase identifier (auto-derived from the label if blank)." style={{ marginBottom: 16 }} controlsLayout="fill">
                            <Text value={form._key} onChange={(e, { value }) => setField('_key', value)} placeholder="e.g. retention_tier" style={{ width: '100%' }} />
                        </ControlGroup>
                    )}
                    <ControlGroup label="Label" style={{ marginBottom: 16 }} controlsLayout="fill">
                        <Text value={form.label} onChange={(e, { value }) => setField('label', value)} style={{ width: '100%' }} />
                    </ControlGroup>
                    <ControlGroup label="Type" style={{ marginBottom: 16 }} controlsLayout="fill">
                        <Select value={form.type} onChange={(e, { value }) => setField('type', value)} style={{ width: '100%' }}>
                            <Select.Option label="Select (customisable dropdown)" value="select" />
                            <Select.Option label="Boolean (Yes/No)" value="boolean" />
                        </Select>
                    </ControlGroup>
                    {form.type === 'select' && (
                        <ControlGroup
                            label="Options"
                            help={form.optionsSource
                                ? `Also suggests values from ${form.optionsSource.type}: ${form.optionsSource.name}.`
                                : 'Comma-separated suggestions. Users can still type free text.'}
                            style={{ marginBottom: 16 }}
                            controlsLayout="fill"
                        >
                            <Text value={form.options} onChange={(e, { value }) => setField('options', value)} placeholder="e.g. Hot, Warm, Cold" style={{ width: '100%' }} />
                        </ControlGroup>
                    )}
                    <ControlGroup label="Order" help="Lower numbers appear first." style={{ marginBottom: 16 }} controlsLayout="fill">
                        <Text value={String(form.order ?? '')} onChange={(e, { value }) => setField('order', value.replace(/[^0-9]/g, ''))} style={{ width: '100%' }} />
                    </ControlGroup>
                    <ControlGroup label="Hidden" help="Hide this field from the catalogue editor without deleting it." style={{ marginBottom: 4 }} controlsLayout="fill">
                        <Switch selected={form.hidden} onClick={() => setField('hidden', !form.hidden)} appearance="toggle" />
                    </ControlGroup>
                </Modal.Body>
                <Modal.Footer>
                    <Button appearance="secondary" label="Cancel" onClick={() => setModalOpen(false)} disabled={saving} />
                    <Button appearance="primary" label={saving ? 'Saving…' : 'Save'} onClick={handleSave} disabled={saving} />
                </Modal.Footer>
            </Modal>
        </div>
    );
}
