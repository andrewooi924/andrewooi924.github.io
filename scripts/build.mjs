import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';
await build({entryPoints:['cloud/client.js'],bundle:true,format:'iife',target:'es2022',outfile:'cloud/bundle.js',minify:true,legalComments:'eof'});
// Preserve the bundled SDK's whitespace alphabet without trailing whitespace in generated lines.
const bundle=readFileSync('cloud/bundle.js','utf8');
writeFileSync('cloud/bundle.js',bundle.replace(/=` \t\n\\r=/g,match=>match.replace('\t','\\t').replace('\n','\\n')));
