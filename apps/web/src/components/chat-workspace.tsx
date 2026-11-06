'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ActionIcon, IconButton, type ActionIconName } from './action-controls';
import { AllocationView, money, profileName } from './allocation-view';
import { OperationError } from './operation-ui';
import { Pagination } from './portfolio-lifecycle';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { transcriptScrollAction, type TranscriptPosition } from '../lib/chat-scroll';
import { LatestRequest } from '../lib/latest-request';
import { workspaceHash, type WorkspaceRoute } from '../lib/workspace-state';
import { chatError, chatStage, chatStatus, chatStopped, createSseParser, readPending, sameFacts, storageKey, type ChatDashboard, type ChatJob, type ChatMessage, type ChatPortfolio, type ChatReceipt, type ConfirmationCard, type Conversation, type FactCard, type RecommendationCard, type SendMessage } from '../lib/chat-types';
import './chat-workspace.css';

export type ChatWorkspaceProps = { api: Api; apiPage: PageApi; route: WorkspaceRoute; navigate: (route: WorkspaceRoute) => void; ownerKey: string; onSessionExpired: () => void };
const emptyPage = <T,>(limit = 10): Page<T> => ({ items: [], total: 0, offset: 0, limit });
const percent = (value: number) => `${(value * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`;
const statusOf = (error: unknown) => error instanceof ApiError ? error.status : undefined;
const stored = (key: string) => { try { return sessionStorage.getItem(key); } catch { return null; } };
const save = (key: string, value: string | null) => { try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch { /* Explicit retry remains possible in this tab without storage. */ } };

export function ChatConsent({ checked, disabled, onChange, compact = false, saving = false }: { checked: boolean; disabled: boolean; onChange: (value: boolean) => void; compact?: boolean; saving?: boolean }) {
  const privacy = <p className="muted small">Gửi nội dung, ngữ cảnh ngắn và dữ liệu danh mục cần thiết đến OpenAI. Bạn vẫn xác nhận mọi đề xuất. Tắt để ngừng các lời gọi LLM mới.</p>;
  return <div className={`chat-consent${compact ? ' compact' : ''}`}><label aria-busy={saving || undefined}><input data-testid="chat-llm-consent" type="checkbox" checked={checked} disabled={disabled} onChange={event => onChange(event.target.checked)}/><span>Cho phép OpenAI hỗ trợ hội thoại này</span></label>{saving && <span className="chat-consent-status" role="status">Đang lưu lựa chọn…</span>}{compact ? <details className="chat-privacy"><summary>Dữ liệu gửi tới OpenAI</summary>{privacy}</details> : privacy}</div>;
}

export function ChatOptions({ intent, strategy, disabled, onIntent, onStrategy }: {
 intent: SendMessage['intent'] | ''; strategy: SendMessage['strategy'] | ''; disabled: boolean;
 onIntent: (value: SendMessage['intent'] | '') => void; onStrategy: (value: SendMessage['strategy'] | '') => void;
}) {
 const purposes: { value: SendMessage['intent'] | ''; label: string; icon: ActionIconName }[] = [
  {value:'',label:'Tự động',icon:'auto'}, {value:'portfolio',label:'Tóm tắt',icon:'portfolio'}, {value:'profile',label:'Hồ sơ',icon:'profile'},
  {value:'market',label:'Thị trường',icon:'market'}, {value:'allocation',label:'Tạo đề xuất',icon:'allocation'}, {value:'explain',label:'Giải thích',icon:'explain'}, {value:'help',label:'Trợ giúp',icon:'help'},
 ];
 return <div className="chat-composer-settings"><fieldset disabled={disabled}><legend>Mục đích</legend><div className="purpose-choices">{purposes.map(item=><label className="option-chip" key={item.value}><input type="radio" name="chat-intent" value={item.value} checked={intent===item.value} onChange={()=>onIntent(item.value)}/><ActionIcon name={item.icon}/><span>{item.label}</span></label>)}</div></fieldset>
 <fieldset disabled={disabled}><legend>Chiến lược khi tạo đề xuất</legend><div className="strategy-choices">{(['','EW','MVO','BL_ML'] as const).map(value=><label className="option-chip" key={value}><input type="radio" name="chat-strategy" data-testid={'chat-strategy-'+(value || 'auto')} value={value} checked={strategy===value} onChange={()=>onStrategy(value)}/><span>{value===''?'Tự động':value==='BL_ML'?'BL + ML':value}</span></label>)}</div><p className="muted small">Tự động: trợ lý sẽ hỏi thêm nếu chưa rõ lựa chọn. Chọn ở đây chưa gửi yêu cầu.</p></fieldset></div>;
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

function ConversationList({ api, apiPage, route, navigate, onSessionExpired }: ChatWorkspaceProps) {
  const [page, setPage] = useState(emptyPage<Conversation>()), [offset, setOffset] = useState(0), [revision, setRevision] = useState(0);
  const [title, setTitle] = useState('Hội thoại mới'), [portfolioId, setPortfolioId] = useState(route.portfolioId ?? '');
  const [loading, setLoading] = useState(true), [creating, setCreating] = useState(false), [error, setError] = useState('');
  useEffect(() => { setPortfolioId(route.portfolioId ?? ''); }, [route.portfolioId]);
  const alive = useRef(true), currentRoute = useRef(workspaceHash(route)); currentRoute.current = workspaceHash(route);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const names = useRef(new Map<string, string>()), [nameRevision, setNameRevision] = useState(0);
  const fail = useCallback((cause: unknown) => { setError(chatError(statusOf(cause))); if (statusOf(cause) === 401) onSessionExpired(); }, [onSessionExpired]);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    apiPage<Conversation>(`/api/v1/conversations?limit=10&offset=${offset}`).then(async result => {
      if (!active) return; setPage(result);
      const ids = [...new Set(result.items.map(item => item.portfolio_id).filter((id): id is string => !!id))];
      await Promise.all(ids.filter(id => !names.current.has(id)).map(async id => {
        try { const portfolio = await api<Portfolio>(`/api/v1/portfolios/${id}`); if (active) names.current.set(id, portfolio.name); }
        catch (cause) { if (statusOf(cause) === 401 && active) fail(cause); }
      }));
      if (active) setNameRevision(value => value + 1);
    }).catch(cause => { if (active) fail(cause); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, apiPage, offset, revision, fail]);
  async function create(event: FormEvent) {
    event.preventDefault(); if (creating || !title.trim()) return;
    const startedOn = currentRoute.current;
    setCreating(true); setError('');
    try {
      const result = await api<Conversation>('/api/v1/conversations', { method: 'POST', body: JSON.stringify({ title: title.trim(), ...(portfolioId ? { portfolio_id: portfolioId } : {}) }) });
      if (!alive.current || startedOn !== currentRoute.current) return;
      navigate({ view: 'chat', conversationId: result.id, ...(result.portfolio_id ? { portfolioId: result.portfolio_id } : {}) });
    } catch (cause) { if (alive.current) fail(cause); }
    finally { if (alive.current) setCreating(false); }
  }
  return <div className="chat-workspace" data-testid="chat-workspace"><OperationError error={error}/>
    <section className="panel chat-new" aria-labelledby="chat-new-heading"><div><h2 id="chat-new-heading">Bắt đầu một cuộc trao đổi</h2><p className="muted">Đọc hồ sơ, hiểu dữ liệu và xem lại đầu vào trước khi tạo đề xuất.</p></div>
      <form onSubmit={create} className="chat-create-form"><label>Chủ đề hội thoại<input data-testid="chat-title" value={title} onChange={event => setTitle(event.target.value)} maxLength={120} required disabled={creating}/></label>
        <PortfolioPicker api={api} apiPage={apiPage} value={portfolioId} onChange={setPortfolioId} onError={fail} disabled={creating}/>
        <button data-testid="chat-create" disabled={creating || !title.trim()}>{creating ? 'Đang tạo…' : 'Hội thoại mới'}</button>
      </form>
    </section>
    <section className="panel chat-conversations" aria-labelledby="chat-history-heading"><div className="section-heading"><h2 id="chat-history-heading">Hội thoại của bạn</h2><IconButton icon="refresh" label="Tải lại danh sách" onClick={() => setRevision(value => value + 1)} disabled={loading}/></div>
      {loading ? <p role="status" className="muted">Đang tải hội thoại…</p> : !page.items.length ? <div className="empty-state compact"><h3>Chưa có hội thoại</h3><p>Tạo hội thoại để bắt đầu. Lịch sử sẽ được lưu trong tài khoản của bạn.</p></div> : <div className="table-wrap mobile-cards"><table data-version={nameRevision}><caption>Những cuộc trao đổi đã lưu trong tài khoản</caption><thead><tr><th>Chủ đề</th><th>Danh mục</th><th>Ngày tạo</th><th><span className="sr-only">Mở hội thoại</span></th></tr></thead><tbody>{page.items.map(item => <tr key={item.id}><th scope="row">{item.title}</th><td data-label="Danh mục">{item.portfolio_id ? names.current.get(item.portfolio_id) ?? 'Chưa đọc được tên danh mục' : 'Chưa chọn'}</td><td data-label="Ngày tạo">{dateTime(item.created_at)}</td><td><a className="button quiet" href={workspaceHash({ view: 'chat', conversationId: item.id, ...(item.portfolio_id ? { portfolioId: item.portfolio_id } : {}) })}>Tiếp tục hội thoại<span className="sr-only">: {item.title}</span></a></td></tr>)}</tbody></table></div>}
      <Pagination total={page.total} offset={offset} limit={page.limit} onChange={setOffset} busy={loading}/>
    </section>
  </div>;
}

function PortfolioFacts({ portfolio }: { portfolio: ChatPortfolio }) {
  return <dl className="chat-facts"><div><dt>Danh mục</dt><dd>{portfolio.name}</dd></div><div><dt>Vốn kế hoạch</dt><dd>{money(portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ rủi ro</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div><div><dt>Phiên bản danh mục</dt><dd>{portfolio.version}</dd></div><div><dt>Tỷ trọng tối đa / tài sản</dt><dd>{percent(portfolio.constraints.max_position_weight)}</dd></div></dl>;
}

export function ChatConfirmation({ card, disabled, onConfirm }: { card: ConfirmationCard; disabled: boolean; onConfirm: () => void }) {
  const portfolio = card.input.portfolio, constraints = portfolio.constraints, answers = portfolio.risk_profile?.answers;
  const levels: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao', beginner: 'Mới bắt đầu', experienced: 'Có kinh nghiệm' };
  return <section className="chat-confirmation" aria-label="Xem lại đầu vào trước khi tạo đề xuất"><span className="badge">Cần xác nhận</span><h3>Xem lại trước khi tạo đề xuất</h3>
    {card.reason === 'STALE_CONFIRMATION' && <p className="notice warning">Danh mục hoặc hồ sơ đã thay đổi. Vui lòng xem lại đầu vào mới bên dưới.</p>}
    <PortfolioFacts portfolio={portfolio}/><dl className="chat-facts"><div><dt>Chiến lược</dt><dd>{card.input.strategy}</dd></div><div><dt>Bộ dữ liệu</dt><dd>{portfolio.universe_id}</dd></div></dl>
    <details className="chat-risk-details"><summary>Chi tiết hồ sơ và ràng buộc</summary><dl className="chat-facts"><div><dt>Mức ngại rủi ro</dt><dd>{constraints.risk_aversion}</dd></div>
      {constraints.min_defensive_weight !== undefined && <div><dt>Phòng thủ tối thiểu</dt><dd>{percent(constraints.min_defensive_weight)}</dd></div>}
      {constraints.max_non_defensive_weight !== undefined && <div><dt>Ngoài nhóm phòng thủ tối đa</dt><dd>{percent(constraints.max_non_defensive_weight)}</dd></div>}
      {!!constraints.defensive_asset_ids?.length && <div><dt>Tài sản phòng thủ</dt><dd>{constraints.defensive_asset_ids.join(', ')}</dd></div>}
      {answers && <><div><dt>Thời gian đầu tư</dt><dd>{answers.horizon_months} tháng</dd></div>{[['liquidity_need', 'Nhu cầu thanh khoản'], ['loss_tolerance', 'Khả năng chịu lỗ'], ['experience', 'Kinh nghiệm']].map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{levels[String(answers[key])] ?? String(answers[key] ?? '—')}</dd></div>)}</>}
      {answers?.questionnaire_version && <div><dt>Phiên bản câu hỏi</dt><dd>{answers.questionnaire_version}</dd></div>}
      {portfolio.risk_profile?.mapping_version && <div><dt>Phiên bản quy tắc hồ sơ</dt><dd>{portfolio.risk_profile.mapping_version}</dd></div>}
    </dl></details><p className="chat-confirm-note">Xác nhận sẽ tạo một đề xuất với đầu vào này. Bạn sẽ xem và quyết định lưu tỷ trọng mục tiêu ở bước tiếp theo.</p>
    <button data-testid="chat-confirm" disabled={disabled} onClick={onConfirm}>Xác nhận tạo đề xuất</button>{disabled && <p className="muted small">Chỉ thẻ của lượt chờ xác nhận hiện tại có thể được sử dụng.</p>}
    <details className="chat-audit"><summary>Nguồn và mã đối chiếu đầu vào</summary><dl><div><dt>Policy</dt><dd>{portfolio.policy_version_id}</dd></div><div><dt>Phiên bản hồ sơ</dt><dd>{portfolio.risk_profile?.version_id ?? 'Chưa xác nhận'}</dd></div><div><dt>Facts hash</dt><dd>{card.facts_hash}</dd></div><div><dt>Thẻ xác nhận</dt><dd>{card.confirmation_message_id}</dd></div></dl></details>
  </section>;
}

export function ChatRecommendation({ card, canonical, content }: { card: RecommendationCard; canonical: Recommendation | undefined; content: string }) {
  if (!canonical) return <div role="status" className="muted">Đang đối chiếu đề xuất với Portfolio…</div>;
  if (!sameFacts(card.facts, canonical)) return <div className="notice warning" role="alert">Nội dung đã lưu chưa khớp dữ liệu đề xuất hiện tại. Tải lại trạng thái để đối chiếu trước khi tiếp tục.</div>;
  return <section data-testid="chat-result" className="chat-recommendation" aria-label="Đề xuất từ kết quả định lượng"><div className="allocation-tags"><span className="badge success">Đề xuất đã lưu</span><span className="badge">{card.explanation_status === 'TEMPLATE' ? 'Giải thích theo mẫu dữ liệu' : 'Giải thích đã đối chiếu dữ liệu'}</span></div>
    <AllocationView allocation={canonical} compact metadata={false}/><details className="chat-explanation"><summary>Đọc giải thích phân bổ</summary><p className="chat-message-text">{content}</p></details><a data-testid="chat-open-recommendation" className="button" href={workspaceHash({ view: 'proposal', portfolioId: canonical.portfolio_id, proposalId: canonical.id })}>Xem đề xuất và quyết định</a>
    <p className="muted small">Chấp nhận chỉ lưu tỷ trọng mục tiêu. Chưa có giao dịch được thực hiện.</p>
    <details className="chat-audit"><summary>Nguồn và mã đối chiếu kết quả</summary><dl><div><dt>Facts hash</dt><dd>{card.facts_hash}</dd></div><div><dt>Input hash</dt><dd>{String((canonical as Recommendation & { input_hash?: string }).input_hash ?? '—')}</dd></div><div><dt>Snapshot</dt><dd>{canonical.data_snapshot_id}</dd></div><div><dt>Bundle hash</dt><dd>{canonical.bundle_hash}</dd></div><div><dt>Giải thích</dt><dd>{card.provider.model ?? 'Template'} · {card.provider.reason}</dd></div>{card.provider.input_tokens !== undefined && <div><dt>Token input / output</dt><dd>{card.provider.input_tokens} / {card.provider.output_tokens}</dd></div>}</dl></details>
  </section>;
}

function ReadFacts({ card }: { card: FactCard }) {
  const facts = card.facts;
  if (card.type === 'market') {
    const observations = Array.isArray(facts.observations) ? facts.observations as { revision_id: string; asset_id: string; price_vnd: string; observation_date: string; provider: string; data_origin: string }[] : [];
    return <section><h3>Dữ liệu thị trường gần nhất</h3><p className="muted small">Các quan sát gần đây; lịch phiên giao dịch chưa được xác minh.</p>{facts.status === 'STALE' && <p className="notice warning">Dữ liệu đang cũ. Cần cập nhật trước khi dùng cho quyết định mới.</p>}{observations.length ? <div className="table-wrap"><table><caption>Giá và nguồn do Market Service lưu</caption><thead><tr><th>Tài sản</th><th>Ngày</th><th>Giá</th><th>Nguồn</th></tr></thead><tbody>{observations.map(row => <tr key={row.revision_id}><th scope="row">{row.asset_id}</th><td>{row.observation_date}</td><td>{money(row.price_vnd)}</td><td>{row.provider} · {row.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}</td></tr>)}</tbody></table></div> : <p>Chưa có quan sát thị trường.</p>}<details className="chat-audit"><summary>Mã đối chiếu dữ liệu</summary><p>{card.facts_hash}</p></details></section>;
  }
  const portfolio = (card.type === 'profile' ? facts.portfolio : facts) as ChatPortfolio | null;
  return portfolio?.constraints ? <section><PortfolioFacts portfolio={portfolio}/><details className="chat-audit"><summary>Mã đối chiếu dữ liệu</summary><p>{card.facts_hash}</p></details></section> : null;
}

function ConversationNavigation({ apiPage, route, onSessionExpired }: Pick<ChatWorkspaceProps, 'apiPage' | 'route' | 'onSessionExpired'>) {
  // Start closed so the native initial toggle cannot race the mobile media-query effect.
  const [navigationOpen, setNavigationOpen] = useState(false);
  useEffect(() => { const query = window.matchMedia('(min-width: 1024px)'); const sync = () => setNavigationOpen(query.matches); sync(); query.addEventListener('change', sync); return () => query.removeEventListener('change', sync); }, []);
  const [page, setPage] = useState(emptyPage<Conversation>()), [offset, setOffset] = useState(0), [error, setError] = useState(false), [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true; setError(false);
    apiPage<Conversation>(`/api/v1/conversations?limit=10&offset=${offset}`).then(result => { if (active) setPage(result); }).catch(cause => { if (!active) return; setError(true); if (statusOf(cause) === 401) onSessionExpired(); });
    return () => { active = false; };
  }, [apiPage, offset, revision, onSessionExpired]);
  return <aside className="chat-navigation" aria-label="Danh sách hội thoại"><details open={navigationOpen} onToggle={event => setNavigationOpen(event.currentTarget.open)}><summary>Hội thoại của bạn</summary><a className="button quiet" href={workspaceHash({ view: 'chat', portfolioId: route.portfolioId })}>Hội thoại mới</a>{error ? <div role="status"><p>Chưa tải được danh sách.</p><button className="quiet" onClick={() => setRevision(value => value + 1)}>Thử lại</button></div> : <nav>{page.items.map(item => <a key={item.id} aria-current={item.id === route.conversationId ? 'page' : undefined} href={workspaceHash({ view: 'chat', conversationId: item.id, ...(item.portfolio_id ? { portfolioId: item.portfolio_id } : {}) })}>{item.title}<small>{dateTime(item.created_at)}</small></a>)}</nav>}<Pagination total={page.total} offset={offset} limit={page.limit} onChange={setOffset}/></details></aside>;
}

export function ChatTurnStatus({ job, resultVisible, connection, disabled, onResume }: {
  job: ChatJob; resultVisible: boolean; connection: string; disabled: boolean; onResume: () => void;
}) {
  // The answer or confirmation already carries its own meaning. A completed chat
  // turn is not a receipt for saving a proposal or accepting a portfolio target.
  if (resultVisible && ['SUCCEEDED', 'WAITING_INPUT'].includes(job.status)) return null;
  if (job.status === 'SUCCEEDED') return <p className="chat-turn-complete muted small" data-testid="chat-job" role="status">Đã xử lý lượt trao đổi.</p>;
  const running = !chatStopped(job.status);
  return <section className="chat-job" data-testid="chat-job" aria-label="Trạng thái lượt trao đổi" role="status">
    <strong>{chatStatus(job.status)}</strong>{(running || job.status === 'WAITING_INPUT') && <p>{chatStage(job.stage)}</p>}
    {running && <p className="muted small">{connection === 'connected' ? 'Đang cập nhật tiến trình.' : connection === 'retrying' ? 'Đang kết nối lại. Trạng thái vẫn được kiểm tra.' : 'Đang kết nối tiến trình…'}</p>}
    {job.status === 'FAILED' && <p>Yêu cầu chưa hoàn tất. Xem lại dữ liệu và đầu vào trước khi gửi một lượt mới.</p>}
    {job.status === 'AUTHORIZATION_REQUIRED' && <><p>Quyền của lượt này đã hết hạn. Cấp lại quyền để tiếp tục cùng yêu cầu.</p><button className="quiet" onClick={onResume} disabled={disabled}>Cấp lại quyền và tiếp tục</button></>}
  </section>;
}

function ConversationWorkspace({ api, apiPage, route, navigate, ownerKey, onSessionExpired }: ChatWorkspaceProps) {
  const cid = route.conversationId!;
  const [conversation, setConversation] = useState<Conversation | null>(null), [history, setHistory] = useState(emptyPage<ChatMessage>(50)), [offset, setOffset] = useState(0);
  const [job, setJob] = useState<ChatJob | null>(null), [recommendations, setRecommendations] = useState<Record<string, Recommendation>>({});
  const [portfolioId, setPortfolioId] = useState(route.portfolioId ?? ''), [dashboard, setDashboard] = useState<ChatDashboard | null>(null), [contextRevision, setContextRevision] = useState(0);
  const [contextOpen, setContextOpen] = useState(false);
  const [content, setContent] = useState(''), [strategy, setStrategy] = useState<SendMessage['strategy'] | ''>(''), [intent, setIntent] = useState<SendMessage['intent'] | ''>(''), [recommendationId, setRecommendationId] = useState('');
  const [consentSaving, setConsentSaving] = useState(false);
  const [pending, setPending] = useState<SendMessage | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'retrying' | 'saved'>('connecting'), [announcement, setAnnouncement] = useState('');
  const transientError = useRef(false);
  const mounted = useRef(true), snapshots = useRef(new LatestRequest()), sending = useRef(false), followLatest = useRef(true), jobRef = useRef<ChatJob | null>(null), portfolioRef = useRef(portfolioId), pendingRef = useRef<SendMessage | null>(null);
  const desiredJob = useRef(route.jobId);
  useEffect(() => { desiredJob.current = route.jobId; }, [route.jobId]);
  const composer = useRef<HTMLFormElement>(null);
  const input = useRef<HTMLTextAreaElement>(null), resumeId = useRef<string | null>(null);
  useEffect(() => {
    const node = composer.current;
    if (!node) return;
    // The proposal-ID field and textarea can change composer height while options are open.
    const update = () => node.style.setProperty('--chat-options-available-height', `${Math.max(80, Math.floor(node.getBoundingClientRect().top) - 16)}px`);
    const observer = new ResizeObserver(update);
    observer.observe(node); window.addEventListener('resize', update); update();
    return () => { observer.disconnect(); window.removeEventListener('resize', update); };
  }, []);
  const transcript = useRef<HTMLDivElement>(null), previousTranscript = useRef<TranscriptPosition | null>(null), nearTranscriptEnd = useRef(true);
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
        const [current, initialPage] = await Promise.all([api<Conversation>(`/api/v1/conversations/${cid}`), apiPage<ChatMessage>(`/api/v1/conversations/${cid}/messages?limit=50&offset=${offset}`)]);
        const latestOffset = Math.floor(Math.max(0, initialPage.total - 1) / initialPage.limit) * initialPage.limit;
        const page = followLatest.current && nearTranscriptEnd.current && initialPage.offset !== latestOffset
          ? await apiPage<ChatMessage>(`/api/v1/conversations/${cid}/messages?limit=50&offset=${latestOffset}`) : initialPage;
        const jid = desiredJob.current ?? current.active_job_id;
        const state = jid ? await api<ChatJob>(`/api/v1/jobs/chat/${jid}`) : null;
        if (state && state.conversation_id !== cid) throw new ApiError(404, '');
        const ids = [...new Set(page.items.flatMap(message => message.structured?.type === 'recommendation' ? [message.structured.recommendation_id] : []))];
        const canonical = await Promise.all(ids.map(id => api<Recommendation>(`/api/v1/recommendations/${id}`)));
        return { current, page, state, canonical };
      });
      if (!snapshot || !mounted.current) return null;
      const { current, page, state, canonical } = snapshot;
      // A reader may scroll up while the latest-page request is in flight.
      if (page.offset !== offset && !nearTranscriptEnd.current) return null;
      if (transientError.current) { transientError.current = false; setError(''); }
      if (page.offset !== offset) setOffset(page.offset);
      setConversation(current); setHistory(page);
      if (!portfolioRef.current && current.portfolio_id) { portfolioRef.current = current.portfolio_id; setPortfolioId(current.portfolio_id); }
      setRecommendations(Object.fromEntries(canonical.map(item => [item.id, item]))); jobRef.current = state; setJob(state);
      const draft = pendingRef.current;
      if (draft && page.items.some(message => message.client_message_id === draft.client_message_id)) { rememberPending(null); setContent(value => value === draft.content ? '' : value); }
      if (state && chatStopped(state.status)) { setConnection('saved'); setAnnouncement(chatStatus(state.status)); }
      return state;
    } catch (cause) { fail(cause); return null; }
    finally { if (mounted.current) setLoading(false); }
  }, [api, apiPage, cid, offset, route.jobId, rememberPending, fail]);
  useEffect(() => { void refreshSnapshot(); }, [refreshSnapshot]);

  useEffect(() => {
    let active = true; setDashboard(null);
    if (portfolioId) api<ChatDashboard>(`/api/v1/portfolios/${portfolioId}/dashboard`).then(value => { if (active) setDashboard(value); }).catch(cause => { if (active) fail(cause); });
    return () => { active = false; };
  }, [api, portfolioId, contextRevision, fail]);

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
      rememberPending(null); setContent(''); setAnnouncement('Yêu cầu đã được tiếp nhận.'); followLatest.current = true;
      // Keep the known receipt in the URL before any further network call. A
      // failed status read must never lose a successfully accepted job identity.
      navigate({ view: 'chat', conversationId: cid, ...(body.portfolio_id ? { portfolioId: body.portfolio_id } : {}), jobId: receipt.job_id });
      await refreshSnapshot();
    } catch (cause) {
      if (!mounted.current) return;
      const status = statusOf(cause);
      if (status && [400, 403, 404, 409, 412, 422].includes(status)) rememberPending(null);
      fail(cause); void refreshSnapshot();
    } finally { sending.current = false; if (mounted.current) setBusy(false); }
  }
  function send(event?: FormEvent) {
    event?.preventDefault(); if (!content.trim() || busy || loading || consentSaving || pending || job && !chatStopped(job.status)) return;
    const body: SendMessage = { content: content.trim(), client_message_id: crypto.randomUUID(), ...(portfolioId ? { portfolio_id: portfolioId } : {}), ...(strategy ? { strategy } : {}), ...(intent ? { intent } : {}), ...(intent === 'explain' && recommendationId ? { recommendation_id: recommendationId } : {}) };
    void submitBody(body);
  }
  async function changeConsent(value: boolean) {
    if (consentSaving) return;
    setConsentSaving(true); setError(''); snapshots.current.invalidate();
    try {
      const updated = await api<Conversation>(`/api/v1/conversations/${cid}/preferences`, { method: 'POST', body: JSON.stringify({ llm_consent: value }) });
      if (mounted.current) { setConversation(updated); setAnnouncement(value ? 'Đã cho phép LLM hỗ trợ hội thoại.' : 'Đã tắt các lời gọi LLM mới.'); }
    } catch (cause) { fail(cause); }
    finally { if (mounted.current) { setConsentSaving(false); void refreshSnapshot(); } }
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
  const active = !!job && !chatStopped(job.status), blocked = busy || loading || active || !!pending;
  return <div className="chat-workspace chat-conversation chat-focused" data-testid="chat-workspace"><header className="chat-topline"><div><h2 title={conversation?.title}>{conversation?.title ?? 'Đang mở hội thoại…'}</h2><p className="muted small">Trao đổi về danh mục · Đề xuất mới luôn cần xác nhận</p></div><div className="chat-topline-actions"><a className="chat-all-link" href={workspaceHash({ view: 'chat' })}>Tất cả hội thoại</a><IconButton icon="refresh" label="Tải lại trạng thái" onClick={() => { setError(''); setContextRevision(value => value + 1); void refreshSnapshot(); }} disabled={busy}/></div></header>
    <OperationError error={error}/><div className="chat-layout"><ConversationNavigation apiPage={apiPage} route={route} onSessionExpired={onSessionExpired}/><section className="chat-thread" aria-label="Cuộc trao đổi"><aside className="chat-context" aria-label="Ngữ cảnh danh mục"><details onKeyDown={event => { if (event.key === 'Escape') { setContextOpen(false); event.currentTarget.querySelector('summary')?.focus(); } }} open={contextOpen}><summary className="chat-context-summary" onClick={event => { event.preventDefault(); setContextOpen(value => !value); }}><span className="chat-context-label"><span className="sr-only">Danh mục đang trao đổi: </span>{dashboard?.portfolio.name ?? (portfolioId ? 'Đang đọc danh mục…' : 'Chọn danh mục trao đổi')}</span><span className="chat-context-preview">{dashboard ? `${money(dashboard.portfolio.capital_vnd)} · ${profileName(dashboard.portfolio.risk_profile?.profile)}` : 'Hồ sơ và giới hạn đi cùng danh mục bạn chọn'}</span><span className="chat-context-affordance">{contextOpen ? 'Thu gọn' : 'Chi tiết'}</span></summary><div className="chat-context-body"><details className="chat-context-picker"><summary>Đổi danh mục trao đổi</summary><PortfolioPicker api={api} apiPage={apiPage} value={portfolioId} onChange={value => { portfolioRef.current = value; setPortfolioId(value); navigate({ view: 'chat', conversationId: cid, ...(value ? { portfolioId: value } : {}), ...(jobId ? { jobId } : {}) }); }} onError={fail} disabled={busy || active || !!pending}/></details>
      {dashboard ? <><PortfolioFacts portfolio={dashboard.portfolio}/><dl className="chat-context-facts"><div><dt>Mục tiêu đã lưu</dt><dd>{dashboard.accepted_target ? `Đã lưu ${dateTime(dashboard.accepted_target.accepted_at)}` : 'Chưa có mục tiêu được chấp nhận'}</dd></div><div><dt>Danh mục thực tế</dt><dd>{dashboard.holdings_status === 'NOT_TRACKED' ? 'Chưa theo dõi tài sản đang nắm giữ' : 'Chưa có thông tin nắm giữ'}</dd></div></dl><a className="button quiet" href={workspaceHash({ view: 'overview', portfolioId: dashboard.portfolio.id })}>Mở danh mục</a></> : <p className="muted">{portfolioId ? 'Đang đọc dữ liệu danh mục…' : 'Chọn danh mục để trao đổi về hồ sơ và phương án phân bổ.'}</p>}
      <p className="muted small chat-context-note">Dữ liệu từ các dịch vụ quản lý danh mục và thị trường. Giải thích hỗ trợ bạn xem xét quyết định.</p>
    </div></details>
    </aside><div ref={transcript} className="chat-transcript" role="region" aria-label="Nội dung cuộc trao đổi" tabIndex={0} onScroll={event => { const element = event.currentTarget; const near = element.scrollHeight - element.scrollTop - element.clientHeight < 64; nearTranscriptEnd.current = near; setShowScrollEnd(!near); }}>
      {loading ? <div className="panel loading-state" role="status">Đang tải lịch sử…</div> : <><ol className="chat-messages" aria-label="Lịch sử tin nhắn">{history.items.map(message => {
        const card = message.structured;
        return <li className={`chat-message ${message.role === 'user' ? 'chat-user' : 'chat-assistant'}`} key={message.id} data-message-id={message.id}><div className="chat-message-byline"><strong>{message.role === 'user' ? 'Bạn' : 'Trợ lý danh mục'}</strong><time dateTime={message.created_at}>{dateTime(message.created_at)}</time></div>
          {card?.type !== 'recommendation' && <p className="chat-message-text">{message.content}</p>}
          {card?.dialogue?.reason === 'VERIFIED' && <details className="chat-message-source"><summary>Nguồn hỗ trợ trả lời</summary><p className="muted small">OpenAI hỗ trợ hiểu yêu cầu. Hệ thống kiểm tra dữ liệu và quyền thực hiện.</p></details>}
          {card?.type === 'confirmation' && <ChatConfirmation card={card} disabled={blocked || job?.status !== 'WAITING_INPUT' || job.result_message_id !== message.id} onConfirm={() => confirm(card)}/>}
          {card?.type === 'recommendation' && <ChatRecommendation card={card} canonical={recommendations[card.recommendation_id]} content={message.content}/>}
          {(card?.type === 'portfolio' || card?.type === 'profile' || card?.type === 'market') && <ReadFacts card={card}/>}
          {card?.type === 'input_required' && card.fields.includes('confirmed_risk_profile') && <a className="button quiet" href={workspaceHash({ view: 'risk-assessment', portfolioId: card.portfolio_id ?? portfolioId })}>Xem và xác nhận hồ sơ rủi ro</a>}
        </li>;
      })}</ol>{!history.items.length && <div className="panel chat-welcome"><h3>Bạn muốn hiểu điều gì về danh mục?</h3><p className="muted">Tôi có thể đọc hồ sơ rủi ro, tóm tắt danh mục, xem dữ liệu thị trường và tạo đề xuất sau khi bạn xác nhận đầu vào.</p><div className="chat-starters">{[['portfolio', 'Tóm tắt danh mục của tôi'], ['profile', 'Xem hồ sơ rủi ro'], ['allocation', 'Tạo đề xuất phân bổ']].map(([kind, label]) => <button className="quiet" key={kind} onClick={() => { setIntent(kind as SendMessage['intent']); setContent(label); input.current?.focus(); }}>{label}</button>)}</div></div>}
        {history.total > history.limit && <Pagination total={history.total} offset={offset} limit={history.limit} onChange={value => { followLatest.current = false; setOffset(value); }}/>}</>}
      {job && <ChatTurnStatus job={job} resultVisible={!!job.result_message_id && history.items.some(message => message.id === job.result_message_id)} connection={connection} disabled={busy} onResume={() => void resume()}/>}
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
      {pending && <aside className="notice warning chat-pending" role="alert"><strong>Yêu cầu chưa rõ trạng thái tiếp nhận</strong><p>{pending.confirmation ? 'Yêu cầu xác nhận đang được giữ nguyên để tránh tạo trùng. Chỉ gửi lại khi bạn chủ động xác nhận lần nữa.' : 'Nội dung và mã yêu cầu được giữ nguyên khi thử lại. Kết nối lại không tự gửi tin nhắn.'}</p><button data-testid="chat-retry" className="quiet" onClick={() => void submitBody(pending)} disabled={busy}>{pending.confirmation ? 'Xác nhận lại & gửi' : 'Gửi lại cùng yêu cầu'}</button></aside>}
      </div>{showScrollEnd && <button type="button" className="quiet chat-scroll-end" aria-label="Cuộn đến cuối vùng trao đổi" onClick={() => { if (transcript.current) { followLatest.current = true; nearTranscriptEnd.current = true; transcript.current.scrollTop = transcript.current.scrollHeight; setShowScrollEnd(false); const latestOffset = Math.floor(Math.max(0, history.total - 1) / history.limit) * history.limit; if (latestOffset !== offset) setOffset(latestOffset); else void refreshSnapshot(); } }}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M12 5v14m-5-5 5 5 5-5"/></svg>Xuống cuối</button>}
      <form ref={composer} className="panel chat-composer" onSubmit={send} aria-label="Soạn tin nhắn"><label className="sr-only" htmlFor="chat-message-input">Tin nhắn của bạn</label><div className="chat-input-row"><textarea ref={input} id="chat-message-input" data-testid="chat-input" value={content} onChange={event => setContent(event.target.value)} maxLength={4000} rows={2} disabled={blocked || consentSaving} placeholder="Hỏi về danh mục hoặc yêu cầu một phương án phân bổ…" aria-describedby="chat-composer-help" onKeyDown={event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}/><IconButton icon="send" label={busy ? 'Đang gửi tin nhắn' : 'Gửi tin nhắn'} data-testid="chat-send" type="submit" className="send-button" disabled={blocked || consentSaving || !content.trim()}/></div>
        {intent === 'explain' && <label>Mã đề xuất<input value={recommendationId} onChange={event => setRecommendationId(event.target.value)} disabled={blocked} pattern="[a-fA-F0-9-]{36}" required autoComplete="off"/></label>}
        <div className="chat-composer-tools"><ChatConsent compact saving={consentSaving} checked={conversation?.llm_consent === true} disabled={!conversation || consentSaving || busy} onChange={value => void changeConsent(value)}/><details className="chat-advanced" onKeyDown={event => { if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus(); } }}><summary aria-label="Tùy chọn hội thoại"><ActionIcon name="options"/><span className="control-tooltip" aria-hidden="true">Tùy chọn hội thoại</span></summary><ChatOptions intent={intent} strategy={strategy} disabled={blocked || consentSaving} onIntent={setIntent} onStrategy={setStrategy}/></details></div>
        <p className="muted small" id="chat-composer-help">Ctrl / ⌘ + Enter để gửi · Chấp nhận mục tiêu tại màn hình đề xuất</p>
      </form>
    </section></div>
  </div>;
}

export function ChatWorkspace(props: ChatWorkspaceProps) {
  return props.route.conversationId ? <ConversationWorkspace key={`${props.ownerKey}:${props.route.conversationId}`} {...props}/> : <ConversationList {...props}/>;
}
