import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ChatConfirmation, ChatRecommendation, ChatWorkspace } from '../src/components/chat-workspace';
import type { ConfirmationCard, RecommendationCard } from '../src/lib/chat-types';
import type { Recommendation } from '../src/lib/portfolio-types';

const canonical: Recommendation = { id: 'recommendation', portfolio_id: 'portfolio', portfolio_version: 3, asset_ids: ['FPT', 'VCB'], weights: ['0.5', '0.5'], capital_vnd: '100000000', strategy: 'MVO', bundle_hash: 'original', inputs_provenance: { data_origin: 'real' } };
const card: RecommendationCard = { type: 'recommendation', recommendation_id: canonical.id, facts: { ...canonical }, facts_hash: 'a'.repeat(64), explanation_status: 'TEMPLATE', provider: { reason: 'PROVIDER_UNAVAILABLE' }, schema_version: 'fact-plan-v1', prompt_version: 'chat-v1' };

it('keeps provider configuration out of the conversation composer', () => {
  const unavailable = async () => { throw new Error('SSR must not fetch'); };
  const html = renderToStaticMarkup(<ChatWorkspace api={unavailable} apiPage={unavailable} route={{ view:'chat', conversationId:'test-conversation' }} navigate={() => {}} ownerKey="alice" onSessionExpired={() => {}}/>);
  expect(html).toContain('chat-input');
  expect(html).toContain('Tùy chọn hội thoại');
  expect(html).not.toContain('chat-llm-consent');
  expect(html).not.toContain('Dữ liệu gửi tới OpenAI');
  expect(html).not.toContain('Cho phép OpenAI');
});

it('withholds stored prose and allocation until canonical API facts are available', () => {
  const html = renderToStaticMarkup(<ChatRecommendation card={card} canonical={undefined} content="Stored claim 99%"/>);
  expect(html).toContain('Đang đối chiếu');
  expect(html).not.toContain('99%');
  expect(html).not.toContain('chat-open-recommendation');
});

it('withholds evidence-derived saved prose after an evidence mismatch', () => {
  const saved = { schema_version: 'recommendation-evidence-v1', recommendation_id: canonical.id, run_id: 'run', facts_hash: card.facts_hash, evidence_hash: 'b'.repeat(64), status: 'PARTIAL', quant: null, limitations: [] } as const;
  const html = renderToStaticMarkup(<ChatRecommendation card={{ ...card, facts: {...canonical, run_id:'run'}, explanation_evidence: { ...saved, limitations: [] } }} canonical={{...canonical, run_id:'run'}} evidence={{...saved, evidence_hash:'c'.repeat(64),limitations:[]}} content="SECRET_SAVED_EVIDENCE_CLAIM"/>);
  expect(html).toContain('chưa khớp');
  expect(html).not.toContain('SECRET_SAVED_EVIDENCE_CLAIM');
  expect(html).toContain('Phân bổ chính');
});
it('rejects a provenance mismatch before rendering a result/action', () => {
  const html = renderToStaticMarkup(<ChatRecommendation card={card} canonical={{ ...canonical, bundle_hash: 'changed' }} content="Stored claim"/>);
  expect(html).toContain('chưa khớp');
  expect(html).not.toContain('Stored claim');
  expect(html).not.toContain('chat-result');
});
it('renders fresh canonical allocation and a proposal link without accepting in chat', () => {
  const html = renderToStaticMarkup(<ChatRecommendation card={card} canonical={canonical} content="Tỷ trọng từ kết quả định lượng."/>);
  expect(html).toContain('FPT');
  expect(html).toContain('50,0%');
  expect(html).toContain('#proposal?portfolio=portfolio&amp;proposal=recommendation');
  expect(html).toContain('chat-open-recommendation');
  expect(html).not.toContain('/accept');
  expect(html).toContain('Giải thích theo mẫu dữ liệu');
});
it('reviews pinned risk answers/constraints and disables historical confirmation', () => {
  const confirmation: ConfirmationCard = { type: 'confirmation', reason: 'CONFIRM_INPUT', confirmation_message_id: 'message', facts_hash: 'b'.repeat(64), input: { strategy: 'MVO', portfolio: { id: 'portfolio', name: 'Kế hoạch dài hạn', capital_vnd: '100000000', universe_id: 'REAL', version: 3, policy_version_id: 'policy-v3', constraints: { risk_aversion: 6, max_position_weight: .5, min_defensive_weight: .2 }, risk_profile: { profile: 'conservative', version_id: 'risk-v3', answers: { horizon_months: 60, liquidity_need: 'high', loss_tolerance: 'low', experience: 'beginner' } } } } };
  const html = renderToStaticMarkup(<ChatConfirmation card={confirmation} disabled onConfirm={() => {}}/>);
  expect(html).toContain('Kế hoạch dài hạn');
  expect(html).toContain('Thận trọng');
  expect(html).toContain('60 tháng');
  expect(html).toContain('20%');
  expect(html).toMatch(/data-testid="chat-confirm" disabled=""/);
  expect(html).toContain('policy-v3');
});

it('opens the explanation when the user asks about a previous recommendation', () => {
  const html = renderToStaticMarkup(<ChatRecommendation card={{...card, explanation_requested:true}} canonical={canonical} content="Giải thích đúng đề xuất đang trao đổi."/>);
  expect(html).toMatch(/class="chat-explanation"[^>]*open=""/);
  expect(html).toContain('Giải thích đúng đề xuất đang trao đổi.');
  const original = renderToStaticMarkup(<ChatRecommendation card={card} canonical={canonical} content="Giải thích ban đầu."/>);
  expect(original).not.toMatch(/class="chat-explanation"[^>]*open=""/);
});
