import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ChatConfirmation, ChatRecommendation, ChatWorkspace, QuoteHistoryLink, ReadFacts } from '../src/components/chat-workspace';
import type { ConfirmationCard, RecommendationCard } from '../src/lib/chat-types';
import type { Recommendation } from '../src/lib/portfolio-types';

const canonical: Recommendation = { id: 'recommendation', portfolio_id: 'portfolio', portfolio_version: 3, asset_ids: ['FPT', 'VCB'], weights: ['0.5', '0.5'], capital_vnd: '100000000', strategy: 'MVO', bundle_hash: 'original', inputs_provenance: { data_origin: 'real' } };
const card: RecommendationCard = { type: 'recommendation', recommendation_id: canonical.id, facts: { ...canonical }, facts_hash: 'a'.repeat(64), explanation_status: 'TEMPLATE', provider: { reason: 'PROVIDER_UNAVAILABLE' }, schema_version: 'fact-plan-v1', prompt_version: 'chat-v1' };

it('shows the composer shortcuts without purpose or provider controls', () => {
  const unavailable = async () => { throw new Error('SSR must not fetch'); };
  const html = renderToStaticMarkup(<ChatWorkspace api={unavailable} apiPage={unavailable} route={{ view:'chat', conversationId:'test-conversation' }} navigate={() => {}} ownerKey="alice" onSessionExpired={() => {}}/>);
  expect(html).toContain('chat-input');
  expect(html).not.toContain('Tùy chọn hội thoại');
  expect(html).not.toContain('Mục đích');
  expect(html).toContain('Enter để gửi · ⌘ + Enter để xuống dòng');
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
  expect(html).toContain('Biểu đồ tỷ trọng theo tài sản');
  expect(html).toContain('width:50%');
  expect(html).toContain('#proposal?portfolio=portfolio&amp;proposal=recommendation');
  expect(html).toContain('chat-open-recommendation');
  expect(html).not.toContain('/accept');
  expect(html).toContain('Đề xuất đã lưu');
  expect(html).not.toContain('PROVIDER_UNAVAILABLE');
});
it('reviews pinned risk answers/constraints and disables historical confirmation', () => {
  const confirmation: ConfirmationCard = { type: 'confirmation', reason: 'CONFIRM_INPUT', confirmation_message_id: 'message', facts_hash: 'b'.repeat(64), input: { strategy: 'MVO', portfolio: { id: 'portfolio', name: 'Kế hoạch dài hạn', capital_vnd: '100000000', universe_id: 'USER_SELECTED', version: 3, policy_version_id: 'policy-v3', constraints: { risk_aversion: 6, max_position_weight: .5, min_defensive_weight: .2 }, risk_profile: { profile: 'conservative', version_id: 'risk-v3', answers: { questionnaire_version: 'risk-v1', horizon_months: 60, liquidity_need: 'high', loss_tolerance: 'low', experience: 'beginner' } } } } };
  const html = renderToStaticMarkup(<ChatConfirmation card={confirmation} disabled onConfirm={() => {}}/>);
  expect(html).toContain('Kế hoạch dài hạn');
  expect(html).toContain('Thận trọng');
  expect(html).toContain('60 tháng');
  expect(html).toContain('20%');
  expect(html).toMatch(/data-testid="chat-confirm" disabled=""/);
  expect(html).toContain('Tài sản bạn chọn');
  expect(html).not.toMatch(/USER_SELECTED|policy-v3|risk-v3/);
  expect(html).not.toContain(confirmation.facts_hash);
});

it('opens the explanation when the user asks about a previous recommendation', () => {
  const html = renderToStaticMarkup(<ChatRecommendation card={{...card, explanation_requested:true}} canonical={canonical} content="Giải thích đúng đề xuất đang trao đổi."/>);
  expect(html).toMatch(/class="chat-explanation"[^>]*open=""/);
  expect(html).toContain('Giải thích đúng đề xuất đang trao đổi.');
  const original = renderToStaticMarkup(<ChatRecommendation card={card} canonical={canonical} content="Giải thích ban đầu."/>);
  expect(original).not.toMatch(/class="chat-explanation"[^>]*open=""/);
});

it('shows a verified concise answer before closed detailed evidence', () => {
  const current = { ...canonical, run_id: 'run' };
  const saved = { schema_version: 'recommendation-evidence-v1', recommendation_id: current.id, run_id: 'run', facts_hash: card.facts_hash, evidence_hash: 'b'.repeat(64), status: 'PARTIAL', quant: null, limitations: [] } as const;
  const concise = { ...card, facts: current, explanation_requested: true, renderer_version: 'allocation-explanation-v2', explanation_evidence: {...saved, limitations: []}, selected_claim_ids:['profile'], explanation_claims:[{id:'profile',text:'Hệ số ngại rủi ro đã ghim: 6.',refs:['facts.constraints']}] };
  const html = renderToStaticMarkup(<ChatRecommendation card={concise} canonical={current} evidence={{...saved, limitations: []}} content="CTG · RSI14: 59,341 (đến 2026-11-16)."/>);
  expect(html.indexOf('RSI14: 59,341')).toBeGreaterThan(0);
  expect(html.indexOf('RSI14: 59,341')).toBeLessThan(html.indexOf('<details class="chat-explanation"'));
  expect(html).not.toMatch(/class="chat-explanation"[^>]*open=""/);
  expect(html).toContain('Căn cứ và số liệu chi tiết');
  expect(html).not.toContain(saved.evidence_hash);
  expect(html).toContain('Hệ số ngại rủi ro đã ghim: 6.');
  const invalid = renderToStaticMarkup(<ChatRecommendation card={concise} canonical={current} evidence={{...saved, evidence_hash:'c'.repeat(64),limitations:[]}} content="SECRET_CONCISE_CLAIM"/>);
  expect(invalid).not.toContain('SECRET_CONCISE_CLAIM');
  const missing = renderToStaticMarkup(<ChatRecommendation card={{...card, renderer_version:'allocation-explanation-v2'}} canonical={canonical} content="UNVERIFIED_V2_CLAIM"/>);
  expect(missing).not.toContain('UNVERIFIED_V2_CLAIM');
});


it('shows method prose only for an explicitly requested explanation', () => {
  const current = { ...canonical, strategy: 'BL_ML' };
  const saved = { ...card, facts: current };
  const content = 'Đề xuất dùng Black–Litterman kết hợp Machine Learning.';
  expect(renderToStaticMarkup(<ChatRecommendation card={saved} canonical={current} content={content}/>)).not.toMatch(/Black–Litterman|Machine Learning|BL \+ ML|BL_ML/);
  expect(renderToStaticMarkup(<ChatRecommendation card={{ ...saved, explanation_requested: true }} canonical={current} content={content}/>)).toContain(content);
});

it('links only a scoped quote with observations for that asset', () => {
  const quote = (scope: string, asset: string, observed: string[]) => renderToStaticMarkup(<QuoteHistoryLink
    card={{ type: 'market', facts_hash: '', facts: { scope, asset_id: asset, observations: observed.map(asset_id => ({ asset_id, price_vnd: '48500' })) } }}/>);
  expect(quote('equity_quote', 'FPT', ['FPT'])).toContain('#asset-prices?asset=FPT');
  expect(quote('gold_quote', '', ['GOLD'])).toContain('#asset-prices?asset=GOLD');
  expect(quote('equity_quote', 'FPT', ['VCB'])).toBe('');
  expect(quote('gold_quote', '', [])).toBe('');
  expect(quote('recent_observations', '', ['FPT'])).toBe('');
});


it('keeps the currency of a focused asset tied to its recommendation and identifies current capital separately', () => {
  const allocation = { ...canonical, weights: ['0.35', '0.65'] };
  const saved = { ...card, facts: allocation, explanation_requested: true, selected_claim_ids: ['focus_FPT'] };
  const dashboard = { portfolio: { id: canonical.portfolio_id, name: 'Kế hoạch', version: 4, capital_vnd: '120000000', universe_id: 'USER_SELECTED', constraints: { risk_aversion: 4, max_position_weight: .7 }, risk_profile: null, policy_version_id: 'policy' },
    accepted_target: { id: 'target', recommendation_id: canonical.id, allocation, accepted_at: '2026-11-18T08:00:00Z', portfolio_version: 3 }, target_matches_portfolio: false, proposal_count: 1 };
  const html = renderToStaticMarkup(<ChatRecommendation card={saved} canonical={allocation} content="FPT chiếm 35% trong đề xuất đã lưu." dashboard={dashboard} onOpen={() => {}}/>);
  expect(html).toMatch(/<strong>FPT chiếm 35% trong đề xuất đã lưu\.<\/strong>/);
  expect(html).toContain('35.000.000');
  expect(html).toContain('Vốn kế hoạch hiện tại là 120.000.000');
  expect(html).toContain('Mục tiêu đã lưu ngày 18/11/2026');
  expect(html).not.toContain('42.000.000');
  const different = renderToStaticMarkup(<ChatRecommendation card={saved} canonical={allocation} content="Kết quả." dashboard={{...dashboard, portfolio: {...dashboard.portfolio, id: 'other'}}} onOpen={() => {}}/>);
  expect(different).not.toContain('120.000.000');
});

it('links the saved target snapshot to its accepted proposal', () => {
  const target = { recommendation_id: 'accepted', accepted_at: '2026-11-24T05:09:35Z' };
  const source = (accepted_target: typeof target | null) => renderToStaticMarkup(<ReadFacts
    card={{ type: 'portfolio', facts_hash: '', facts: { scope: 'saved_target', id: 'portfolio', name: 'ssssss', accepted_target } }}/>);
  expect(source(target)).toContain('#proposal?portfolio=portfolio&amp;proposal=accepted');
  expect(source(null)).toContain('chưa có mục tiêu');
  expect(source(null)).not.toContain('#proposal');
});
