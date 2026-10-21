// ESLint flat config (ESLint 9+). Same rules as the old .eslintrc.js.
const js = require('@eslint/js');
const globals = require('globals');

module.exports = [
    { ignores: ['node_modules/**', 'stage/**', 'build/**', 'dist/**', 'output/**'] },
    js.configs.recommended,
    {
        files: ['src/**/*.{js,jsx}'],
        languageOptions: {
            ecmaVersion: 2021,
            sourceType: 'module',
            parserOptions: { ecmaFeatures: { jsx: true } },
            globals: { ...globals.browser, ...globals.node },
        },
        rules: {
            'no-unused-vars': 'warn',
            'no-console': 'off',
        },
    },
    {
        // No eslint-plugin-react, so JSX references are invisible to no-undef.
        files: ['**/*.jsx'],
        rules: { 'no-undef': 'off' },
    },
];
