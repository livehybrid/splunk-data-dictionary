import React from 'react';
import Heading from '@splunk/react-ui/Heading';
import Link from '@splunk/react-ui/Link';
import Paragraph from '@splunk/react-ui/Paragraph';
import Table from '@splunk/react-ui/Table';

// The MCP tools - what an agent calls. `ping` runs an SPL template; `query` and
// `index_metadata` are API tools: the Splunk MCP Server proxies a GET to this
// app's own REST handlers, which return a flat row array of catalog + merged
// governance metadata (standard + custom fields).
const MCP_TOOLS = [
    {
        name: 'data_dictionary_index_metadata',
        answers:
            'Governance & ownership for a named index - who owns it, who to get access sign-off from, security/service owner, escalation contacts, PII status, classification, per sourcetype.',
        execution: 'API → GET /services/data_dictionary/dictionary/index/<index>?flat=1',
    },
    {
        name: 'data_dictionary_query',
        answers:
            'Search across ALL indexes/sourcetypes by keyword to find data and its owners/PII/classification (e.g. "who owns the cultivar data?").',
        execution: 'API → GET /services/data_dictionary/dictionary/query?flat=1 (q, index, sourcetype, limit)',
    },
    {
        name: 'data_dictionary_ping',
        answers: 'Health check - confirms the catalog lookup is reachable and returns its row count.',
        execution: 'SPL → | inputlookup data_dictionary_catalog | stats count',
    },
];

// The REST API - persistent handlers the in-app React UI calls. These are HTTP
// endpoints (restmap.conf); they are NOT how the MCP tools execute.
const REST_ENDPOINTS = [
    { method: 'GET', path: '/data_dictionary/ping', summary: 'Health check for the app REST stack.' },
    { method: 'GET', path: '/data_dictionary/discovery/catalog', summary: 'Catalog rows (index, sourcetype) from the lookup.' },
    { method: 'GET', path: '/data_dictionary/discovery/indexes', summary: 'Indexes via Splunk REST.' },
    { method: 'GET', path: '/data_dictionary/discovery/sourcetypes', summary: 'Sourcetypes via Splunk REST.' },
    { method: 'GET / POST / DELETE', path: '/data_dictionary/metadata[/<key>]', summary: 'List / get / upsert / delete governance metadata in the KV store. Writes need edit_data_dictionary.' },
    { method: 'GET / POST / DELETE', path: '/data_dictionary/field-defs[/<key>]', summary: 'Standard + custom field definitions. Writes need edit_data_dictionary.' },
    { method: 'GET', path: '/data_dictionary/dictionary/index/<index>', summary: 'Catalog + merged governance metadata for one index (flat=1 for the MCP api tool).' },
    { method: 'GET', path: '/data_dictionary/dictionary/query', summary: 'Search the catalog with merged metadata (q, index, sourcetype, limit, offset; flat=1 for the MCP api tool).' },
    { method: 'GET', path: '/data_dictionary/options', summary: 'Option lists for the edit-form dropdowns (macro / lookup).' },
    { method: 'GET', path: '/data_dictionary/permissions', summary: 'Current user: username, roles, can_edit (drives the UI edit controls).' },
    { method: 'POST', path: '/data_dictionary/build-catalog', summary: 'Dispatch the "Data Dictionary - Build Catalog" saved search. Needs edit_data_dictionary.' },
];

const styles = {
    page: { padding: 24, maxWidth: 1040 },
    section: {
        background: 'rgba(128, 128, 128, 0.10)',
        border: '1px solid rgba(128, 128, 128, 0.30)',
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
    },
    sectionTitle: { marginBottom: 8 },
    codeInline: {
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        fontSize: 12,
        background: 'rgba(128, 128, 128, 0.16)',
        border: '1px solid rgba(128, 128, 128, 0.35)',
        borderRadius: 4,
        padding: '1px 6px',
    },
    compactParagraph: { marginBottom: 10, lineHeight: 1.6 },
    bulletList: { margin: '0 0 12px 18px', padding: 0, lineHeight: 1.55 },
};

function InlineCode({ children }) {
    return <span style={styles.codeInline}>{children}</span>;
}

export default function McpToolsDocs() {
    return (
        <div style={styles.page}>
            <Heading level={2} style={{ marginBottom: 8 }}>
                AI and Splunk MCP tools
            </Heading>
            <Paragraph style={{ marginBottom: 16, maxWidth: 900 }}>
                How this app exposes the Data Dictionary to AI agents as Splunk MCP tools, how those
                tools actually run, and the REST API the in-app UI uses.
            </Paragraph>

            <div style={styles.section}>
                <Heading level={3} style={styles.sectionTitle}>
                    How the MCP tools work
                </Heading>
                <Paragraph style={styles.compactParagraph}>
                    The app ships its tool definitions in{' '}
                    <InlineCode>appserver/static/tool_input_payload_signatures.json</InlineCode> (the single
                    source of truth), declared restmap-side in <InlineCode>default/tools.conf</InlineCode>.
                    On <strong>Splunk Cloud</strong> they register automatically on install (a native
                    synced-apps registrar reads <InlineCode>tools.conf</InlineCode>). On{' '}
                    <strong>Splunk Enterprise</strong> the app self-registers via{' '}
                    <InlineCode>bin/autoregister.py</InlineCode> - fired by an{' '}
                    <InlineCode>app.conf</InlineCode> reload trigger on install - which upserts the tools into
                    the Splunk MCP Server&apos;s <InlineCode>mcp_tools</InlineCode> KV Store collection.
                    (<InlineCode>deploy/register_mcp_tools.py</InlineCode> remains as a manual one-shot.)
                </Paragraph>
                <ul style={styles.bulletList}>
                    <li>
                        <InlineCode>data_dictionary_ping</InlineCode> runs a small <strong>SPL</strong> template
                        against the catalog lookup - pure <InlineCode>| inputlookup</InlineCode> with
                        no <InlineCode>| rest</InlineCode>, so it is safe inside the MCP search sandbox.
                    </li>
                    <li>
                        <InlineCode>data_dictionary_query</InlineCode> and{' '}
                        <InlineCode>data_dictionary_index_metadata</InlineCode> are <strong>API</strong> tools:
                        the MCP Server proxies a <InlineCode>GET</InlineCode> to this app&apos;s REST handlers
                        (the <InlineCode>/dictionary/*</InlineCode> endpoints below) with{' '}
                        <InlineCode>flat=1</InlineCode>, which return a flat row array of catalog + merged
                        governance metadata - so <strong>standard and custom fields</strong> flow through.
                    </li>
                    <li>
                        The agent sees each tool&apos;s name, description and input schema, calls it by name,
                        and gets the rows back. All three tools are <strong>read-only</strong>; editing
                        metadata requires the <InlineCode>edit_data_dictionary</InlineCode> capability.
                    </li>
                </ul>
            </div>

            <Heading level={3} style={{ marginBottom: 12 }}>
                Registered MCP tools
            </Heading>
            <Paragraph style={{ marginBottom: 10 }}>
                What each tool answers and how it executes:
            </Paragraph>
            <Table stripeRows>
                <Table.Head>
                    <Table.HeadCell>MCP tool</Table.HeadCell>
                    <Table.HeadCell>What it answers</Table.HeadCell>
                    <Table.HeadCell>Execution</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {MCP_TOOLS.map((t) => (
                        <Table.Row key={t.name}>
                            <Table.Cell>
                                <InlineCode>{t.name}</InlineCode>
                            </Table.Cell>
                            <Table.Cell>{t.answers}</Table.Cell>
                            <Table.Cell>
                                <InlineCode>{t.execution}</InlineCode>
                            </Table.Cell>
                        </Table.Row>
                    ))}
                </Table.Body>
            </Table>

            <Heading level={3} style={{ marginBottom: 12, marginTop: 24 }}>
                REST API (used by the in-app UI)
            </Heading>
            <Paragraph style={{ marginBottom: 10, maxWidth: 900 }}>
                The app exposes persistent REST handlers (<InlineCode>restmap.conf</InlineCode>) that the
                React UI calls - and that the <InlineCode>query</InlineCode> /{' '}
                <InlineCode>index_metadata</InlineCode> MCP tools proxy to (the{' '}
                <InlineCode>/dictionary/*</InlineCode> routes). Writes (metadata, field-defs, build-catalog)
                require the <InlineCode>edit_data_dictionary</InlineCode> capability. Paths are app-scoped, e.g.{' '}
                <InlineCode>/servicesNS/nobody/data_dictionary/data_dictionary/ping</InlineCode>.
            </Paragraph>
            <Table stripeRows>
                <Table.Head>
                    <Table.HeadCell>HTTP</Table.HeadCell>
                    <Table.HeadCell>App REST path</Table.HeadCell>
                    <Table.HeadCell>Description</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {REST_ENDPOINTS.map((r) => (
                        <Table.Row key={r.path}>
                            <Table.Cell>{r.method}</Table.Cell>
                            <Table.Cell>
                                <InlineCode>{r.path}</InlineCode>
                            </Table.Cell>
                            <Table.Cell>{r.summary}</Table.Cell>
                        </Table.Row>
                    ))}
                </Table.Body>
            </Table>

            <div style={{ ...styles.section, marginTop: 16 }}>
                <Heading level={3} style={styles.sectionTitle}>
                    REST path mapping (the usual gotcha)
                </Heading>
                <Paragraph style={{ ...styles.compactParagraph, marginBottom: 0 }}>
                    For the REST API, do not infer the URL from the <InlineCode>restmap.conf</InlineCode> stanza
                    name - the HTTP URL is the stanza&apos;s <InlineCode>match =</InlineCode> path. Example:{' '}
                    <InlineCode>[script:dictionary_query]</InlineCode> with{' '}
                    <InlineCode>match = /data_dictionary/dictionary/query</InlineCode> is called on{' '}
                    <InlineCode>/data_dictionary/dictionary/query</InlineCode>, not{' '}
                    <InlineCode>/services/dictionary_query</InlineCode>.
                </Paragraph>
            </div>

            <Paragraph>
                <Link to="/app/data_dictionary/home" appearance="standalone">
                    Back to Data Dictionary catalog
                </Link>
            </Paragraph>
        </div>
    );
}
