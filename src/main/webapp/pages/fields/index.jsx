import React from 'react';
import layout from '@splunk/react-page';
import { getUserTheme } from '@splunk/splunk-utils/themes';
import FieldsAdmin from './FieldsAdmin';

// layout() renders the full Splunk Web page chrome around the component.
getUserTheme()
    .then((theme) => {
        layout(<FieldsAdmin />, { theme });
    })
    .catch((e) => {
        const el = document.createElement('div');
        el.textContent = `Failed to load theme: ${e}`;
        document.body.appendChild(el);
    });
