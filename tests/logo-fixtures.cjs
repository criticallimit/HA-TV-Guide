/* Offline counterpart of the authenticated app's public database image endpoint. */
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const root=execFileSync(process.env.PYTHON||'python',['tests/stage_logo_fixtures.py'],{encoding:'utf8'}).trim();
module.exports=function serveLogo(url,res){
  if(!url.pathname.startsWith('/tv_guide/logo/'))return false;
  const source=decodeURIComponent(url.pathname.slice('/tv_guide/logo/'.length));
  const file=path.resolve(root,source);
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return true;}
  res.setHeader('Content-Type','image/svg+xml');res.end(fs.readFileSync(file));return true;
};
