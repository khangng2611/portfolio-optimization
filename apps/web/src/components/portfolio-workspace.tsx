'use client';
import { PaperReviewReminder } from './paper-portfolio';
import { AnswerRows, RiskReason } from './risk-questions';
import { TaskActions } from './task-actions';
import { isSelectionReadiness, type AssetCatalogItem } from '../lib/selection-types';
import { useEffect, useState, type ReactNode, type Ref } from 'react';
import './portfolio-workspace.css';
import { AllocationView, money, percentage, profileName } from './allocation-view';
import { SavedRecommendationEvidence } from './recommendation-evidence';
import { JobTrace } from './job-trace';
import { dateTime, type Api, type Dashboard, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { assetUniverseName, readinessAllows, readinessReason, workspaceHash, type Readiness } from '../lib/workspace-state';

const portfolioLink = (id: string, view: 'overview' | 'proposal' | 'history' | 'profile' | 'edit' | 'chat' | 'risk-assessment') => workspaceHash({ view, portfolioId: id });

export function proposalStrategy(portfolio: Portfolio, readiness: Readiness | null | undefined) {
  if (portfolio.universe_id === 'DEMO' && readiness && !isSelectionReadiness(readiness) && readiness.demo) return readinessAllows(readiness, 'EW', false) ? 'EW' : 'MVO';
  return 'HYBRID';
}

const compactCapital = new Intl.NumberFormat('vi-VN', { notation: 'compact', compactDisplay: 'long', maximumFractionDigits: 2 });
const shortDate = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });

const proposalLabel = (id: string) => id.slice(0, 8);
function DataDay({ day }: { day?: string }) {
  return day && Number.isFinite(Date.parse(day)) ? <time dateTime={day}>{shortDate.format(new Date(day))}</time> : <>chưa xác định</>;
}

export function PlanHeading({ portfolio, recommendation, headingRef }: { portfolio: Portfolio; recommendation?: Recommendation | null; headingRef?: Ref<HTMLHeadingElement> }) {
  const horizon = portfolio.risk_profile?.answers?.horizon_months;
  return <header className="plan-heading"><h1 title={recommendation?.id} ref={headingRef} tabIndex={-1}>{recommendation ? `Đề xuất ${proposalLabel(recommendation.id)}` : portfolio.name}</h1>
    {recommendation ? <p>{portfolio.name} · Dữ liệu <DataDay day={recommendation.as_of_date}/></p> :
      <p><span title={money(portfolio.capital_vnd)}>Vốn hiện tại {compactCapital.format(Number(portfolio.capital_vnd))} ₫</span>{horizon ? <> · {horizon} tháng</> : null} · {profileName(portfolio.risk_profile?.profile)}</p>}
  </header>;
}

function StatusCard({ title, message, children, tone = 'neutral', testId }: {
  title: string; message: string; children: ReactNode; tone?: 'good' | 'warning' | 'neutral'; testId?: string;
}) {
  return <aside className="plan-status" data-tone={tone} data-testid={testId} aria-label="Việc tiếp theo">
    <div><h2>{title}</h2><p>{message}</p></div><div className="plan-status-actions">{children}</div>
  </aside>;
}

type PlanProps = { portfolio: Portfolio; dashboard: Dashboard | null; readiness?: Readiness | null; universeAssetIds?: string[] };
function PlanDetails({ portfolio, universeAssetIds, readiness, children, onRefresh, showFacts = false }: Pick<PlanProps, 'portfolio' | 'universeAssetIds' | 'readiness'> & { children?: ReactNode; onRefresh?: () => void; showFacts?: boolean }) {
  const basket = portfolio.asset_selection?.candidate_asset_ids ?? universeAssetIds;
  const horizon = portfolio.risk_profile?.answers?.horizon_months;
  return <section className="plan-details" aria-label="Chi tiết kế hoạch">
    {showFacts && <div className="plan-current-facts">
      <h2>Vốn kế hoạch hiện tại</h2><strong>{money(portfolio.capital_vnd)}</strong>
      <dl><div><dt>Thời gian đầu tư</dt><dd>{horizon ? `${horizon} tháng` : 'Chưa xác định'}</dd></div>
        <div><dt>Hồ sơ rủi ro</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div></dl>
    </div>}
    <details className="plan-disclosure"><summary>{showFacts ? 'Xem rổ tài sản' : 'Chi tiết kế hoạch'}</summary>
    <h3>Rổ tài sản hiện tại</h3>
    <p>{basket ? basket.join(' · ') || 'Rổ chưa có tài sản.' : assetUniverseName(portfolio.universe_id)}</p>
    <p>{basket && `${basket.length} tài sản trong rổ. `}Tài sản được cân nhắc có thể nhận tỷ trọng 0%.</p>
    <a href={portfolioLink(portfolio.id, 'edit')}>Sửa danh mục</a>
    <details><summary>Tài khoản mô phỏng</summary>
      <p>Sau khi chấp nhận mục tiêu, bạn có thể mở tài khoản mô phỏng và xem trước lệnh.</p>
      <div className="actions"><a href={workspaceHash({ view: 'holdings', portfolioId: portfolio.id })}>Tài sản và hiệu suất</a><a href={workspaceHash({ view: 'rebalance', portfolioId: portfolio.id })}>Tái cân bằng</a></div>
    </details>
    <details id="methodology"><summary>Dữ liệu và cách tính</summary>
      <p>Vốn kế hoạch hiện tại {money(portfolio.capital_vnd)}. Phân bổ sử dụng vốn, rổ tài sản và hồ sơ tại lần tính.</p>
      {readiness?.reason_code && readinessReason[readiness.reason_code] && <p>{readinessReason[readiness.reason_code]}</p>}
      {readiness?.checked_at && <p>Kiểm tra dữ liệu lúc {dateTime(readiness.checked_at)} (GMT+7).</p>}
      {children}
      {onRefresh && <button type="button" className="quiet" onClick={onRefresh}>Kiểm tra lại dữ liệu</button>}
    </details></details>
  </section>;
}

function PausedStatus({ id, hasProposals, proposalView = false }: { id: string; hasProposals: boolean | undefined; proposalView?: boolean }) {
  const history = workspaceHash({ view: 'proposal', portfolioId: id, focus: 'history' });
  const message = hasProposals ? 'Bạn vẫn xem được phân bổ và căn cứ của các đề xuất đã lưu.'
    : hasProposals === undefined ? 'Bạn có thể trao đổi về kế hoạch hiện tại với trợ lý.'
    : proposalView ? 'Danh mục chưa có đề xuất. Bạn vẫn có thể trao đổi về kế hoạch.' : 'Bạn chưa có đề xuất. Trợ lý vẫn có thể giải thích kế hoạch hiện tại.';
  return <StatusCard title="Tạm dừng tạo đề xuất" message={message} tone="warning" testId="paused-input-notice">
    <a className="button" href={hasProposals ? history : portfolioLink(id, 'chat')}>{hasProposals ? 'Xem lịch sử đề xuất' : 'Hỏi về kế hoạch'}</a>
  </StatusCard>;
}

export function PausedProposal({ portfolio, dashboard, readiness, universeAssetIds, onRefresh }: PlanProps & { onRefresh?: () => void }) {
  const hasProposals = dashboard ? dashboard.proposal_count > 0 : undefined;
  return <section className="plan-overview plan-surface"><div className="plan-empty-grid">
    <div className="plan-decision overview-next-step"><PausedStatus id={portfolio.id} hasProposals={hasProposals} proposalView/></div>
    <PlanDetails showFacts portfolio={portfolio} readiness={readiness} universeAssetIds={universeAssetIds} onRefresh={onRefresh}/>
  </div></section>;
}

export function ProposalReview({ portfolio, recommendation, accepted, stale, conflict, busy, onAccept, viewerBase, assets, readiness, readinessFailed, onRefresh, universeAssetIds, api }: {
  portfolio: Portfolio; recommendation: Recommendation; accepted: boolean; stale: boolean; conflict: boolean; busy: boolean; onAccept: () => void; viewerBase: string | null; assets?: AssetCatalogItem[]; readiness?: Readiness | null; readinessFailed?: boolean; onRefresh?: () => void; universeAssetIds?: string[]; api?: Api;
}) {
  const historical = stale && !accepted;
  const paused = readiness?.reason_code === 'SYSTEM_PAUSED';
  const canCalculate = !!portfolio.risk_profile && readinessAllows(readiness ?? null, proposalStrategy(portfolio, readiness), false);
  const changed = recommendation.portfolio_version !== portfolio.version;
  const expiry = Date.parse(recommendation.valid_until ?? '');
  const expired = expiry <= Date.now();
  const [sourcesOpened, setSourcesOpened] = useState(false);
  const label = proposalLabel(recommendation.id);
  const historyLink = workspaceHash({ view: 'proposal', portfolioId: portfolio.id, focus: 'history' });
  const requestLink = workspaceHash({ view: 'proposal', portfolioId: portfolio.id, focus: 'request' });
  const chatLink = workspaceHash({ view: 'chat', portfolioId: portfolio.id, proposalId: recommendation.id });
  const staleTitle = expired ? paused ? 'Hết hạn · Tính mới tạm dừng' : 'Đề xuất đã hết hạn' : changed ? 'Đầu vào đã thay đổi sau khi tính' : 'Chưa xác minh được hiệu lực đề xuất';
  const staleMessage = paused ? `${label} đã khóa chấp nhận. Bạn vẫn xem được tỷ trọng và căn cứ của lần tính.`
    : canCalculate ? `${label} chỉ còn để tham khảo. Xem lại đầu vào trước khi xác nhận tính mới.`
    : !readiness ? readinessFailed ? 'Chưa xác định được tình trạng dữ liệu để tính mới.' : 'Đang kiểm tra dữ liệu để tính mới.'
    : readinessReason[readiness.reason_code] ?? 'Dữ liệu hiện tại chưa đủ điều kiện tính mới.';
  return <section className="proposal-review plan-surface"><div className="plan-result-grid">
    <StatusCard title={historical ? staleTitle : accepted ? 'Đã lưu mục tiêu' : 'Chờ xem xét'} tone={historical ? 'warning' : 'good'}
      message={historical ? staleMessage : accepted ? 'Danh mục đang dùng tỷ trọng mục tiêu này.' : 'Chấp nhận sẽ lưu tỷ trọng của đề xuất này làm mục tiêu của danh mục.'}
      testId={historical ? 'stale-proposal-notice' : undefined}>
      {historical ? <a className="button" href={canCalculate && !paused ? requestLink : historyLink}>{canCalculate && !paused ? 'Xem lại đầu vào' : 'Xem lịch sử đề xuất'}</a>
        : accepted ? <a className="button" href={portfolioLink(portfolio.id, 'overview')}>Về tổng quan</a>
        : <button type="button" data-testid="accept-proposal" disabled={busy || conflict} onClick={onAccept}>{busy ? 'Đang lưu…' : 'Chấp nhận làm mục tiêu'}</button>}
      {historical && !readiness && readinessFailed && onRefresh && <button type="button" className="quiet" onClick={onRefresh}>Kiểm tra lại</button>}
    </StatusCard>
    <section className="allocation-primary" aria-label={historical ? 'Phân bổ của lần tính cũ' : accepted ? 'Phân bổ đã lưu' : 'Phân bổ đề xuất'}>
      <AllocationView key={recommendation.id} allocation={recommendation} assets={assets} pricePortfolioId={portfolio.id} priceProposalId={recommendation.id} presentation="summary" summaryVariant="compact" metadata={false} capitalLabel="Vốn tại lần tính" chartTitle={historical ? 'Phân bổ của lần tính cũ' : accepted ? 'Phân bổ đã lưu' : 'Phân bổ đề xuất'}/>
    </section>
    <div className="plan-result-details">
      <details className="plan-evidence plan-disclosure" onToggle={event => { if (event.currentTarget.open) setSourcesOpened(true); }}><summary>Căn cứ và nguồn</summary>
        <h3>Căn cứ, giới hạn và nguồn</h3>
        <p>Đề xuất {label} · Ngày dữ liệu <DataDay day={recommendation.as_of_date}/>.</p>
        {api && sourcesOpened && <SavedRecommendationEvidence key={recommendation.id} facts={recommendation} api={api}/>}
        <p>Hồ sơ khi tính đề xuất · {profileName(recommendation.risk_profile?.profile)}. Tài sản được cân nhắc có thể nhận tỷ trọng 0%.</p>
        {recommendation.valid_until && Number.isFinite(expiry) && <p>Hiệu lực đến {dateTime(recommendation.valid_until)} (GMT+7).</p>}
        {changed && <p>Đầu vào đã thay đổi sau khi tính.</p>}
        {recommendation.fallback_reason && <p>Đề xuất đã lưu này được tính bằng phương án dự phòng.</p>}
        {recommendation.constraints ? <ul><li>Tỷ trọng tối đa mỗi tài sản {percentage(recommendation.constraints.max_position_weight)}</li>{recommendation.constraints.min_defensive_weight != null && <li>Phòng thủ tối thiểu {percentage(recommendation.constraints.min_defensive_weight)}</li>}{recommendation.constraints.max_non_defensive_weight != null && <li>Ngoài nhóm phòng thủ tối đa {percentage(recommendation.constraints.max_non_defensive_weight)}</li>}</ul> : <p>Lần tính này chưa lưu chi tiết giới hạn.</p>}
        <AllocationView allocation={recommendation} assets={assets} summaryFirst capitalLabel="Vốn tại lần tính"/>
        {(accepted || historical) && <button type="button" data-testid="accept-proposal" disabled>{accepted ? 'Đã lưu mục tiêu' : 'Đề xuất cũ · đã khóa chấp nhận'}</button>}
        <div className="actions"><a href={chatLink}>Hỏi về kết quả</a><a href={workspaceHash({ view: 'views', portfolioId: portfolio.id })}>Nhận định của bạn</a><a href={portfolioLink(portfolio.id, 'edit')}>Điều chỉnh đầu vào</a><a href={historyLink}>So sánh đề xuất đã lưu</a></div>
        {viewerBase && <JobTrace reference={recommendation} viewerBase={viewerBase}/>}
      </details>
      <PlanDetails portfolio={portfolio} readiness={readiness} universeAssetIds={universeAssetIds}/>
    </div>
  </div></section>;
}

export function PortfolioOverview({ portfolio, dashboard, readiness, assets, universeAssetIds, api, readinessFailed, onRefresh }: PlanProps & { assets?: AssetCatalogItem[]; api?: Api; readinessFailed?: boolean; onRefresh?: () => void }) {
  const target = dashboard?.accepted_target;
  const hasProposals = dashboard ? dashboard.proposal_count > 0 : undefined;
  const [latest, setLatest] = useState<Recommendation>();
  useEffect(() => {
    if (!api || !hasProposals) return;
    let active = true;
    setLatest(undefined);
    api<Recommendation[]>(`/api/v1/portfolios/${portfolio.id}/recommendations?limit=1`).then(([item]) => {
      if (active) setLatest(item);
    }).catch(() => { if (active) setLatest(undefined); });
    return () => { active = false; };
  }, [api, hasProposals, portfolio.id, portfolio.version, dashboard?.proposal_count]);
  const pending = hasProposals && latest?.portfolio_id === portfolio.id && latest.id !== target?.recommendation_id && latest.portfolio_version === portfolio.version && Date.parse(latest.valid_until ?? '') > Date.now() ? latest : null;
  const chat = workspaceHash({ view: 'chat', portfolioId: portfolio.id, proposalId: target?.recommendation_id });
  const history = workspaceHash({ view: 'proposal', portfolioId: portfolio.id, focus: 'history' });
  const paused = readiness?.reason_code === 'SYSTEM_PAUSED';
  const allowed = readinessAllows(readiness ?? null, proposalStrategy(portfolio, readiness), false);
  let status;
  if (paused) {
    status = <PausedStatus id={portfolio.id} hasProposals={hasProposals}/>;
  } else if (pending) {
    const label = proposalLabel(pending.id);
    status = <StatusCard title={target ? 'Có đề xuất mới chờ xem' : 'Có đề xuất chờ xem'} message={target ? `${label} đang chờ xem với vốn tại lần tính ${money(pending.capital_vnd)}. Mục tiêu đã lưu vẫn áp dụng tới khi bạn chấp nhận.` : `${label} đang chờ bạn xem tỷ trọng trước khi quyết định lưu làm mục tiêu.`} tone="good">
      <a className="button" href={workspaceHash({ view: 'proposal', portfolioId: portfolio.id, proposalId: pending.id })}>Xem đề xuất {label}</a>
    </StatusCard>;
  } else if (target) {
    status = null;
  } else if (!portfolio.risk_profile) {
    status = <StatusCard title="Hoàn tất hồ sơ rủi ro" message="Chưa xác nhận hồ sơ. Trả lời vài câu hỏi để xác định giới hạn phân bổ.">
      <a className="button" href={portfolioLink(portfolio.id, 'risk-assessment')}>Tiếp tục hồ sơ rủi ro</a>
    </StatusCard>;
  } else if (hasProposals) {
    status = <StatusCard title="Có đề xuất đã lưu" message="Bạn có thể mở lịch sử để xem lại phân bổ và căn cứ của từng lần tính.">
      <a className="button" href={history}>Xem lịch sử đề xuất</a>
    </StatusCard>;
  } else if (allowed && dashboard) {
    status = <StatusCard title="Sẵn sàng tạo đề xuất" message="Xem lại rổ tài sản, ngày dữ liệu và giới hạn trước khi xác nhận tính." tone="good">
      <a className="button" href={portfolioLink(portfolio.id, 'proposal')}>Tạo đề xuất đầu tiên</a>
    </StatusCard>;
  } else {
    const checking = !readiness && !readinessFailed || !dashboard;
    status = <StatusCard title={checking ? 'Đang kiểm tra điều kiện tính' : 'Chưa thể tạo đề xuất'} tone={checking ? 'neutral' : 'warning'}
      message={checking ? 'Hệ thống đang xác minh dữ liệu. Bạn vẫn có thể hỏi về kế hoạch.' : (readiness && readinessReason[readiness.reason_code]) || 'Chưa xác nhận được điều kiện tính. Bạn có thể kiểm tra lại dữ liệu.'}>
      <a className="button" href={chat}>Hỏi về kế hoạch</a>
    </StatusCard>;
  }
  const historyAction = <a className="button quiet" href={portfolioLink(portfolio.id, 'history')}>Lịch sử mục tiêu</a>;
  const targetLink = target && workspaceHash({ view: 'proposal', portfolioId: portfolio.id, proposalId: target.recommendation_id });
  return <section className="plan-overview plan-surface">{target && api && <PaperReviewReminder key={portfolio.id} portfolioId={portfolio.id} api={api}/>}<div className={target ? 'plan-result-grid' : 'plan-empty-grid'}>
    {status && <div className="plan-decision overview-next-step">{status}
      {paused && pending && <a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId: portfolio.id, proposalId: pending.id })}>Xem đề xuất {proposalLabel(pending.id)}</a>}
      {paused && !portfolio.risk_profile && <a className="button quiet" href={portfolioLink(portfolio.id, 'risk-assessment')}>Tiếp tục hồ sơ rủi ro</a>}
    </div>}
    {target && <section className="allocation-primary" aria-label="Mục tiêu đã chấp nhận">
      <AllocationView key={target.id} allocation={target.allocation} assets={assets} pricePortfolioId={portfolio.id} priceProposalId={target.recommendation_id} priceReturnView="overview" presentation="summary" summaryVariant={status ? 'compact' : undefined} metadata={false} chartTitle="Phân bổ đã lưu" capitalLabel="Vốn tại lần lưu" capitalNote={<>Mục tiêu đã lưu ngày <DataDay day={target.accepted_at}/></>} capitalAction={<span className="plan-history-desktop">{historyAction}</span>}/>
    </section>}
    {target && <div className="plan-result-actions">
      {status && targetLink && <a className="button quiet" href={targetLink}>Xem mục tiêu đã lưu</a>}
      <a className="button quiet" href={workspaceHash({ view: 'holdings', portfolioId: portfolio.id })}>Tài sản mô phỏng</a>
      <a className="button quiet plan-chat" href={chat}>Hỏi về kế hoạch</a>
      {!status && <span className="plan-history-mobile">{historyAction}</span>}
    </div>}
    <div className="plan-result-details"><PlanDetails showFacts={!target} portfolio={portfolio} universeAssetIds={universeAssetIds} readiness={readiness} onRefresh={onRefresh}>
      {target && <>
        {!dashboard?.target_matches_portfolio && <p>Danh mục đã thay đổi sau lần chấp nhận này. Mục tiêu đã lưu vẫn giữ vốn và đầu vào tại thời điểm chấp nhận.</p>}
        <a href={workspaceHash({ view: 'proposal', portfolioId: portfolio.id, proposalId: target.recommendation_id })}>Xem mục tiêu đã lưu</a>
        <AllocationView key={target.id} allocation={target.allocation} assets={assets} summaryFirst capitalLabel="Vốn tại lần lưu"/>
      </>}
    </PlanDetails></div>
  </div></section>;
}

export function ProposalRequest({ portfolio, readiness, busy, onSubmit, initialReview = false }: {
  portfolio: Portfolio; readiness: Readiness | null; busy: boolean; onSubmit: (strategy: 'EW' | 'MVO' | 'HYBRID') => void; initialReview?: boolean;
}) {
  const [demoStrategy, setDemoStrategy] = useState<'EW' | 'MVO'>();
  const demo = portfolio.universe_id === 'DEMO' && readiness && !isSelectionReadiness(readiness) && readiness.demo;
  const strategy = demo && demoStrategy ? demoStrategy : proposalStrategy(portfolio, readiness);
  const fingerprint = JSON.stringify([portfolio.id, portfolio.version, readiness, strategy]);
  const allowed = !!portfolio.risk_profile && readinessAllows(readiness, strategy, false);
  const [reviewed, setReviewed] = useState<string | null>(initialReview ? 'initial' : null);
  if (allowed && reviewed === 'initial') setReviewed(fingerprint);
  const reviewing = allowed && reviewed === fingerprint;
  const custom = isSelectionReadiness(readiness) ? readiness : null;
  if (readiness?.reason_code === 'SYSTEM_PAUSED') return null;
  return <section className="proposal-request" aria-label="Tạo đề xuất phân bổ">
    {reviewing ? <section className="request-review"><h2>Xem lại đầu vào</h2>
      <dl className="review-list"><div><dt>Rổ tài sản được cân nhắc</dt><dd>{(custom?.candidate_asset_ids ?? (readiness && !isSelectionReadiness(readiness) ? readiness.asset_ids : [])).join(' · ') || 'Chưa xác định'}</dd></div><div><dt>Ngày dữ liệu hiện tại</dt><dd>{(readiness && !isSelectionReadiness(readiness) ? readiness.as_of_date : custom?.decision_session) ?? 'Chưa xác định'}{demo && ' · Minh họa'}</dd></div><div><dt>Tỷ trọng tối đa mỗi mã</dt><dd>{percentage(custom?.effective_constraints?.max_position_weight ?? portfolio.constraints.max_position_weight)}</dd></div></dl>
      <TaskActions hint="Bạn có thể xem tỷ trọng trước khi lưu làm mục tiêu."><button data-testid="confirm-proposal" disabled={busy || !allowed} onClick={() => { if (allowed && !busy && readinessAllows(readiness, strategy, false)) { setReviewed(null); onSubmit(strategy); } }}>Xác nhận tạo đề xuất</button><button className="quiet" disabled={busy} onClick={() => setReviewed(null)}>Quay lại</button></TaskActions>
    </section> : <>
      {demo && <fieldset><legend>Phương pháp tính với dữ liệu minh họa</legend>{(['EW', 'MVO'] as const).map(method => <label className="method-choice-title" key={method}><input type="radio" name="demo-strategy" data-testid={`strategy-${method}`} checked={strategy === method} disabled={busy || !readinessAllows(readiness, method, false)} onChange={() => setDemoStrategy(method)}/>{method === 'EW' ? 'Chia đều tỷ trọng (EW)' : 'Tối ưu theo lợi nhuận và biến động (MVO)'}</label>)}</fieldset>}
      <p>Hệ thống tính tỷ trọng từ rổ tài sản, hồ sơ rủi ro và dữ liệu thị trường.</p>
      <TaskActions><button data-testid="propose-portfolio" disabled={busy || !allowed} onClick={() => setReviewed(fingerprint)}>Xem lại yêu cầu</button><a className="button quiet" href={portfolioLink(portfolio.id, 'overview')}>Về tổng quan</a></TaskActions>
    </>}
  </section>;
}

export function RiskProfileView({ portfolio }: { portfolio: Portfolio }) {
  const answers = portfolio.risk_profile?.answers;
  const levels: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
  const hasAnswers = answers && Number.isInteger(answers.horizon_months) && answers.horizon_months > 0 && levels[answers.liquidity_need] && levels[answers.loss_tolerance] && (answers.questionnaire_version === 'risk-v2' ? !!answers.reserve_months : ['beginner', 'experienced'].includes(answers.experience));
  return <section className="investor-profile">
    <p className="muted investor-context">{portfolio.name}</p>
    <section className="investor-fact"><h2>{profileName(portfolio.risk_profile?.profile)}</h2>
      <p>{portfolio.risk_profile ? 'Hồ sơ đã xác nhận' : 'Đánh giá hồ sơ trước khi tạo đề xuất phân bổ.'}</p></section>
    {answers && Number.isInteger(answers.horizon_months) && answers.horizon_months > 0 && <section className="investor-fact"><h2>Thời gian đầu tư</h2><p>{answers.horizon_months} tháng</p></section>}
    <details className="investor-disclosure"><summary>Câu trả lời và giới hạn phân bổ</summary>
    <p className="muted">Hồ sơ được hệ thống dùng để áp dụng giới hạn phân bổ. Đây không phải dự báo lợi nhuận hoặc mức thua lỗ tối đa.</p>
    <section className="profile-allocation-rules"><h3>Giới hạn theo hồ sơ</h3><p>Tối đa {portfolio.constraints.max_position_weight * 100}% mỗi tài sản.</p>{portfolio.constraints.min_defensive_weight != null && <p>Phòng thủ tối thiểu {percentage(portfolio.constraints.min_defensive_weight)}{portfolio.constraints.defensive_asset_ids?.length ? ` · ${portfolio.constraints.defensive_asset_ids.join(' · ')}` : ''}.</p>}{portfolio.constraints.max_non_defensive_weight != null && <p>Ngoài nhóm phòng thủ tối đa {percentage(portfolio.constraints.max_non_defensive_weight)}.</p>}<p className="muted small">Giới hạn được áp dụng khi tính phân bổ; không chỉnh trực tiếp tại đây.</p></section>
    <section className="profile-answers"><h3>Câu trả lời làm cơ sở</h3>{hasAnswers ? <><RiskReason profile={portfolio.risk_profile}/><dl className="review-list"><AnswerRows answers={answers}/></dl></> : <p className="muted">Chưa có câu trả lời đã lưu để hiển thị cho hồ sơ này. Đánh giá lại khi bạn muốn xác nhận thông tin hiện tại.</p>}</section>
    </details>
    <div className="actions"><a className="button quiet" href={portfolioLink(portfolio.id, 'overview')}>Quay lại</a><a className="button quiet" href={portfolioLink(portfolio.id, 'risk-assessment')}>Đánh giá lại hồ sơ</a></div>
  </section>;
}
