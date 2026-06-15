module.exports = {
    root: true,
    parserOptions: {
        ecmaVersion: 2021,
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
    },
    env: { browser: true, es2021: true, node: true },
    extends: ['eslint:recommended'],
    plugins: [],
    settings: { react: { version: '18' } },
    rules: {
        'no-unused-vars': 'warn',
        'no-console': 'off',
    },
    globals: { module: 'readonly', require: 'readonly', process: 'readonly' },
    overrides: [
        {
            files: ['*.jsx'],
            rules: { 'no-undef': 'off' },
        },
    ],
};
