import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {marked} from '/Users/nguyenkhang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked/lib/marked.esm.js';

const root='/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization';
const out=path.join(root,'outputs/step1/paper_period/google_doc_submission_20261007');
await fs.mkdir(out,{recursive:true});
const source=path.join(root,'outputs/step1/Step1_Submission_20261007/00_Step1_Report.md');
const md=await fs.readFile(source,'utf8');
const images=[];
let html=marked.parse(md,{gfm:true});
html=html.replace(/<img src="([^"]+)" alt="([^"]*)"\s*\/?\s*>/g,(_,src,alt)=>{
  const marker=`STEP1FIGURE${images.length+1}`;
  images.push({marker,path:src,caption:alt});
  return `<span>${marker}</span>`;
});
// Local file paths do not resolve for a lecturer reading Google Docs. Preserve
// their visible reference labels; keep actual public web links clickable.
html=html.replace(/<a href="(?!https?:)[^"]+">([\s\S]*?)<\/a>/g,'$1');
const normal='font-family:Times New Roman;font-size:11pt;font-weight:normal;color:#000;line-height:1.15;margin-top:0;margin-bottom:6pt;';
html=html.replace(/<pre><code(?: class="[^"]*")?>([\s\S]*?)<\/code><\/pre>/g,(_,text)=>`<p style="${normal}font-family:Courier New;font-size:8.5pt;">${text.trimEnd().replace(/\n/g,'<br>')}</p>`);
html=html.replace(/<p>/g,`<p style="${normal}">`);
html=html.replace(/<h1>/g,'<h1 style="font-family:Times New Roman;font-size:18pt;font-weight:bold;color:#000;margin-bottom:12pt;">');
html=html.replace(/<h2>/g,'<h2 style="font-family:Times New Roman;font-size:14pt;font-weight:bold;color:#000;margin-top:12pt;margin-bottom:6pt;">');
html=html.replace(/<h3>/g,'<h3 style="font-family:Times New Roman;font-size:12pt;font-weight:bold;color:#000;margin-top:8pt;margin-bottom:4pt;">');
html=html.replace(/<code>/g,'<code style="font-family:Courier New;font-size:9pt;color:#000;">');
html=html.replace(/<table>/g,'<table border="1" cellpadding="3" cellspacing="0" style="width:100%;border-collapse:collapse;border-color:#d9d9d9;font-family:Times New Roman;font-size:10pt;">');
html=html.replace(/<th([^>]*)>([\s\S]*?)<\/th>/g,(_,attr,text)=>`<th${attr} style="border:1px solid #d9d9d9;"><p style="${normal}font-size:10pt;font-weight:bold;margin:0;">${text}</p></th>`);
html=html.replace(/<td([^>]*)>([\s\S]*?)<\/td>/g,(_,attr,text)=>`<td${attr} style="border:1px solid #d9d9d9;"><p style="${normal}font-size:10pt;margin:0;">${text}</p></td>`);
html=html.replace(/<li>/g,`<li style="${normal}">`);
const complete=`<html><head><meta charset="utf-8"></head><body style="${normal}">${html}</body></html>`;
await fs.writeFile(path.join(out,'full_report.html'),complete);
await fs.writeFile(path.join(out,'publication_source.json'),JSON.stringify({
  source,source_sha256:createHash('sha256').update(md).digest('hex'),
  target:'https://docs.google.com/document/d/17Hzm6ND3ZB8UioSkeqZVP3ysJEpQslEaDxTwwPXBKKw/edit?tab=t.0',
  published_date:'2026-10-07',images,
  table_count:(html.match(/<table /g)||[]).length,
  main_sections:(md.match(/^## \d+\./gm)||[]).length,
  notes:'Condensed thirteen-section report with standardized attachment names and inventory; three original NAV images. All empirical tables unchanged. No run changed.'
},null,2));
console.log(JSON.stringify({html_characters:complete.length,tables:(html.match(/<table /g)||[]).length,images,main_sections:13}));
