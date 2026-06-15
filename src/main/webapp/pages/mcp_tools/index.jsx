import React from 'react';
import layout from '@splunk/react-page';
import { getUserTheme } from '@splunk/splunk-utils/themes';
import McpToolsDocs from './McpToolsDocs';

// layout() renders the full Splunk Web page chrome (header + app nav bar) around
// the component, using the __splunkd_partials__ the view template injects.
getUserTheme()
    .then((theme) => {
        layout(<McpToolsDocs />, { theme });
    })
    .catch((e) => {
        const el = document.createElement('div');
        el.textContent = `Failed to load theme: ${e}`;
        document.body.appendChild(el);
    });
