const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', 'node_modules/*', '.expo/*'],
  },
  {
    rules: {
      // Apostrophes in <Text> render fine in React Native; this rule is web-oriented.
      'react/no-unescaped-entities': 'off',
      'import/no-duplicates': 'off',
    },
  },
]);
