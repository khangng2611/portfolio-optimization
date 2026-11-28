'use client';

import { AnswerRows, RiskReason } from './risk-questions';
import { useCallback, useEffect, useEffectEvent, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode, type Ref } from 'react';
import { RecommendationEvidenceView } from './recommendation-evidence';
import type { RecommendationEvidence } from '../lib/chat-types';
import { IconButton } from './action-controls';
import { AllocationView, money, percentage, profileName } from './allocation-view';
import { OperationError } from './operation-ui';
import { Pagination } from './portfolio-lifecycle';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { transcriptScrollAction, type TranscriptPosition } from '../lib/chat-scroll';
import { LatestRequest } from '../lib/latest-request';
import type { AssetCatalogItem } from '../lib/selection-types';
import { allocationPriceKey, assetUniverseName, readinessReason, workspaceHash, type WorkspaceRoute } from '../lib/workspace-state';
import { chatError, chatStage, chatStatus, chatStopped, createSseParser, readPending, sameFacts, storageKey, type AllocationStatusCard, type ChatDashboard, type ChatJob, type ChatMessage, type ChatPortfolio, type ChatReceipt, type ConfirmationCard, type Conversation, type FactCard, type KnowledgeEvidence, type RecommendationCard, type SendMessage } from '../lib/chat-types';
import './chat-workspace.css';

export type ChatWorkspaceProps = { api: Api; apiPage: PageApi; route: WorkspaceRoute; navigate: (route: WorkspaceRoute) => void; ownerKey: string; onSessionExpired: () => void; assets?: AssetCatalogItem[]; systemPaused?: boolean };
type FirstMessage = { conversationId: string; body: SendMessage };
const emptyPage = <T,>(limit = 10): Page<T> => ({ items: [], total: 0, offset: 0, limit });
const percent = (value: number) => `${(value * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`;
const statusOf = (error: unknown) => error instanceof ApiError ? error.status : undefined;
const stored = (key: string) => { try { return sessionStorage.getItem(key); } catch { return null; } };
const save = (key: string, value: string | null) => { try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch { /* Explicit retry remains possible in this tab without storage. */ } };

export function KnowledgeSources({ evidence, initiallyOpen }: { evidence: KnowledgeEvidence; initiallyOpen?: boolean }) {
  if (!evidence.citations.length) return null;
  return <details className="chat-message-source chat-knowledge-sources" open={initiallyOpen}><summary>Nguồn tham khảo · {evidence.citations.length}</summary><ol>{evidence.citations.map(citation => {
    let safe = false;
    try { const url = new URL(citation.source_url); safe = url.protocol === 'https:' && !url.username && !url.password; } catch { /* Invalid references remain readable without a link. */ }
    return <li key={citation.chunk_id}>{safe ? <a href={citation.source_url} target="_blank" rel="noopener noreferrer">{citation.source_title}<span className="sr-only"> (mở tab mới)</span></a> : <strong>{citation.source_title}</strong>}<p className="muted small">{citation.locator}{citation.published_at ? ` · Xuất bản ${dateTime(citation.published_at)}` : ''}</p><blockquote>{citation.text}</blockquote></li>;
  })}</ol></details>;
}

export function ChatKnowledge({ evidence }: { evidence: KnowledgeEvidence }) {
  return <section className="chat-knowledge" data-testid="chat-knowledge" aria-label="Kiến thức tham khảo">{evidence.citations.length ? <KnowledgeSources evidence={evidence} initiallyOpen/> : <p>Chưa tìm thấy nguồn phù hợp cho câu hỏi này.</p>}</section>;
}

function PortfolioPicker({ api, apiPage, value, onChange, onError, disabled = false }: { api: Api; apiPage: PageApi; value: string; onChange: (id: string) => void; onError: (error: unknown) => void; disabled?: boolean }) {
  const [offset, setOffset] = useState(0), [page, setPage] = useState(emptyPage<Portfolio>()), [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Portfolio | null>(null);
  useEffect(() => {
    let active = true; setLoading(true);
    apiPage<Portfolio>(`/api/v1/portfolios?limit=10&offset=${offset}`).then(result => { if (active) setPage(result); }).catch(error => { if (active) onError(error); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apiPage, offset, onError]);
  useEffect(() => {
    let active = true; setSelected(null);
    if (value && !page.items.some(item => item.id === value)) api<Portfolio>(`/api/v1/portfolios/${value}`).then(result => { if (active) setSelected(result); }).catch(error => { if (active) onError(error); });
    return () => { active = false; };
  }, [api, value, page.items, onError]);
  return <div className="chat-portfolio-picker"><label>Danh mục trao đổi<select data-testid="chat-portfolio" value={value} onChange={event => onChange(event.target.value)} disabled={disabled || loading}>
    <option value="">Chưa chọn danh mục</option>{selected && !page.items.some(item => item.id === selected.id) && <option value={selected.id}>{selected.name}</option>}{page.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
  </select><small>Hồ sơ và ràng buộc lấy từ danh mục bạn chọn.</small></label>
    {page.total > page.limit && <Pagination total={page.total} offset={offset} limit={page.limit} onChange={setOffset} busy={loading || disabled}/>}
  </div>;
}

type ChatAllocation = Pick<Recommendation, 'id' | 'asset_ids' | 'as_of_date'>;
function savedAllocation(dashboard: ChatDashboard | null): ChatAllocation | null {
  const target = dashboard?.accepted_target;
  return target ? { id: target.recommendation_id, asset_ids: target.allocation.asset_ids, as_of_date: target.allocation.as_of_date } : null;
}

function ContextSummary({ dashboard, allocation, portfolioId, expanded }: { dashboard: ChatDashboard | null; allocation?: ChatAllocation | null; portfolioId: string; expanded: boolean }) {
  const saved = dashboard?.accepted_target;
  const preview = saved && saved.recommendation_id === allocation?.id ? `Mục tiêu đã lưu · ${historyDate.format(new Date(saved.accepted_at))}`
    : allocation ? `Đề xuất${allocation.as_of_date ? ' · ' + allocation.as_of_date : ''}`
    : dashboard ? `${money(dashboard.portfolio.capital_vnd)} · ${profileName(dashboard.portfolio.risk_profile?.profile)}` : '';
  return <><span className="chat-context-label"><span className="sr-only">Danh mục đang trao đổi: </span>{dashboard?.portfolio.name ?? (portfolioId ? 'Đang đọc danh mục…' : 'Chọn danh mục trao đổi')}</span>
    {preview && <span className="chat-context-preview">{preview}</span>}<span className="chat-context-affordance">{expanded ? 'Thu gọn' : 'Đổi'}</span></>;
}

function ChatWelcome({ ownerKey, portfolioId, allocation, saved, paused, disabled, onDraft }: {
  ownerKey: string; portfolioId: string; allocation?: ChatAllocation | null; saved: boolean; paused?: boolean; disabled: boolean;
  onDraft: (content: string, intent: SendMessage['intent'], recommendationId?: string) => void;
}) {
  const assets = allocation?.asset_ids ?? [];
  const lastPrice = allocation && stored(allocationPriceKey(ownerKey, portfolioId, allocation.id));
  const asset = lastPrice && assets.includes(lastPrice) ? lastPrice : assets[0];
  const questions: [SendMessage['intent'], string, string?][] = saved && asset
    ? [['explain', `Tỷ trọng ${asset}`, `Giải thích tỷ trọng ${asset}`], ['profile', 'Giải thích hồ sơ rủi ro']]
    : allocation ? [['explain', 'Rủi ro của phương án này là gì?']]
    : portfolioId ? [['portfolio', 'Tóm tắt kế hoạch'], ['profile', 'Giải thích hồ sơ rủi ro']]
    : [['knowledge', 'Phân bổ tài sản là gì?'], ['market', 'Giá vàng hôm nay là bao nhiêu?']];
  return <div className="chat-welcome"><h3>{saved ? 'Bạn muốn hiểu gì về phân bổ đã lưu?' : allocation ? 'Bạn muốn hiểu gì về đề xuất này?' : portfolioId ? 'Bạn muốn hiểu gì về kế hoạch này?' : 'Bạn muốn hỏi gì?'}</h3>
    <p className="muted">{paused && !allocation ? 'Tính đề xuất mới đang tạm dừng.' : 'Chọn câu hỏi để điền vào ô soạn.'}</p>
    <div className="chat-starters">{questions.map(([intent, label, draft]) => <button type="button" className="quiet" key={label} disabled={disabled}
      onClick={() => onDraft(draft ?? label, intent, intent === 'explain' ? allocation?.id : undefined)}>{label}</button>)}</div></div>;
}

function useChatKeyboard() {
  useEffect(() => {
    const viewport = window.visualViewport, workspace = document.querySelector<HTMLElement>('.workspace-chat');
    if (!viewport || !workspace) return;
    const update = () => {
      const keyboard = window.matchMedia('(max-width: 800px)').matches && viewport.scale === 1 && window.innerHeight - viewport.height > 120;
      workspace.toggleAttribute('data-chat-keyboard', keyboard);
      if (keyboard) workspace.style.setProperty('--chat-visible-height', `${Math.round(viewport.height)}px`);
    };
    viewport.addEventListener('resize', update); window.addEventListener('resize', update); update();
    return () => { viewport.removeEventListener('resize', update); window.removeEventListener('resize', update); workspace.removeAttribute('data-chat-keyboard'); workspace.style.removeProperty('--chat-visible-height'); };
  }, []);
}

function composerKey(event: KeyboardEvent<HTMLTextAreaElement>, edit: (value: string) => void) {
  if (event.key !== 'Enter' || event.nativeEvent.isComposing || event.keyCode === 229) return;
  if (event.metaKey) {
    event.preventDefault();
    const area = event.currentTarget;
    if (area.value.length - (area.selectionEnd - area.selectionStart) < area.maxLength) {
      area.setRangeText('\n', area.selectionStart, area.selectionEnd, 'end');
      edit(area.value);
    }
  } else if (!event.shiftKey && !event.ctrlKey && !event.altKey) {
    event.preventDefault();
    if (!event.repeat) event.currentTarget.form?.requestSubmit();
  }
}

function ComposerInput({ inputRef, id, label, value, edit, disabled, submitDisabled, sending, helpId }: {
  inputRef: Ref<HTMLTextAreaElement>; id: string; label: string; value: string; edit: (value: string) => void;
  disabled: boolean; submitDisabled?: boolean; sending: boolean; helpId?: string;
}) {
  return <div className="chat-input-row">
    <label className="sr-only" htmlFor={id}>{label}</label>
    <textarea id={id} ref={inputRef} data-testid="chat-input" rows={1} maxLength={4000} enterKeyHint="send"
      placeholder="Nhập câu hỏi của bạn…" value={value} disabled={disabled} aria-describedby={helpId}
      onChange={event => edit(event.target.value)} onKeyDown={event => composerKey(event, edit)}/>
    <button type="submit" className="send-button" data-testid="chat-send" aria-label={sending ? 'Đang gửi tin nhắn' : 'Gửi tin nhắn'}
      disabled={disabled || submitDisabled || !value.trim()}>Gửi</button>
  </div>;
}

function ConversationList({ api, apiPage, route, navigate, ownerKey, onSessionExpired, onFirstMessage, systemPaused }: ChatWorkspaceProps & { onFirstMessage: (message: FirstMessage) => void }) {
  const portfolioId = route.portfolioId ?? '';
  const [title, setTitle] = useState(''), [question, setQuestion] = useState(''), [suggestion, setSuggestion] = useState<SendMessage['intent']>();
  const [linked, setLinked] = useState<Recommendation | null>(null), [dashboard, setDashboard] = useState<ChatDashboard | null>(null);
  const [contextOpen, setContextOpen] = useState(false), [historyOpen, setHistoryOpen] = useState(false);
  const optionalTitle = useRef<HTMLDetailsElement>(null);
  const questionInput = useRef<HTMLTextAreaElement>(null), creatingNow = useRef(false);
  const [creating, setCreating] = useState(false), [error, setError] = useState('');
  const alive = useRef(true), currentRoute = useRef(workspaceHash(route)); currentRoute.current = workspaceHash(route);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const fail = useCallback((cause: unknown) => { setError(chatError(statusOf(cause))); if (statusOf(cause) === 401) onSessionExpired(); }, [onSessionExpired]);
  useEffect(() => {
    let active = true;
    if (portfolioId) api<ChatDashboard>(`/api/v1/portfolios/${portfolioId}/dashboard`).then(value => { if (active && value.portfolio.id === portfolioId) setDashboard(value); }).catch(cause => { if (active) fail(cause); });
    return () => { active = false; };
  }, [api, portfolioId, fail]);
  useEffect(() => {
    let active = true; setLinked(null);
    if (route.proposalId && portfolioId === route.portfolioId) api<Recommendation>(`/api/v1/recommendations/${route.proposalId}`).then(value => {
      if (!active) return;
      if (value.id !== route.proposalId || value.portfolio_id !== portfolioId) throw new ApiError(404, '');
      setLinked(value);
    }).catch(cause => { if (active) fail(cause); });
    return () => { active = false; };
  }, [api, fail, portfolioId, route.portfolioId, route.proposalId]);
  async function create(send: boolean) {
    if (creatingNow.current || unresolved || send && !question.trim()) return;
    const startedOn = currentRoute.current;
    creatingNow.current = true;
    setCreating(true); setError('');
    try {
      const result = await api<Conversation>('/api/v1/conversations', { method: 'POST', body: JSON.stringify({ title: title.trim() || question.trim().slice(0, 120) || 'Hội thoại mới', ...(portfolioId ? { portfolio_id: portfolioId } : {}) }) });
      if (!alive.current || startedOn !== currentRoute.current) return;
      if (send) {
        const body: SendMessage = { content: question.trim(), client_message_id: crypto.randomUUID(), ...(result.portfolio_id ? { portfolio_id: result.portfolio_id } : {}), ...(suggestion ? { intent: suggestion } : {}), ...(allocation ? { recommendation_id: allocation.id } : {}) };
        save(storageKey(ownerKey, result.id, 'pending'), JSON.stringify(body));
        onFirstMessage({ conversationId: result.id, body });
      }
      navigate({ view: 'chat', conversationId: result.id, ...(result.portfolio_id ? { portfolioId: result.portfolio_id } : {}), ...(allocation ? { proposalId: allocation.id } : {}) });
    } catch (cause) { if (alive.current) fail(cause); }
    finally { creatingNow.current = false; if (alive.current) setCreating(false); }
  }
  const allocation = route.proposalId ? linked : savedAllocation(dashboard);
  const saved = !!allocation && dashboard?.accepted_target?.recommendation_id === allocation.id;
  const unresolved = !!route.proposalId && !linked;
  function editQuestion(value: string) { setQuestion(value); setSuggestion(undefined); }
  return <div className="chat-workspace chat-conversation chat-focused chat-plan" data-testid="chat-workspace">
    <OperationError error={error}/>
    <div className="chat-layout">
      <ConversationNavigation apiPage={apiPage} route={route} onSessionExpired={onSessionExpired} mobileOpen={historyOpen} setMobileOpen={setHistoryOpen} onNew={() => { setQuestion(''); setTitle(''); setSuggestion(undefined); setContextOpen(false); if (optionalTitle.current) optionalTitle.current.open = false; questionInput.current?.focus(); }}/>
      <section className="chat-thread chat-start-thread" aria-label="Hội thoại mới">
        <header className="chat-topline"><h2>Trợ lý danh mục</h2><div className="chat-topline-actions"><button type="button" className="quiet chat-history-trigger" onClick={() => setHistoryOpen(true)}>Lịch sử</button></div></header>
        <aside className="chat-context" aria-label="Ngữ cảnh danh mục"><details open={contextOpen} onToggle={event => setContextOpen(event.currentTarget.open)}>
          <summary className="chat-context-summary"><ContextSummary dashboard={dashboard} portfolioId={portfolioId} allocation={allocation} expanded={contextOpen}/></summary>
          <div className="chat-context-body"><PortfolioPicker api={api} apiPage={apiPage} value={portfolioId} onChange={value => { navigate({ view: 'chat', portfolioId: value || undefined }); }} onError={fail} disabled={creating}/></div>
        </details></aside>
        <div className="chat-transcript chat-start-transcript">
          <ChatWelcome ownerKey={ownerKey} portfolioId={portfolioId} allocation={allocation} saved={saved} paused={systemPaused} disabled={creating || unresolved}
            onDraft={(draft, intent) => { setQuestion(draft); setSuggestion(intent); questionInput.current?.focus(); }}/>
        </div>
        <details ref={optionalTitle} className="chat-optional-title"><summary>Đặt tên hội thoại (tùy chọn)</summary><label>Tên hội thoại<input data-testid="chat-title" value={title} onChange={event => setTitle(event.target.value)} maxLength={120} disabled={creating}/></label>
          {!question.trim() && <button type="button" className="quiet" data-testid="chat-create" disabled={creating || unresolved} onClick={() => void create(false)}>Tạo hội thoại</button>}
        </details>
        <form onSubmit={event => { event.preventDefault(); void create(true); }} className="panel chat-composer" aria-label="Soạn tin nhắn">
          <ComposerInput inputRef={questionInput} id="chat-start-question" label="Câu hỏi của bạn" value={question} edit={editQuestion}
            disabled={creating} submitDisabled={unresolved} sending={creating}/>
          {suggestion && <p className="chat-draft-note muted small" role="status">Đã điền gợi ý vào bản nháp.</p>}
        </form>
      </section>
    </div>
  </div>;
}

function PortfolioFacts({ portfolio }: { portfolio: ChatPortfolio }) {
  return <dl className="chat-facts"><div><dt>Danh mục</dt><dd>{portfolio.name}</dd></div><div><dt>Vốn kế hoạch</dt><dd>{money(portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ rủi ro</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div><div><dt>Tỷ trọng tối đa / tài sản</dt><dd>{percent(portfolio.constraints.max_position_weight)}</dd></div></dl>;
}

export function ChatConfirmation({ card, disabled, onConfirm }: { card: ConfirmationCard; disabled: boolean; onConfirm: () => void }) {
  const portfolio = card.input.portfolio, constraints = portfolio.constraints, answers = portfolio.risk_profile?.answers;
  return <section className="chat-confirmation" aria-label="Xem lại đầu vào trước khi tạo đề xuất"><h3>Xem lại trước khi tạo đề xuất</h3>
    {card.reason === 'STALE_CONFIRMATION' && <p className="notice warning">Danh mục hoặc hồ sơ đã thay đổi. Vui lòng xem lại đầu vào mới bên dưới.</p>}
    <PortfolioFacts portfolio={portfolio}/><dl className="chat-facts"><div><dt>Bộ tài sản</dt><dd>{assetUniverseName(portfolio.universe_id)}</dd></div></dl>
    <details className="chat-risk-details"><summary>Câu trả lời và giới hạn phân bổ</summary><dl className="chat-facts">
      {constraints.min_defensive_weight !== undefined && <div><dt>Phòng thủ tối thiểu</dt><dd>{percent(constraints.min_defensive_weight)}</dd></div>}
      {constraints.max_non_defensive_weight !== undefined && <div><dt>Ngoài nhóm phòng thủ tối đa</dt><dd>{percent(constraints.max_non_defensive_weight)}</dd></div>}
      {!!constraints.defensive_asset_ids?.length && <div><dt>Tài sản phòng thủ</dt><dd>{constraints.defensive_asset_ids.join(', ')}</dd></div>}
      {answers && <AnswerRows answers={answers}/>}
    </dl></details><p className="chat-confirm-note">Xác nhận sẽ tạo một đề xuất với đầu vào này. Bạn sẽ xem và quyết định lưu tỷ trọng mục tiêu ở bước tiếp theo.</p>
    <button data-testid="chat-confirm" disabled={disabled} onClick={onConfirm}>Xác nhận tạo đề xuất</button>{disabled && <p className="muted small">Chỉ có thể xác nhận yêu cầu đang chờ.</p>}
  </section>;
}

type ResultPanel = 'allocation' | 'sources';
export function ChatRecommendation({ card, canonical, content, isCurrentTarget = false, onExplain, evidence, onOpen, panel, assets, dashboard }: { card: RecommendationCard; canonical: Recommendation | null | undefined; content: string; isCurrentTarget?: boolean; onExplain?: (question: string) => void; evidence?: RecommendationEvidence; onOpen?: (panel: ResultPanel) => void; panel?: ResultPanel; assets?: AssetCatalogItem[]; dashboard?: ChatDashboard | null }) {
  if (canonical === null) return <div className="notice warning" role="alert">Chưa mở được đề xuất đã lưu. Kiểm tra quyền truy cập hoặc tải lại trạng thái.</div>;
  if (!canonical) return <div role="status" className="muted">Đang đối chiếu đề xuất đã lưu…</div>;
  if (!sameFacts(card.facts, canonical)) return <div className="notice warning" role="alert">Nội dung đã lưu chưa khớp dữ liệu đề xuất hiện tại. Tải lại trạng thái để đối chiếu trước khi tiếp tục.</div>;
  const active = canonical.strategy === 'HYBRID' ? canonical.asset_ids : canonical.selection_proof?.active_asset_ids ?? canonical.inputs_provenance?.phase1_full?.active_asset_ids;
  const positive = canonical.weights.filter(weight => Number(weight) > 0).length;
  const concise = card.renderer_version === 'allocation-explanation-v2';
  const evidenceVerified = (!concise && !card.explanation_evidence) || !!(card.explanation_evidence && evidence && evidence.recommendation_id === canonical.id && evidence.run_id === canonical.run_id && evidence.facts_hash === card.facts_hash && sameFacts(card.explanation_evidence, evidence));
  const fullExplanation = card.explanation_requested && concise && evidenceVerified
    ? card.selected_claim_ids?.map(id => card.explanation_claims?.find(claim => claim.id === id)?.text).filter(text => text && !content.includes(text)).join('\n\n')
    : '';
  const assetIndex = canonical.asset_ids.findIndex(id => card.selected_claim_ids?.includes(`focus_${id}`));
  const focused = card.explanation_requested && assetIndex >= 0 && evidenceVerified;
  const weight = Number(canonical.weights[assetIndex]);
  const capital = Number(canonical.capital_vnd);
  const amount = focused && canonical.capital_vnd != null && Number.isFinite(capital) && Number.isFinite(weight) ? money(capital * weight) : null;
  const currentPlan = dashboard?.portfolio.id === canonical.portfolio_id ? dashboard : null;
  const savedAt = currentPlan?.accepted_target?.recommendation_id === canonical.id ? currentPlan.accepted_target.accepted_at : null;
  const answer = card.explanation_requested && (concise || onOpen) && (evidenceVerified ? <div className="chat-concise-answer"><AnswerText content={content}/></div> : <p role="alert" className="notice warning">Chưa đối chiếu được dữ liệu dùng để giải thích. Hãy thử tải lại hội thoại.</p>);
  const followup = onExplain && <button type="button" className="quiet" onClick={() => onExplain('Hệ thống tính đề xuất này như thế nào?')}>Hỏi cách tính đề xuất</button>;
  const review = <a data-testid="chat-open-recommendation" className="button" href={workspaceHash({ view: 'proposal', portfolioId: canonical.portfolio_id, proposalId: canonical.id })}>Xem đề xuất và quyết định</a>;
  if (onOpen) return <section data-testid="chat-result" className="chat-result-reference" aria-label="Đề xuất từ kết quả định lượng">
    {answer}
    {focused && <>
      {amount && <p>{percent(weight)} của vốn tại lần tính {money(capital)} tương ứng {amount}.</p>}
      {currentPlan && Number(currentPlan.portfolio.capital_vnd) !== capital && <p>Vốn kế hoạch hiện tại là {money(currentPlan.portfolio.capital_vnd)}.</p>}
      <details className="chat-turn-facts"><summary>Dữ kiện và nguồn</summary>
        <p>{savedAt ? `Mục tiêu đã lưu ngày ${historyDate.format(new Date(savedAt))}` : canonical.as_of_date ? `Đề xuất · Ngày dữ liệu ${canonical.as_of_date}` : 'Đề xuất đã lưu'}</p>
        <p>{canonical.asset_ids[assetIndex]} · {percent(weight)}{amount && ` · ${amount}`}</p>
        <div className="chat-fact-actions">
          <button type="button" className="quiet" onClick={() => onOpen('sources')}>Xem căn cứ của đề xuất</button>
          <button type="button" className="quiet" onClick={() => onOpen('allocation')}>Xem phân bổ</button>
        </div>
      </details>
    </>}
    {!card.explanation_requested && <p><strong>Đã tạo đề xuất</strong>{isCurrentTarget && ' · Đã chấp nhận làm mục tiêu hiện tại'}</p>}
    {!evidenceVerified && !concise && <p role="alert" className="notice warning">Chưa đối chiếu được dữ liệu dùng để giải thích. Hãy thử tải lại hội thoại.</p>}
    {evidenceVerified && evidence && evidence.status !== 'COMPLETE' && <p className="muted small">{evidence.status === 'PARTIAL' ? 'Lần tính chỉ có một phần dữ kiện để giải thích.' : 'Lần tính này chưa có dữ kiện để giải thích.'}</p>}
    {!focused && canonical.as_of_date && <p className="muted small">Ngày dữ liệu của đề xuất {canonical.as_of_date}</p>}
    {!focused && <div className="actions"><button type="button" className="quiet" onClick={() => onOpen('sources')}>Xem dữ kiện và nguồn</button>{followup}</div>}
  </section>;
  const allocation = <section className="chat-main-allocation" aria-label="Phân bổ chính"><h3>Phân bổ chính</h3><AllocationView allocation={canonical} assets={assets} presentation="chart" metadata={false} summaryFirst capitalLabel="Vốn tại thời điểm tính"/></section>;
  return <section {...(!panel && { 'data-testid': 'chat-result' })} className="chat-recommendation" aria-label="Đề xuất từ kết quả định lượng">{isCurrentTarget && <span className="badge success">Đã chấp nhận làm mục tiêu hiện tại</span>}
    <header className="chat-result-summary"><h3>{card.explanation_requested ? 'Kết quả đang được giải thích' : 'Đề xuất đã lưu'}</h3>{canonical.as_of_date && <p className="muted">Ngày dữ liệu {canonical.as_of_date}</p>}</header>
    {panel !== 'allocation' && answer}
    {panel !== 'sources' && (panel || !concise || !card.explanation_requested ? allocation : <details className="chat-linked-allocation"><summary>Xem phân bổ</summary>{allocation}</details>)}
    <details className="chat-explanation" open={panel === 'sources' || (!concise && card.explanation_requested === true)}><summary>{concise ? 'Căn cứ và số liệu chi tiết' : 'Đọc giải thích phân bổ'}</summary>
      <section className="chat-verified-basis"><h3>Căn cứ của đề xuất</h3>{active && <p>{active.length} tài sản dùng khi tính, {positive} tài sản có tỷ trọng trên 0%.</p>}
        {fullExplanation && <p className="chat-message-text">{fullExplanation}</p>}
        {!evidenceVerified && <p role="alert" className="notice warning">Dữ liệu giải thích chưa khớp với đề xuất. Hãy thử tải lại hội thoại.</p>}
        {card.explanation_requested && evidence && evidenceVerified && <RecommendationEvidenceView evidence={evidence} facts={canonical} factsHash={card.facts_hash}/>}
        {card.explanation_requested && !concise && evidenceVerified && content.trim() && <details className="chat-original-explanation"><summary>Nội dung giải thích đã lưu</summary><p className="chat-message-text">{content}</p></details>}
      </section>
      {canonical.constraints && <section className="chat-result-limits"><h3>Giới hạn và điều cần lưu ý</h3><p>Tối đa {percentage(canonical.constraints.max_position_weight)} mỗi tài sản.{canonical.constraints.min_defensive_weight != null && <> Phòng thủ tối thiểu {percentage(canonical.constraints.min_defensive_weight)}.</>}{canonical.constraints.max_non_defensive_weight != null && <> Ngoài nhóm phòng thủ tối đa {percentage(canonical.constraints.max_non_defensive_weight)}.</>}</p><p className="muted">Đây là tỷ trọng mục tiêu, không phải tài sản đang nắm giữ hoặc bảo đảm lợi nhuận. Nội dung giải thích không thay đổi kết quả đã tính.</p></section>}
    </details>
    {card.explanation_requested && !!card.knowledge?.citations.length && <KnowledgeSources evidence={card.knowledge}/>}
    {review}
    {followup && <div className="chat-followups">{followup}</div>}
  </section>;
}

type MarketObservation = { revision_id: string; asset_id: string; price_vnd: string; observation_date: string; provider: string; data_origin: string };
function marketObservations(card: FactCard) {
  return Array.isArray(card.facts.observations) ? card.facts.observations as MarketObservation[] : [];
}
export function QuoteHistoryLink({ card, portfolioId }: { card: FactCard; portfolioId?: string }) {
  const scope = card.facts.scope;
  const asset = scope === 'gold_quote' ? 'GOLD' : scope === 'equity_quote' ? card.facts.asset_id : null;
  if (typeof asset !== 'string' || !/^[A-Z0-9_-]{1,64}$/.test(asset)) return null;
  const rows = marketObservations(card);
  if (!rows.length || !rows.every(row => row.asset_id === asset && Number(row.price_vnd) > 0 && Number.isFinite(Number(row.price_vnd)))) return null;
  return <a className="button quiet" href={workspaceHash({ view: 'asset-prices', assetId: asset, portfolioId })}>Xem lịch sử giá {asset === 'GOLD' ? 'vàng' : asset}</a>;
}

function AnswerText({ content }: { content: string }) {
  const first = content.trim().match(/^(.+?[.!?])(?:\s+|$)|^([^\n]+)(?:\n|$)/);
  const conclusion = first?.[1] ?? first?.[2] ?? content;
  const detail = content.trim().slice(conclusion.length).trim();
  return <div className="chat-answer-text"><strong>{conclusion}</strong>{detail && ' '}{detail && <p className="chat-message-text">{detail}</p>}</div>;
}

function factAnswer(card: FactCard) {
  if (card.type === 'market') {
    const latest = marketObservations(card).map(item => item.observation_date).sort().at(-1);
    return latest ? `Ngày có giá gần nhất trong dữ liệu là ${latest}. Bạn có thể xem từng mức giá và nguồn bên dưới.` : 'Chưa có quan sát giá để hiển thị.';
  }
  const portfolio = (card.type === 'profile' ? card.facts.portfolio : card.facts) as ChatPortfolio | null;
  if (!portfolio?.constraints) return 'Chưa đọc được thông tin danh mục.';
  const profile = profileName(portfolio.risk_profile?.profile);
  const months = portfolio.risk_profile?.answers?.horizon_months;
  if (card.type === 'portfolio' && months) return `Kế hoạch của bạn có thời hạn ${months} tháng. Vốn kế hoạch ${money(portfolio.capital_vnd)}, hồ sơ ${profile.toLowerCase()}.`;
  return card.type === 'profile' ? `Hồ sơ rủi ro của ${portfolio.name} là ${profile.toLowerCase()}.` : `${portfolio.name} có vốn kế hoạch ${money(portfolio.capital_vnd)}. Hồ sơ rủi ro ${profile.toLowerCase()}.`;
}

export function ReadFacts({ card }: { card: FactCard }) {
  const facts = card.facts;
  if (card.type === 'portfolio' && facts.scope === 'saved_target') {
    const target = facts.accepted_target as { accepted_at: string; recommendation_id: string } | null;
    return <section><h3>Mục tiêu phân bổ của {String(facts.name)}</h3>{target
      ? <><p>Portfolio ghi nhận mục tiêu lúc {dateTime(target.accepted_at)}.</p><a href={workspaceHash({ view: 'proposal', portfolioId: String(facts.id), proposalId: target.recommendation_id })}>Xem đề xuất đã chấp nhận</a></>
      : <p>Danh mục chưa có mục tiêu đã chấp nhận tại thời điểm hỏi.</p>}</section>;
  }
  if (card.type === 'market' && facts.scope === 'asset_description') {
    return <section><h3>Thông tin mã {String(facts.asset_id)}</h3><p>{String(facts.display_name || facts.asset_id)}</p><p>Nguồn: danh mục tài sản{facts.metadata_source ? ` (${String(facts.metadata_source)})` : ''}.</p></section>;
  }
  if (card.type === 'market') {
    const observations = marketObservations(card);
    return <section><h3>{facts.requested_date ? 'Dữ liệu giá của lượt hỏi' : 'Dữ liệu thị trường gần nhất'}</h3>{typeof facts.requested_date === 'string' && <p>Ngày được hỏi: {facts.requested_date}.</p>}<p className="muted small">Các ngày bên dưới là ngày ghi nhận giá.</p>{facts.status === 'STALE' && <p className="notice warning">Dữ liệu đang cũ. Cần cập nhật trước khi dùng cho quyết định mới.</p>}{observations.length ? <div className="table-wrap mobile-cards"><table><caption>Giá theo ngày và nguồn dữ liệu</caption><thead><tr><th>Tài sản</th><th>Ngày</th><th>Giá</th><th>Nguồn</th></tr></thead><tbody>{observations.map(row => <tr key={row.revision_id}><th scope="row">{row.asset_id}</th><td data-label="Ngày">{row.observation_date}</td><td data-label="Giá">{money(row.price_vnd)}</td><td data-label="Nguồn">{row.provider} · {row.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}</td></tr>)}</tbody></table></div> : <p>Chưa có quan sát thị trường.</p>}</section>;
  }
  const portfolio = (card.type === 'profile' ? facts.portfolio : facts) as ChatPortfolio | null;
  return portfolio?.constraints ? <section><h3>{card.type === 'profile' ? 'Hồ sơ rủi ro' : 'Tóm tắt danh mục'}</h3><PortfolioFacts portfolio={portfolio}/>{portfolio.risk_profile?.answers && <dl className="chat-facts">{card.type === 'profile' ? <AnswerRows answers={portfolio.risk_profile.answers}/> : <div><dt>Thời hạn kế hoạch</dt><dd>{portfolio.risk_profile.answers.horizon_months} tháng</dd></div>}</dl>}<p className="muted small">Nguồn: Hồ sơ và kế hoạch đã lưu tại thời điểm trả lời.</p></section> : <p>Chưa tải được thông tin danh mục cho câu trả lời này.</p>;
}

function ChatPanel({ id, title, inline, onClose, children }: { id: string; title: string; inline?: boolean; onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null), close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const node = dialog.current;
    node?.showModal();
    close.current?.focus({ preventScroll: true });
    return () => { if (node?.open) node.close(); if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, [inline]);
  const body = <><header className="chat-detail-header"><h2 id={id}>{title}</h2><button ref={close} type="button" className="quiet" onClick={onClose}>{inline ? 'Thu gọn' : 'Trở lại hội thoại'}</button></header>{children}</>;
  return inline ? <aside className="chat-detail-panel" aria-labelledby={id} onKeyDown={event => { if (event.key === 'Escape') onClose(); }}>{body}</aside>
    : <dialog ref={dialog} className="chat-detail-panel" aria-labelledby={id} onCancel={event => { event.preventDefault(); onClose(); }}>{body}</dialog>;
}

const historyDate = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh' });

const historyTime = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' });

function ConversationNavigation({ apiPage, route, onSessionExpired, mobileOpen, setMobileOpen, onNew }: Pick<ChatWorkspaceProps, 'apiPage' | 'route' | 'onSessionExpired'> & { mobileOpen: boolean; setMobileOpen: (open: boolean) => void; onNew?: () => void }) {
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [page, setPage] = useState(emptyPage<Conversation>()), [offset, setOffset] = useState(0), [error, setError] = useState(false), [loading, setLoading] = useState(true), [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true; setError(false); setLoading(true);
    apiPage<Conversation>(`/api/v1/conversations?limit=10&offset=${offset}`).then(result => { if (active) setPage(result); }).catch(cause => { if (!active) return; setError(true); if (statusOf(cause) === 401) onSessionExpired(); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apiPage, offset, revision, onSessionExpired]);
  const today = historyDate.format(new Date());
  const body = <><a className="button quiet" href={workspaceHash({ view: 'chat', portfolioId: route.portfolioId, proposalId: route.proposalId })} onClick={() => { setMobileOpen(false); onNew?.(); }}>Hội thoại mới</a>{error ? <div role="status"><p>Chưa tải được danh sách.</p><button className="quiet" onClick={() => setRevision(value => value + 1)}>Thử lại</button></div> : loading && !page.items.length ? <p role="status">Đang tải hội thoại…</p> : page.items.length ? <nav aria-label="Hội thoại đã lưu">{page.items.map(item => {
    const created = new Date(item.created_at);
    const day = historyDate.format(created);
    const timestamp = dateTime(item.created_at);
    return <a key={item.id} title={timestamp} aria-current={item.id === route.conversationId ? 'page' : undefined} href={workspaceHash({ view: 'chat', conversationId: item.id, ...(item.portfolio_id ? { portfolioId: item.portfolio_id } : {}) })} onClick={() => setMobileOpen(false)}>{item.title}<small><time dateTime={item.created_at} aria-label={timestamp}>{day === today ? historyTime.format(created) : day}</time></small></a>;
  })}</nav> : <p>Chưa có hội thoại.</p>}{page.total > page.limit && <Pagination total={page.total} offset={offset} limit={page.limit} onChange={setOffset} busy={loading}/>}</>;
  return <><aside className="chat-navigation" aria-label="Danh sách hội thoại"><details open={navigationOpen} onToggle={event => setNavigationOpen(event.currentTarget.open)}><summary>Lịch sử</summary>{body}</details></aside>
    {mobileOpen && <ChatPanel id="chat-history-panel" title="Lịch sử hội thoại" onClose={() => setMobileOpen(false)}>{body}</ChatPanel>}</>;
}

export function AllocationStatusAnswer({ card, content, dashboard, portfolioId, onRecheck }: {
  card: AllocationStatusCard; content: string; dashboard: ChatDashboard | null; portfolioId: string; onRecheck?: () => void;
}) {
  const hasHistory = card.portfolio_id === portfolioId && dashboard?.portfolio.id === portfolioId && dashboard.proposal_count > 0;
  return <div data-testid="allocation-status">
    <AnswerText content={content}/>
    {card.checked_at && <p className="muted small">Kiểm tra lúc <time dateTime={card.checked_at}>{dateTime(card.checked_at)} (GMT+7)</time></p>}
    {card.status === 'UNKNOWN' && card.portfolio_id === portfolioId && onRecheck && <button type="button" className="quiet" onClick={onRecheck}>Kiểm tra lại trạng thái</button>}
    {hasHistory && <a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId, focus: 'history' })}>Xem đề xuất đã lưu</a>}
  </div>;
}

export function ChatTurnStatus({ job, resultVisible, connection, disabled, onResume, onCancel }: {
  job: ChatJob; resultVisible: boolean; connection: string; disabled: boolean; onResume: () => void; onCancel?: () => void;
}) {
  // The answer or confirmation already carries its own meaning. A completed chat
  // turn is not a receipt for saving a proposal or accepting a portfolio target.
  if (resultVisible && ['SUCCEEDED', 'WAITING_INPUT'].includes(job.status)) return null;
  if (job.status === 'FAILED' && job.error === 'SYSTEM_PAUSED') return <p className="chat-job" data-testid="chat-job" role="status">{chatStatus(job.status, job.error)}</p>;
  if (job.status === 'SUCCEEDED') return <p className="chat-turn-complete muted small" data-testid="chat-job" role="status">Đã xử lý lượt trao đổi.</p>;
  const inputFailures: Record<string, string> = {
    INPUT_EXPIRED: 'Dữ liệu đầu vào đã hết hạn nên chưa thể tạo đề xuất. Nhờ người vận hành làm mới và phát hành dữ liệu, sau đó tạo yêu cầu mới, xem lại đầu vào và xác nhận lại.',
    VFF_STALE: 'NAV của quỹ VFF đủ điều kiện sử dụng đã quá cũ so với giới hạn 7 ngày. Nhờ người vận hành kiểm tra và cập nhật nguồn; khi có dữ liệu đủ mới, hãy tạo yêu cầu mới và xác nhận lại.',
    GOLD_STALE: 'Dữ liệu giá vàng đủ điều kiện sử dụng đã quá cũ so với giới hạn 7 ngày. Nhờ người vận hành cập nhật nguồn, sau đó tạo yêu cầu mới và xác nhận lại.',
    ASSET_DATA_STALE: 'Dữ liệu của một hoặc nhiều tài sản đã quá cũ để tính toán. Nhờ người vận hành cập nhật dữ liệu, sau đó tạo yêu cầu mới và xác nhận lại.',
  };
  const running = !chatStopped(job.status);
  return <section className="chat-job" data-testid="chat-job" aria-label="Trạng thái lượt trao đổi" role="status">
    <strong>{chatStatus(job.status)}</strong>{(running || job.status === 'WAITING_INPUT') && <p>{chatStage(job.stage)}</p>}
    {running && <p className="muted small">{connection === 'connected' ? 'Đang cập nhật tiến trình.' : connection === 'retrying' ? 'Đang kết nối lại. Trạng thái vẫn được kiểm tra.' : 'Đang kết nối tiến trình…'}</p>}
    {running && onCancel && <button type="button" className="quiet" disabled={disabled} onClick={onCancel}>Hủy lượt trao đổi</button>}
    {job.status === 'FAILED' && <p>{inputFailures[job.error ?? ''] ?? readinessReason[job.error ?? ''] ?? 'Yêu cầu chưa hoàn tất. Bạn có thể gửi lại yêu cầu để thử lại.'}</p>}
    {job.status === 'AUTHORIZATION_REQUIRED' && <><p>Quyền của lượt này đã hết hạn. Cấp lại quyền để tiếp tục cùng yêu cầu.</p><button className="quiet" onClick={onResume} disabled={disabled}>Cấp lại quyền và tiếp tục</button></>}
  </section>;
}

function ConversationWorkspace({ api, apiPage, route, navigate, ownerKey, onSessionExpired, assets, systemPaused, firstMessage, onFirstMessageConsumed }: ChatWorkspaceProps & { firstMessage?: SendMessage; onFirstMessageConsumed: () => void }) {
  const cid = route.conversationId!;
  const [conversation, setConversation] = useState<Conversation | null>(null), [history, setHistory] = useState(emptyPage<ChatMessage>(50)), [offset, setOffset] = useState(0);
  const [job, setJob] = useState<ChatJob | null>(null), [recommendations, setRecommendations] = useState<Record<string, Recommendation | null>>({});
  const [evidenceById, setEvidenceById] = useState<Record<string, RecommendationEvidence>>({});
  const [portfolioId, setPortfolioId] = useState(route.portfolioId ?? ''), [dashboard, setDashboard] = useState<ChatDashboard | null>(null), [contextRevision, setContextRevision] = useState(0);
  const [pinned, setPinned] = useState<Recommendation | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const layoutRef = useRef<HTMLDivElement>(null);
  const [historyOpen, setHistoryOpen] = useState(false), [sideBySide, setSideBySide] = useState(false);
  const [opened, setOpened] = useState<{ message: ChatMessage; panel: ResultPanel } | null>(null);
  useEffect(() => {
    const layout = layoutRef.current;
    const history = layout?.querySelector<HTMLElement>('.chat-navigation');
    if (!layout || !history) return;
    const measure = () => {
      const style = getComputedStyle(layout);
      const historyWidth = history.getBoundingClientRect().width;
      const remaining = layout.clientWidth - historyWidth - parseFloat(style.paddingRight)
        - 2 * parseFloat(style.columnGap) - parseFloat(style.getPropertyValue('--chat-detail-min'));
      setSideBySide(historyWidth > 0 && remaining >= parseFloat(style.getPropertyValue('--chat-thread-min')));
      if (historyWidth > 0) setHistoryOpen(false);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(layout);
    observer.observe(history);
    measure();
    return () => observer.disconnect();
  }, []);
  const [content, setContent] = useState('');
  const [draftAction, setDraftAction] = useState<Pick<SendMessage, 'intent' | 'recommendation_id'>>({});
  const [suggested, setSuggested] = useState(false);
  const [pending, setPending] = useState<SendMessage | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'retrying' | 'saved'>('connecting'), [announcement, setAnnouncement] = useState('');
  const transientError = useRef(false);
  const mounted = useRef(true), snapshots = useRef(new LatestRequest()), sending = useRef(false), followLatest = useRef(true), jobRef = useRef<ChatJob | null>(null), portfolioRef = useRef(portfolioId), pendingRef = useRef<SendMessage | null>(null);
  const desiredJob = useRef(route.jobId);
  useEffect(() => { desiredJob.current = route.jobId; }, [route.jobId]);
  const input = useRef<HTMLTextAreaElement>(null), resumeId = useRef<string | null>(null);
  const transcript = useRef<HTMLDivElement>(null), previousTranscript = useRef<TranscriptPosition | null>(null), nearTranscriptEnd = useRef(true);
  const panelScroll = useRef<number | null>(null);
  const panelTrigger = useRef<HTMLElement | null>(null);
  const [showScrollEnd, setShowScrollEnd] = useState(false);
  const lastVisibleId = history.items.at(-1)?.id;
  useEffect(() => {
    if (loading || !transcript.current) return;
    const next = { offset: history.offset, lastId: lastVisibleId };
    const action = transcriptScrollAction(previousTranscript.current, next, followLatest.current, nearTranscriptEnd.current);
    previousTranscript.current = next;
    if (action === 'preserve') return;
    const frame = requestAnimationFrame(() => {
      if (!transcript.current) return;
      transcript.current.scrollTop = action === 'end' ? transcript.current.scrollHeight : 0;
      nearTranscriptEnd.current = action === 'end'; setShowScrollEnd(action !== 'end');
    });
    return () => cancelAnimationFrame(frame);
  }, [history.offset, lastVisibleId, loading]);
  const pendingKey = storageKey(ownerKey, cid, 'pending');
  const rememberPending = useCallback((value: SendMessage | null) => { pendingRef.current = value; setPending(value); save(pendingKey, value ? JSON.stringify(value) : null); }, [pendingKey]);
  const fail = useCallback((cause: unknown) => {
    if (!mounted.current) return;
    const status = statusOf(cause); transientError.current = status === undefined || status >= 500;
    setError(chatError(status));
    if (status === 401) onSessionExpired();
  }, [onSessionExpired, pendingKey]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { const saved = readPending(stored(pendingKey)); pendingRef.current = saved; setPending(saved); if (saved && !saved.confirmation) setContent(saved.content); }, [pendingKey]);
  useEffect(() => { if (route.portfolioId) { portfolioRef.current = route.portfolioId; setPortfolioId(route.portfolioId); } }, [route.portfolioId]);

  const refreshSnapshot = useCallback(async () => {
    if (!mounted.current) return null;
    try {
      // Each requested job/page supersedes earlier reads. Do not drop a newer
      // refresh while a canonical request from an older turn is still pending.
      const snapshot = await snapshots.current.runFor(`${cid}:${offset}:${desiredJob.current ?? ''}:${followLatest.current}`, async () => {
        const current = await api<Conversation>(`/api/v1/conversations/${cid}`);
        const jid = desiredJob.current ?? current.active_job_id;
        const state = jid ? await api<ChatJob>(`/api/v1/jobs/chat/${jid}`) : null;
        if (state && state.conversation_id !== cid) throw new ApiError(404, '');
        // A terminal job stops polling. Read messages after its state so the committed reply is visible.
        const initialPage = await apiPage<ChatMessage>(`/api/v1/conversations/${cid}/messages?limit=50&offset=${offset}`);
        const latestOffset = Math.floor(Math.max(0, initialPage.total - 1) / initialPage.limit) * initialPage.limit;
        const page = followLatest.current && nearTranscriptEnd.current && initialPage.offset !== latestOffset
          ? await apiPage<ChatMessage>(`/api/v1/conversations/${cid}/messages?limit=50&offset=${latestOffset}`) : initialPage;
        const ids = [...new Set(page.items.flatMap(message => message.structured?.type === 'recommendation' ? [message.structured.recommendation_id] : []))];
        const canonical = await Promise.all(ids.map(id => api<Recommendation>(`/api/v1/recommendations/${id}`).catch(cause => {
          if (statusOf(cause) === 401) throw cause;
          return null;
        })));
        const evidence = await Promise.all(ids.map(id => api<RecommendationEvidence>(`/api/v1/recommendations/${id}/evidence`).catch(() => null)));
        return { current, page, state, canonical: Object.fromEntries(ids.map((id, index) => [id, canonical[index]])), evidence };
      });
      if (!snapshot || !mounted.current) return null;
      const { current, page, state, canonical, evidence } = snapshot;
      // A reader may scroll up while the latest-page request is in flight.
      if (page.offset !== offset && !nearTranscriptEnd.current) return null;
      if (transientError.current) { transientError.current = false; setError(''); }
      if (page.offset !== offset) setOffset(page.offset);
      setConversation(current); setHistory(page);
      if (!portfolioRef.current && current.portfolio_id) { portfolioRef.current = current.portfolio_id; setPortfolioId(current.portfolio_id); }
      setRecommendations(canonical); jobRef.current = state; setJob(state);
      setEvidenceById(Object.fromEntries(evidence.filter((item): item is RecommendationEvidence => item !== null).map(item => [item.recommendation_id, item])));
      const draft = pendingRef.current;
      if (draft && page.items.some(message => message.client_message_id === draft.client_message_id)) {
        rememberPending(null); setContent(value => value === draft.content ? '' : value); setDraftAction({}); setSuggested(false);
      }
      if (state && chatStopped(state.status)) { setConnection('saved'); setAnnouncement(chatStatus(state.status, state.error)); }
      return state;
    } catch (cause) { fail(cause); return null; }
    finally { if (mounted.current) setLoading(false); }
  }, [api, apiPage, cid, offset, route.jobId, rememberPending, fail]);
  useEffect(() => { void refreshSnapshot(); }, [refreshSnapshot]);

  useEffect(() => {
    let active = true; setDashboard(null);
    if (portfolioId) api<ChatDashboard>(`/api/v1/portfolios/${portfolioId}/dashboard`).then(value => { if (active && value.portfolio.id === portfolioId) setDashboard(value); }).catch(cause => { if (active) fail(cause); });
    return () => { active = false; };
  }, [api, portfolioId, contextRevision, fail]);
  useEffect(() => {
    let active = true; setPinned(null);
    if (route.proposalId) api<Recommendation>(`/api/v1/recommendations/${route.proposalId}`).then(value => {
      if (!active || !portfolioId) return;
      if (value.id !== route.proposalId || value.portfolio_id !== portfolioId) throw new ApiError(404, '');
      setPinned(value);
    }).catch(cause => { if (active) fail(cause); });
    return () => { active = false; };
  }, [api, fail, portfolioId, route.proposalId]);

  const jobId = job?.job_id ?? route.jobId;
  const stopped = chatStopped(job?.status);
  useEffect(() => {
    if (!jobId || stopped) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refreshSnapshot(); if (active) timer = setTimeout(poll, 1000); };
    timer = setTimeout(poll, 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [jobId, stopped, refreshSnapshot]);

  useEffect(() => {
    if (!jobId || stopped) return;
    const abort = new AbortController(), key = storageKey(ownerKey, jobId, 'sequence');
    const saved = Number(stored(key) ?? 0); let cursor = Number.isSafeInteger(saved) && saved >= 0 && saved <= 999999999999 ? saved : 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const wait = () => new Promise<void>(resolve => { const done = () => { clearTimeout(retryTimer); abort.signal.removeEventListener('abort', done); resolve(); }; retryTimer = setTimeout(done, 1500); abort.signal.addEventListener('abort', done, { once: true }); });
    const connect = async () => {
      while (!abort.signal.aborted) {
        let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
        try {
          setConnection('connecting');
          const response = await fetch(`/api/v1/jobs/chat/${jobId}/events`, { headers: { Accept: 'text/event-stream', 'Last-Event-ID': String(cursor) }, credentials: 'same-origin', cache: 'no-store', signal: abort.signal });
          if (response.status === 401) { fail(new ApiError(401, '')); return; }
          if (!response.ok || !response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('Stream unavailable');
          setConnection('connected'); const parser = createSseParser(), decoder = new TextDecoder(); reader = response.body.getReader();
          while (!abort.signal.aborted) {
            const part = await reader.read(); if (part.done) break;
            for (const event of parser.push(decoder.decode(part.value, { stream: true }))) {
              if (event.event === 'session_expired') { fail(new ApiError(401, '')); return; }
              if (event.event === 'reset_required' || event.id !== null && event.id > cursor + 1) {
                const state = await refreshSnapshot(); cursor = state?.last_event_id ?? 0; save(key, String(cursor)); setAnnouncement('Đã tải lại lịch sử và kết quả từ dữ liệu đã lưu.');
                await reader.cancel(); break;
              }
              if (event.id !== null && event.id <= cursor) continue;
              if (event.id !== null) { cursor = event.id; save(key, String(cursor)); }
              if (event.event === 'stage_changed') setAnnouncement(chatStage(typeof event.data.stage === 'string' ? event.data.stage : undefined));
              if (['accepted', 'input_required', 'artifact_ready', 'completed', 'failed', 'cancelled'].includes(event.event)) {
                const state = await refreshSnapshot();
                if (state && chatStopped(state.status)) { setConnection('saved'); setContextRevision(value => value + 1); return; }
              }
            }
          }
          const state = await refreshSnapshot(); if (state && chatStopped(state.status)) { setConnection('saved'); return; }
        } catch { if (abort.signal.aborted) return; setConnection('retrying'); }
        finally { try { await reader?.cancel(); } catch { /* Aborted streams are already closed. */ } }
        if (abort.signal.aborted || jobRef.current && chatStopped(jobRef.current.status)) return;
        setConnection('retrying'); await wait();
      }
    };
    void connect();
    return () => { abort.abort(); clearTimeout(retryTimer); };
  }, [jobId, stopped, ownerKey, refreshSnapshot, fail]);

  async function submitBody(body: SendMessage) {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(''); rememberPending(body);
    try {
      const receipt = await api<ChatReceipt>(`/api/v1/conversations/${cid}/messages`, { method: 'POST', headers: { 'Idempotency-Key': body.client_message_id }, body: JSON.stringify(body) });
      if (!mounted.current) return;
      snapshots.current.invalidate(); desiredJob.current = receipt.job_id;
      // The accepted receipt itself is durable. Start reconnect/poll recovery
      // even if the very next read fails while the browser goes offline.
      const acceptedJob: ChatJob = { ...receipt, status: 'QUEUED', stage: 'INTENT', error: null, recommendation_id: null, result_message_id: null, last_event_id: 0, attempts: 0 };
      jobRef.current = acceptedJob; setJob(acceptedJob);
      rememberPending(null); setContent(''); setDraftAction({}); setSuggested(false); setAnnouncement('Yêu cầu đã được tiếp nhận.'); followLatest.current = true;
      // Keep the known receipt in the URL before any further network call. A
      // failed status read must never lose a successfully accepted job identity.
      navigate({ view: 'chat', conversationId: cid, ...(body.portfolio_id ? { portfolioId: body.portfolio_id } : {}), proposalId: pinned?.id ?? route.proposalId, jobId: receipt.job_id });
      await refreshSnapshot();
    } catch (cause) {
      if (!mounted.current) return;
      const status = statusOf(cause);
      if (status && [400, 403, 404, 409, 412, 422].includes(status)) rememberPending(null);
      fail(cause); void refreshSnapshot();
    } finally { sending.current = false; if (mounted.current) setBusy(false); }
  }
  const sendFirstMessage = useEffectEvent((body: SendMessage) => {
    onFirstMessageConsumed();
    if (!history.items.some(message => message.client_message_id === body.client_message_id)) void submitBody(body);
  });
  useEffect(() => {
    if (firstMessage && !loading && conversation && !job) sendFirstMessage(firstMessage);
  }, [conversation, firstMessage, job, loading]);
  function send(event?: FormEvent) {
    event?.preventDefault(); if (!content.trim() || blocked) return;
    const action = !draftAction.recommendation_id || draftAction.recommendation_id === dashboard?.accepted_target?.recommendation_id || draftAction.recommendation_id === pinned?.id || recommendations[draftAction.recommendation_id]?.portfolio_id === portfolioId ? draftAction : {};
    const body: SendMessage = { content: content.trim(), client_message_id: crypto.randomUUID(), ...(portfolioId ? { portfolio_id: portfolioId } : {}), ...(allocation ? { recommendation_id: allocation.id } : {}), ...action };
    void submitBody(body);
  }
  function editDraft(value: string) {
    setContent(value);
    setSuggested(false);
    if (draftAction.intent && (!value.trim() || !draftAction.recommendation_id)) setDraftAction({});
  }
  function confirm(card: ConfirmationCard) {
    if (busy || pending || !job || job.status !== 'WAITING_INPUT' || job.result_message_id !== card.confirmation_message_id) return;
    void submitBody({ content: 'Xác nhận tạo đề xuất với đầu vào đã xem.', client_message_id: crypto.randomUUID(), portfolio_id: card.input.portfolio.id, confirmation: { message_id: card.confirmation_message_id, facts_hash: card.facts_hash } });
  }
  async function resume() {
    if (busy || !job || job.status !== 'AUTHORIZATION_REQUIRED') return;
    setBusy(true); setError('');
    const key = storageKey(ownerKey, job.job_id, 'resume');
    resumeId.current ??= stored(key) || crypto.randomUUID(); save(key, resumeId.current);
    try {
      await api<ChatReceipt>(`/api/v1/jobs/chat/${job.job_id}/resume`, { method: 'POST', body: JSON.stringify({ confirmed: true, authorization_id: resumeId.current }) });
      save(key, null); resumeId.current = null; await refreshSnapshot();
    } catch (cause) { fail(cause); }
    finally { if (mounted.current) setBusy(false); }
  }
  async function cancel() {
    if (busy || !job || chatStopped(job.status)) return;
    setBusy(true); setError('');
    try {
      await api(`/api/v1/jobs/chat/${job.job_id}/cancel`, { method: 'POST', body: '{}' });
      await refreshSnapshot();
    } catch (cause) { fail(cause); }
    finally { if (mounted.current) setBusy(false); }
  }
  const active = !!job && !chatStopped(job.status), blocked = busy || loading || active || !!pending || !!route.proposalId && pinned?.id !== route.proposalId;
  const openedCard = opened?.message.structured;
  function openPanel(message: ChatMessage, panel: ResultPanel) {
    panelTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelScroll.current = transcript.current?.scrollTop ?? null;
    setOpened({ message, panel });
  }
  function closePanel() {
    const scrollTop = panelScroll.current;
    setOpened(null);
    requestAnimationFrame(() => {
      panelTrigger.current?.focus({ preventScroll: true });
      if (transcript.current && scrollTop !== null) transcript.current.scrollTop = scrollTop;
    });
  }
  const resultContexts = new Map<string, { message: ChatMessage; recommendation: Recommendation }>();
  for (const message of history.items) {
    const card = message.structured;
    if (card?.type !== 'recommendation') continue;
    const recommendation = recommendations[card.recommendation_id];
    if (recommendation?.portfolio_id === portfolioId && sameFacts(card.facts, recommendation)) resultContexts.set(recommendation.id, { message, recommendation });
  }
  const orderedResults = [...resultContexts.values()].reverse();
  const currentResult = orderedResults.find(result => result.recommendation.id === pinned?.id) ?? orderedResults[0];
  const otherResults = orderedResults.filter(result => result !== currentResult);
  const renderContextResult = ({ message, recommendation }: typeof currentResult) => <button key={recommendation.id} className="quiet" type="button" onClick={() => openPanel(message, 'allocation')}>Xem phân bổ{recommendation.as_of_date && <small> · {recommendation.as_of_date}</small>}</button>;
  const allocation = route.proposalId ? (pinned?.id === route.proposalId && pinned.portfolio_id === portfolioId ? pinned : null) : savedAllocation(dashboard);
  const saved = !!allocation && allocation.id === dashboard?.accepted_target?.recommendation_id;
  const draftSuggestion = (question: string, purpose: SendMessage['intent'], id = '') => {
    setDraftAction({ intent: purpose, ...(id ? { recommendation_id: id } : {}) });
    setContent(question); setSuggested(true); input.current?.focus();
  };
  return <div className="chat-workspace chat-conversation chat-focused chat-plan" data-testid="chat-workspace">
    <OperationError error={error}/>{error && <button type="button" className="quiet" onClick={() => { setContextRevision(value => value + 1); void refreshSnapshot(); }}>Thử tải lại</button>}<div className="chat-layout" ref={layoutRef}><ConversationNavigation apiPage={apiPage} route={route} onSessionExpired={onSessionExpired} mobileOpen={historyOpen} setMobileOpen={setHistoryOpen}/><section className="chat-thread" aria-label="Cuộc trao đổi">
        <header className="chat-topline"><div className="chat-title"><h2>Trợ lý danh mục</h2><p className="muted small" title={conversation?.title}>{conversation?.title ?? 'Đang mở hội thoại…'}</p></div><div className="chat-topline-actions"><button type="button" className="quiet chat-history-trigger" onClick={() => setHistoryOpen(true)}>Lịch sử</button></div></header>
        <aside className="chat-context" aria-label="Ngữ cảnh danh mục"><details onKeyDown={event => { if (event.key === 'Escape') { setContextOpen(false); event.currentTarget.querySelector('summary')?.focus(); } }} open={contextOpen}><summary className="chat-context-summary" onClick={event => { event.preventDefault(); setContextOpen(value => !value); }}><ContextSummary dashboard={dashboard} portfolioId={portfolioId} allocation={allocation} expanded={contextOpen}/></summary><div className="chat-context-body"><div className="chat-context-picker"><PortfolioPicker api={api} apiPage={apiPage} value={portfolioId} onChange={value => { if (!value && conversation?.portfolio_id) { navigate({ view: 'chat' }); return; } portfolioRef.current = value; setPortfolioId(value); setContextOpen(false); setOpened(null); setPinned(null); setDashboard(null); setContent(''); setDraftAction({}); setSuggested(false); navigate({ view: 'chat', conversationId: cid, ...(value ? { portfolioId: value } : {}), ...(jobId ? { jobId } : {}) }); }} onError={fail} disabled={busy || active || !!pending}/></div>
      {dashboard ? <><dl className="chat-context-facts"><div><dt>Vốn kế hoạch</dt><dd>{money(dashboard.portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ rủi ro</dt><dd>{profileName(dashboard.portfolio.risk_profile?.profile)}</dd></div></dl>
        <details className="chat-context-more"><summary>Xem chi tiết danh mục</summary><dl className="chat-context-facts"><div><dt>Tỷ trọng tối đa / tài sản</dt><dd>{percent(dashboard.portfolio.constraints.max_position_weight)}</dd></div><div><dt>Mục tiêu đã lưu</dt><dd>{dashboard.accepted_target ? `Đã lưu ${dateTime(dashboard.accepted_target.accepted_at)}` : 'Chưa có mục tiêu được chấp nhận'}</dd></div><div><dt>Danh mục thực tế</dt><dd>{dashboard.holdings_status === 'PAPER_TRACKED' ? <a href={workspaceHash({ view: 'holdings', portfolioId })}>Xem tài khoản mô phỏng</a> : dashboard.holdings_status === 'NOT_TRACKED' ? 'Chưa theo dõi tài sản đang nắm giữ' : 'Chưa có thông tin nắm giữ'}</dd></div></dl><p className="muted small chat-context-note">Dữ liệu từ các dịch vụ quản lý danh mục và thị trường.</p></details></> : <p className="muted">{portfolioId ? 'Đang đọc dữ liệu danh mục…' : 'Chọn danh mục để trao đổi về hồ sơ và phương án phân bổ.'}</p>}
      <div className="chat-context-actions">{dashboard && <a className="button quiet" href={workspaceHash({ view: 'overview', portfolioId: dashboard.portfolio.id })}>Mở danh mục</a>}
        <IconButton icon="refresh" label="Tải lại trạng thái" onClick={() => { setError(''); setContextRevision(value => value + 1); void refreshSnapshot(); }} disabled={busy}/>
      </div>
    </div></details>
    {(currentResult || pinned || otherResults.length > 0) && <div className="chat-context-results" aria-label="Đề xuất đang trao đổi">
      {!saved && pinned?.portfolio_id === portfolioId && !resultContexts.has(pinned.id) && <a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId, proposalId: pinned.id })}>Xem đề xuất{pinned.as_of_date && ` · ${pinned.as_of_date}`}</a>}
      {currentResult && !(currentResult.message.structured?.type === 'recommendation' && currentResult.message.structured.selected_claim_ids?.some(id => id.startsWith('focus_'))) && renderContextResult(currentResult)}
      {otherResults.length > 0 && <details><summary>Các đề xuất khác</summary><div>{otherResults.map(renderContextResult)}</div></details>}
    </div>}
    </aside>{systemPaused && history.items.length > 0 && !saved && <p className="chat-pause-note muted small">Tính đề xuất mới đang tạm dừng.</p>}<div ref={transcript} className="chat-transcript" role="region" aria-label="Nội dung cuộc trao đổi" tabIndex={0} onScroll={event => { const element = event.currentTarget; const near = element.scrollHeight - element.scrollTop - element.clientHeight < 64; nearTranscriptEnd.current = near; setShowScrollEnd(!near); }}>
      {loading ? <div className="panel loading-state" role="status">Đang tải lịch sử…</div> : <><ol className="chat-messages" aria-label="Lịch sử tin nhắn">{history.items.map(message => {
        const card = message.structured;
        const facts = card?.type === 'market' || card?.type === 'profile' || card?.type === 'portfolio' ? card : null;
        const hasReply = !card || card.type === 'input_required' || !!facts || card.type === 'knowledge' || card.type !== 'recommendation' && card.type !== 'allocation_status' && card.response?.reason === 'VERIFIED';
        return <li className={`chat-message ${message.role === 'user' ? 'chat-user' : 'chat-assistant'}`} key={message.id} data-message-id={message.id}><div className="chat-message-byline"><strong>{message.role === 'user' ? 'Bạn' : 'Trợ lý danh mục'}</strong><time dateTime={message.created_at}>{dateTime(message.created_at)}</time></div>
          {hasReply && (message.role === 'user' ? <p className="chat-message-text">{message.content}</p> : <AnswerText content={card?.type === 'input_required' && card.fields.includes('strategy') ? 'Hãy gửi yêu cầu mới để hệ thống tính đề xuất.' : facts && !['equity_quote', 'gold_quote', 'asset_description', 'saved_target'].includes(String(facts.facts.scope)) && card?.response?.reason !== 'VERIFIED' ? factAnswer(facts) : message.content}/>)}
          {facts?.type === 'profile' && card?.response?.reason !== 'VERIFIED' && <RiskReason profile={(facts.facts.portfolio as ChatPortfolio | undefined)?.risk_profile}/>}
          {card?.type === 'allocation_status' && <AllocationStatusAnswer card={card} content={message.content} dashboard={dashboard} portfolioId={portfolioId} onRecheck={blocked ? undefined : () => draftSuggestion('Bây giờ tạo được chưa?', undefined)}/>}
          {card?.type === 'help' && !hasReply && <p className="chat-message-text">Bạn có thể hỏi về danh mục, hồ sơ rủi ro, giá thị trường hoặc cách tính phân bổ. Để tạo đề xuất, hãy chọn danh mục và xác nhận thông tin.</p>}
          {card?.type === 'knowledge' && (card.knowledge.citations.length ? <button type="button" className="quiet chat-turn-source" onClick={() => openPanel(message, 'sources')}>Xem nguồn tham khảo</button> : <ChatKnowledge evidence={card.knowledge}/>)}
          {card?.type === 'confirmation' && <ChatConfirmation card={card} disabled={blocked || job?.status !== 'WAITING_INPUT' || job.result_message_id !== message.id} onConfirm={() => confirm(card)}/>}
          {card?.type === 'recommendation' && <ChatRecommendation card={card} dashboard={dashboard} canonical={recommendations[card.recommendation_id]} evidence={evidenceById[card.recommendation_id]} content={message.content} isCurrentTarget={dashboard?.accepted_target?.recommendation_id === card.recommendation_id} onOpen={panel => openPanel(message, panel)} onExplain={!blocked && recommendations[card.recommendation_id]?.portfolio_id === portfolioId ? question => draftSuggestion(question, 'explain', card.recommendation_id) : undefined}/>}
          {facts && <div className="chat-fact-actions">
            {facts.type === 'market' && <QuoteHistoryLink card={facts} portfolioId={portfolioId || undefined}/>}
            {facts.type === 'market' ? <button type="button" className="quiet chat-turn-source" onClick={() => openPanel(message, 'sources')}>Xem dữ kiện và nguồn</button>
              : <details className="chat-turn-facts"><summary>Dữ kiện và nguồn</summary><ReadFacts card={facts}/></details>}
          </div>}
          {card?.type === 'input_required' && card.fields.includes('confirmed_risk_profile') && <a className="button quiet" href={workspaceHash({ view: 'risk-assessment', portfolioId: card.portfolio_id ?? portfolioId })}>Xem và xác nhận hồ sơ rủi ro</a>}
        </li>;
      })}</ol>{!history.items.length && <ChatWelcome ownerKey={ownerKey} portfolioId={portfolioId} allocation={allocation} saved={saved} paused={systemPaused} disabled={blocked} onDraft={draftSuggestion}/>}
        {history.total > history.limit && <Pagination total={history.total} offset={offset} limit={history.limit} onChange={value => { followLatest.current = false; setOffset(value); }}/>}</>}
      {job && <ChatTurnStatus job={job} resultVisible={!!job.result_message_id && history.items.some(message => message.id === job.result_message_id)} connection={connection} disabled={busy} onResume={() => void resume()} onCancel={() => void cancel()}/>}
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
      {pending && <aside className="notice warning chat-pending" role="alert"><strong>Yêu cầu chưa rõ trạng thái tiếp nhận</strong><p>{pending.confirmation ? 'Yêu cầu xác nhận đang được giữ nguyên để tránh tạo trùng. Chỉ gửi lại khi bạn chủ động xác nhận lần nữa.' : 'Nội dung và mã yêu cầu được giữ nguyên khi thử lại. Kết nối lại không tự gửi tin nhắn.'}</p><button data-testid="chat-retry" className="quiet" onClick={() => void submitBody(pending)} disabled={busy}>{pending.confirmation ? 'Xác nhận lại & gửi' : 'Gửi lại cùng yêu cầu'}</button></aside>}
      </div>{showScrollEnd && <button type="button" className="quiet chat-scroll-end" aria-label="Cuộn đến cuối vùng trao đổi" onClick={() => { if (transcript.current) { followLatest.current = true; nearTranscriptEnd.current = true; transcript.current.scrollTop = transcript.current.scrollHeight; setShowScrollEnd(false); const latestOffset = Math.floor(Math.max(0, history.total - 1) / history.limit) * history.limit; if (latestOffset !== offset) setOffset(latestOffset); else void refreshSnapshot(); } }}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M12 5v14m-5-5 5 5 5-5"/></svg>Xuống cuối</button>}
      <form className="panel chat-composer" onSubmit={send} aria-label="Soạn tin nhắn">
        <ComposerInput inputRef={input} id="chat-message-input" label="Tin nhắn của bạn" value={content} edit={editDraft}
          disabled={blocked} sending={busy} helpId="chat-composer-help"/>
        {suggested && <p className="chat-draft-note muted small" role="status">Đã điền gợi ý vào bản nháp.</p>}
        <p className="muted small" id="chat-composer-help">Enter để gửi · ⌘ + Enter để xuống dòng</p>
      </form>
    </section>
    {opened && openedCard && <ChatPanel key={opened.message.id + opened.panel} id="chat-result-panel" title={opened.panel === 'sources' ? 'Dữ kiện và nguồn' : 'Đề xuất đang trao đổi'} inline={sideBySide} onClose={closePanel}>
      <p className="muted small">Lượt trả lời lúc <time dateTime={opened.message.created_at}>{dateTime(opened.message.created_at)} (GMT+7)</time></p>
      {openedCard.type === 'recommendation' && <ChatRecommendation card={openedCard} canonical={recommendations[openedCard.recommendation_id]} evidence={evidenceById[openedCard.recommendation_id]} content={opened.message.content} isCurrentTarget={dashboard?.accepted_target?.recommendation_id === openedCard.recommendation_id} assets={assets} panel={opened.panel}/>}
      {openedCard.type === 'knowledge' && <ChatKnowledge evidence={openedCard.knowledge}/>}
      {(openedCard.type === 'portfolio' || openedCard.type === 'profile' || openedCard.type === 'market') && <ReadFacts card={openedCard}/>}
    </ChatPanel>}
    </div>
  </div>;
}

export function ChatWorkspace(props: ChatWorkspaceProps) {
  useChatKeyboard();
  const [firstMessage, setFirstMessage] = useState<FirstMessage>();
  useEffect(() => {
    if (firstMessage && props.route.conversationId !== firstMessage.conversationId) setFirstMessage(undefined);
  }, [firstMessage, props.route.conversationId]);
  return props.route.conversationId ? <ConversationWorkspace key={`${props.ownerKey}:${props.route.conversationId}`} {...props} firstMessage={firstMessage?.conversationId === props.route.conversationId ? firstMessage.body : undefined} onFirstMessageConsumed={() => setFirstMessage(undefined)}/> : <ConversationList key={`${props.ownerKey}:${props.route.portfolioId ?? ''}:${props.route.proposalId ?? ''}`} {...props} onFirstMessage={setFirstMessage}/>;
}
