import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';
await build({entryPoints:['cloud/client.js'],bundle:true,format:'iife',target:'es2022',outfile:'cloud/bundle.js',minify:true,legalComments:'eof'});
// Preserve the bundled SDK's whitespace alphabet without a trailing tab in the generated file.
const bundle=readFileSync('cloud/bundle.js','utf8');
writeFileSync('cloud/bundle.js',bundle.replace('ks=` \t\n\\r=`','ks=` \\t\n\\r=`'));
