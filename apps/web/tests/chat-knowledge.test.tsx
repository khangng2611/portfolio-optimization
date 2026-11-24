import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ChatKnowledge, KnowledgeSources } from '../src/components/chat-workspace';
import { readPending, type KnowledgeEvidence } from '../src/lib/chat-types';
const evidence: KnowledgeEvidence = { corpus_id:'corpus', corpus_version:'knowledge-vi-v1', corpus_hash:'a'.repeat(64), evidence_hash:'b'.repeat(64), mode:'LEXICAL', status:'REFERENCE', reason:'MATCH', citations:[{ chunk_id:'chunk', document_version_id:'document', document_version:1, claim_id:'ew-definition', text:'EW chia đều tỷ trọng <script>alert(1)</script>', text_hash:'c'.repeat(64), source_title:'Tài liệu EW', source_url:'https://example.org/ew', locator:'EW', available_at:'2026-11-07T00:00:00Z', published_at:null }] };
it('renders each reference and its source once without internal corpus metadata', () => {
 const html=renderToStaticMarkup(<ChatKnowledge evidence={evidence}/>);
 expect(html.match(/EW chia đều tỷ trọng/g)).toHaveLength(1);expect(html).not.toContain('knowledge-vi-v1');expect(html).not.toContain(evidence.evidence_hash);expect(html).not.toContain('<script>');expect(html).not.toContain('confidence');
 expect(html).toContain('Nguồn tham khảo');expect(html).toContain('rel="noopener noreferrer"');
});
it('never makes unsafe source URLs clickable and leaves text escaped',()=>{
 const html=renderToStaticMarkup(<KnowledgeSources evidence={{...evidence,citations:[{...evidence.citations[0],source_url:'javascript:alert(1)'}]}}/>);
 expect(html).not.toContain('href="javascript:');expect(html).toContain('Tài liệu EW');
});
it('retains knowledge pending intent across reconnect',()=>{
 const body={content:'EW là gì?',client_message_id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',intent:'knowledge'};
 expect(readPending(JSON.stringify(body))).toEqual(body);
});
