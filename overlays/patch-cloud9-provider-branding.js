const fs = require('node:fs');
const path = require('node:path');
const root = '/app/.build/next';
const source = 'name:"llama.cpp",icon:"memory"';
const target = 'name:"Cloud9 Engine",iconUrl:"/providers/cloud9-assets/cloud9-engine.png",icon:"memory"';
let total = 0, client = 0, server = 0, already = 0;
function visit(dir) {
  if (!fs.existsSync(dir)) return;
  for (const e of fs.readdirSync(dir, {withFileTypes:true})) {
    const p=path.join(dir,e.name);
    if(e.isDirectory()) {visit(p);continue;}
    if(!e.isFile()||!e.name.endsWith('.js'))continue;
    const text=fs.readFileSync(p,'utf8');
    if(text.includes(target))already++;
    if(!text.includes(source))continue;
    const found=text.split(source).length-1;
    const replaced=text.split(source).join(target);
    fs.writeFileSync(p,replaced);
    total+=found;
    if(p.includes('/static/'))client+=found;
    else server+=found;
  }
}
visit(path.join(root,'static','chunks'));
visit(path.join(root,'server','chunks'));
if((client<1||server<1) && already===0)throw new Error('Cloud9 Engine built-in icon patch signature missing (expected client and server)');
console.log('Cloud9-branding', {total,client,server,already});
