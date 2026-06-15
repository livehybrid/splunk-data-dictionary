import React from 'react';
import Heading from '@splunk/react-ui/Heading';
import Link from '@splunk/react-ui/Link';
import Paragraph from '@splunk/react-ui/Paragraph';
import Table from '@splunk/react-ui/Table';

// The MCP tools — what an agent calls. These EXECUTE AS SPL (not by calling the
// REST API): the Splunk MCP Server runs each tool's SPL template against the
// catalog lookup overlaid with governance metadata.
const MCP_TOOLS = [
    {
        name: 'data_dictionary_index_metadata',
        answers:
            'Governance & ownership for a named index — who owns it, who to get access sign-off from, security/service owner, escalation contacts, PII status, classification, per sourcetype.',
        spl: '| inputlookup data_dictionary_catalog (filtered to the index) | lookup data_dictionary_metadata (row / index / sourcetype overlays)',
    },
    {
        name: 'data_dictionary_query',
        answers:
            'Search across ALL indexes/sourcetypes by keyword to find data and its owners/PII/classification (e.g. "who owns the cultivar data?").',
        spl: '| inputlookup data_dictionary_catalog | lookup data_dictionary_metadata | where keyword matches index, sourcetype, or any governance field',
    },
    {
        name: 'data_dictionary_ping',
        answers: 'Health check — confirms the catalog lookup is reachable and returns its row count.',
        spl: '| inputlookup data_dictionary_catalog | stats count',
    },
];

// The REST API — persistent handlers the in-app React UI calls. These are HTTP
// endpoints (restmap.conf); they are NOT how the MCP tools execute.
const REST_ENDPOINTS = [
    { method: 'GET', path: '/data_dictionary/ping', summary: 'Health check for the app REST stack.' },
    { method: 'GET', path: '/data_dictionary/discovery/catalog', summary: 'Catalog rows (index, sourcetype) from the lookup.' },
    { method: 'GET', path: '/data_dictionary/discovery/indexes', summary: 'Indexes via Splunk REST.' },
    { method: 'GET', path: '/data_dictionary/discovery/sourcetypes', summary: 'Sourcetypes via Splunk REST.' },
    { method: 'GET / POST / DELETE', path: '/data_dictionary/metadata[/<key>]', summary: 'List / get / upsert / delete governance metadata in the KV store.' },
    { method: 'GET', path: '/data_dictionary/dictionary/index/<index>', summary: 'Catalog + merged governance metadata for one index.' },
    { method: 'GET', path: '/data_dictionary/dictionary/query', summary: 'Search the catalog with merged metadata (q, index, sourcetype, limit, offset).' },
    { method: 'GET', path: '/data_dictionary/options', summary: 'Option lists for the edit-form dropdowns (macro / lookup).' },
    { method: 'POST', path: '/data_dictionary/build-catalog', summary: 'Dispatch the "Data Dictionary - Build Catalog" saved search.' },
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
                    The app ships tool definitions in{' '}
                    <InlineCode>appserver/static/tool_input_payload_signatures.json</InlineCode>. The Splunk
                    MCP Server <strong>automatically imports</strong> them into its{' '}
                    <InlineCode>mcp_tools</InlineCode> KV Store collection — there is no manual registration.
                </Paragraph>
                <ul style={styles.bulletList}>
                    <li>
                        Each tool <strong>executes as SPL</strong> against the Data Dictionary&apos;s catalog
                        lookup (<InlineCode>data_dictionary_catalog</InlineCode>) overlaid with governance
                        metadata from the <InlineCode>data_dictionary_metadata</InlineCode> KV lookup —
                        pure <InlineCode>| inputlookup</InlineCode> / <InlineCode>| lookup</InlineCode>, with
                        no <InlineCode>| rest</InlineCode>, so it is safe inside the MCP search sandbox.
                    </li>
                    <li>
                        The agent sees each tool&apos;s name, description and input schema, calls it by name,
                        and the MCP Server runs the SPL and returns the rows. The tools are
                        read-only.
                    </li>
                    <li>
                        Tool identity and the SPL template live in the signature JSON, <em>not</em> in the
                        REST API below — the two are independent.
                    </li>
                </ul>
            </div>

            <Heading level={3} style={{ marginBottom: 12 }}>
                Registered MCP tools
            </Heading>
            <Paragraph style={{ marginBottom: 10 }}>
                What each tool answers and the SPL it runs:
            </Paragraph>
            <Table stripeRows>
                <Table.Head>
                    <Table.HeadCell>MCP tool</Table.HeadCell>
                    <Table.HeadCell>What it answers</Table.HeadCell>
                    <Table.HeadCell>Execution (SPL)</Table.HeadCell>
                </Table.Head>
                <Table.Body>
                    {MCP_TOOLS.map((t) => (
                        <Table.Row key={t.name}>
                            <Table.Cell>
                                <InlineCode>{t.name}</InlineCode>
                            </Table.Cell>
                            <Table.Cell>{t.answers}</Table.Cell>
                            <Table.Cell>
                                <InlineCode>{t.spl}</InlineCode>
                            </Table.Cell>
                        </Table.Row>
                    ))}
                </Table.Body>
            </Table>

            <Heading level={3} style={{ marginBottom: 12, marginTop: 24 }}>
                REST API (used by the in-app UI)
            </Heading>
            <Paragraph style={{ marginBottom: 10, maxWidth: 900 }}>
                The app also exposes persistent REST handlers (<InlineCode>restmap.conf</InlineCode>) that the
                React UI calls. These are HTTP endpoints — <strong>not</strong> how the MCP tools execute —
                but they are available for direct integration. Paths are app-scoped, e.g.{' '}
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
                    name — the HTTP URL is the stanza&apos;s <InlineCode>match =</InlineCode> path. Example:{' '}
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
