const fs = require('node:fs');
fs.mkdirSync('app/static/vendor', { recursive: true });
fs.copyFileSync('node_modules/htmx.org/dist/htmx.min.js', 'app/static/vendor/htmx.min.js');
fs.copyFileSync('node_modules/@alpinejs/csp/dist/cdn.min.js', 'app/static/vendor/alpine.min.js');
