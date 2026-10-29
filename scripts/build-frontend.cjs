/* The active frontend has one build entry; legacy app.css is deliberately untouched. */
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
execFileSync(process.execPath,['scripts/build-assets.cjs'],{stdio:'inherit'});
execFileSync(process.execPath,['node_modules/@tailwindcss/cli/dist/index.mjs','-i','app/static/css/frontend/input.css','-o','app/static/css/frontend/utilities.css','--minify'],{stdio:'inherit'});
for(const path of ['app/static/css/frontend','app/static/js/frontend']){
  if(!fs.readdirSync(path).length)throw new Error(`Frontend directory is empty: ${path}`);
}
console.log('V1 refactored frontend assets built; legacy UI files are not part of the page manifest.');
