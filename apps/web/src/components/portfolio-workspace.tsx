'use client';
import { TaskActions } from './task-actions';
import { useState } from 'react';
import { AllocationMetadata, AllocationView, money, profileName, strategyName } from './allocation-view';
import { JobTrace } from './job-trace';
import { dateTime, type Dashboard, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { readinessAllows, workspaceHash, type Readiness } from '../lib/workspace-state';

const portfolioLink = (id: string, view: 'overview' | 'proposal' | 'history' | 'profile' | 'edit' | 'chat' | 'risk-assessment') => workspaceHash({ view, portfolioId: id });

export function ProposalReview({ portfolio, recommendation, accepted, stale, conflict, busy, onAccept, viewerBase }: {
  portfolio: Portfolio; recommendation: Recommendation; accepted: boolean; stale: boolean; conflict: boolean; busy: boolean; onAccept: () => void; viewerBase: string | null;
}) {
  return <section className="proposal-review results">
    <aside className={`notice review-status ${stale && !accepted ? 'warning' : ''}`}><strong>{accepted ? 'Đã chấp nhận làm mục tiêu' : stale ? 'Cần tính lại' : 'Chờ bạn xem xét'}</strong><p>Chiến lược thực tế: {strategyName(recommendation.strategy)} · Ngày dữ liệu: {recommendation.as_of_date ?? 'Chưa xác định'}</p></aside>
    {recommendation.valid_until && <p className="muted small">Hiệu lực đến {dateTime(recommendation.valid_until)} · GMT+7</p>}
    {stale && !accepted && <aside className="notice warning" data-testid="stale-proposal-notice"><strong>{recommendation.portfolio_version !== portfolio.version ? 'Đầu vào đã thay đổi sau khi tính' : 'Đề xuất đã hết hiệu lực'}</strong><p>Kết quả thuộc phiên bản hoặc thời hạn cũ. Hãy tạo đề xuất mới từ dữ liệu hiện hành.</p></aside>}
    <TaskActions label="Quyết định đề xuất" hint="Chấp nhận chỉ lưu tỷ trọng mục tiêu, không đặt lệnh giao dịch.">        <button data-testid="accept-proposal" disabled={busy || accepted || stale || conflict} onClick={onAccept}>{accepted ? 'Đã lưu mục tiêu' : busy ? 'Đang lưu…' : stale ? 'Đề xuất cũ — hãy tạo lại' : 'Chấp nhận làm mục tiêu'}</button>
        {accepted && <a className="button" href={portfolioLink(portfolio.id, 'overview')}>Về tổng quan</a>}
</TaskActions>
    <div className="allocation-decision-layout">
      <div className="allocation-primary"><h2 className="sr-only">Phân bổ đề xuất</h2><AllocationView allocation={recommendation} metadata={false}/></div>
      <aside className="decision-rail" aria-label="Quyết định của bạn"><h2>Quyết định của bạn</h2><p>{accepted ? 'Tỷ trọng mục tiêu đã được lưu cho danh mục.' : 'Chấp nhận sẽ lưu tỷ trọng này làm mục tiêu của danh mục.'}</p><p className="muted">Không đặt lệnh mua bán và không thay đổi tài sản đang nắm giữ.</p>
        <button className="quiet" onClick={() => { const history = document.getElementById('proposal-history'); history?.closest('details')?.setAttribute('open', ''); requestAnimationFrame(() => { history?.scrollIntoView({ block: 'start' }); history?.focus(); }); }}>So sánh hai phương án</button>
        <a className="button quiet" href={portfolioLink(portfolio.id, 'proposal')}>{stale ? 'Tạo đề xuất mới' : 'Tính lại đề xuất'}</a>
        <p className="muted small">Hồ sơ hiện tại: {profileName(portfolio.risk_profile?.profile)}<br/>Bộ tài sản: {recommendation.asset_ids.join(' · ')}</p>
      </aside>
    </div>
    <section className="allocation-basis"><h2>Cơ sở & giới hạn phân bổ</h2><p className="muted">Đề xuất được tính theo hồ sơ đã xác nhận và policy tại thời điểm gửi yêu cầu. Kết quả không bảo đảm lợi nhuận hoặc mức thua lỗ tối đa.</p><p>Giới hạn hiện tại: tối đa {portfolio.constraints.max_position_weight * 100}% mỗi tài sản. Đề xuất lưu theo phiên bản danh mục {recommendation.portfolio_version}.</p></section>
    <AllocationMetadata allocation={recommendation}/>
    <details className="diagnostics"><summary>Chẩn đoán kỹ thuật</summary><JobTrace reference={recommendation} viewerBase={viewerBase}/><pre>{JSON.stringify(recommendation, null, 2)}</pre></details>
  </section>;
}

export function PortfolioOverview({ portfolio, dashboard }: { portfolio: Portfolio; dashboard: Dashboard | null }) {
  const target = dashboard?.accepted_target;
  const hasProposals = (dashboard?.proposal_count ?? 0) > 0;
  const existingProposals = workspaceHash({ view: 'proposal', portfolioId: portfolio.id, focus: 'history' });
  return <section className="plan-overview">
    <h2 className="plan-name">{portfolio.name}</h2>
    <dl className="plan-context"><div><dt>Vốn kế hoạch hiện tại</dt><dd>{money(portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ rủi ro</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div><div><dt>Bộ tài sản</dt><dd>{portfolio.universe_id}</dd></div><div><dt>Ngày dữ liệu mục tiêu</dt><dd>{target?.allocation.as_of_date ?? 'Chưa có mục tiêu'}</dd></div></dl>
    {target ? <div className="allocation-decision-layout"><section className="allocation-primary"><h2>Mục tiêu đã chấp nhận</h2><p className="muted small">{strategyName(target.allocation.strategy)} · Lưu {dateTime(target.accepted_at)}</p>{!dashboard?.target_matches_portfolio && <aside className="notice warning">Danh mục đã thay đổi sau lần chấp nhận này. Mục tiêu đã lưu vẫn giữ nguyên theo vốn và đầu vào tại thời điểm chấp nhận.</aside>}<AllocationView allocation={target.allocation}/></section><aside className="next-steps"><h2>Bước tiếp theo</h2><p className="muted">Xem lại kế hoạch khi mục tiêu tài chính hoặc khả năng chịu rủi ro thay đổi.</p><a className="button" href={workspaceHash({ view: 'proposal', portfolioId: portfolio.id, proposalId: target.recommendation_id })}>Xem mục tiêu đã lưu</a><a className="button quiet" href={portfolioLink(portfolio.id, 'proposal')}>Tạo đề xuất mới</a><a className="button quiet" href={portfolioLink(portfolio.id, 'chat')}>Trao đổi về danh mục</a><a className="button quiet" href={portfolioLink(portfolio.id, 'history')}>Lịch sử mục tiêu</a></aside></div>
      : <section className="plan-empty"><h2>Chưa có mục tiêu được chấp nhận</h2><p>{portfolio.risk_profile ? hasProposals ? 'Bạn đã có đề xuất để xem lại. Mở kết quả và quyết định có lưu làm mục tiêu hay không.' : 'Hồ sơ đã được xác nhận. Bước tiếp theo là tạo đề xuất, xem phân bổ và chủ động chấp nhận nếu phù hợp.' : 'Chưa xác nhận hồ sơ rủi ro. Hãy xem lại mục tiêu và câu trả lời trước khi tạo phương án phân bổ.'}</p><div className="actions"><a className="button" href={portfolio.risk_profile && hasProposals ? existingProposals : portfolioLink(portfolio.id, portfolio.risk_profile ? 'proposal' : 'risk-assessment')}>{portfolio.risk_profile ? hasProposals ? 'Xem các đề xuất' : 'Tạo đề xuất đầu tiên' : 'Xác nhận hồ sơ rủi ro'}</a>{portfolio.risk_profile && hasProposals && <a className="button quiet" href={portfolioLink(portfolio.id, 'proposal')}>Tạo đề xuất mới</a>}<a className="button quiet" href={portfolioLink(portfolio.id, 'chat')}>Trao đổi qua hội thoại</a></div></section>}
    <aside className="notice holdings-note"><strong>Tài sản thực tế: chưa theo dõi</strong><p>Vốn kế hoạch và tỷ trọng mục tiêu không phải số dư hoặc hiệu suất đầu tư. Chấp nhận không tạo lệnh giao dịch.</p></aside>
  </section>;
}

const methods = [
  { id: 'EW', name: 'Phân bổ đều có ràng buộc', description: 'Điểm xuất phát đơn giản trong giới hạn của hệ thống.', detail: 'Chia tỷ trọng đều giữa các tài sản rồi áp dụng ràng buộc. Các giới hạn có thể khiến tỷ trọng không hoàn toàn bằng nhau.' },
  { id: 'MVO', name: 'Tối ưu lợi nhuận / rủi ro', description: 'Tính tỷ trọng từ dữ liệu đầu vào và hồ sơ đã xác nhận.', detail: 'Tìm tỷ trọng theo dữ liệu ước lượng và mức ngại rủi ro của hồ sơ. Kết quả phụ thuộc đầu vào, không dự đoán lợi nhuận thực tế.' },
  { id: 'BL_ML', name: 'Black–Litterman kết hợp ML', description: 'Kết hợp mô hình đã được duyệt, tương thích và sẵn sàng.', detail: 'Sử dụng mô hình học máy trong phương pháp Black–Litterman. Chỉ chuyển sang EW khi thiếu mô hình phù hợp và bạn chủ động cho phép; dữ liệu hết hạn hoặc mô hình không hợp lệ vẫn bị chặn.' },
];
export function ProposalRequest({ portfolio, readiness, strategy, fallback, busy, onStrategy, onFallback, onSubmit }: {
  portfolio: Portfolio; readiness: Readiness | null; strategy: string; fallback: boolean; busy: boolean;
  onStrategy: (value: string) => void; onFallback: (value: boolean) => void; onSubmit: () => void;
}) {
  const [reviewed, setReviewed] = useState<string | null>(null);
  // A read refresh or input change invalidates the local confirmation. API-side checks remain authoritative.
  const fingerprint = JSON.stringify([portfolio, strategy, fallback, readiness]);
  const reviewing = reviewed === fingerprint;
  const allowed = readinessAllows(readiness, strategy, fallback);
  return <section className="proposal-request" aria-label="Tạo đề xuất phân bổ">
    <dl className="plan-context"><div><dt>Danh mục</dt><dd>{portfolio.name}</dd></div><div><dt>Vốn kế hoạch (VND)</dt><dd>{money(portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div></dl>
    {reviewing ? <section className="request-review"><h2>Xem lại yêu cầu</h2><dl className="review-list"><div><dt>Chiến lược đã chọn</dt><dd>{strategyName(strategy)}</dd></div><div><dt>Bộ tài sản</dt><dd>{readiness?.asset_ids.join(' · ') || portfolio.universe_id}</dd></div><div><dt>EW dự phòng</dt><dd>{strategy === 'BL_ML' && fallback ? 'Đã chủ động cho phép' : 'Chưa cho phép'}</dd></div><div><dt>Giới hạn phân bổ</dt><dd>Tối đa {portfolio.constraints.max_position_weight * 100}% mỗi tài sản</dd></div></dl><aside className="notice"><strong>Xác nhận tạo đề xuất</strong><p>Thao tác này gửi yêu cầu tính toán. Chấp nhận làm mục tiêu là quyết định riêng sau khi bạn xem kết quả.</p></aside><TaskActions hint="Gửi yêu cầu tính toán; bạn sẽ chấp nhận mục tiêu ở bước riêng."><button data-testid="confirm-proposal" disabled={busy || !allowed} onClick={() => { if (allowed && !busy) { setReviewed(null); onSubmit(); } }}>Xác nhận tạo đề xuất</button><button className="quiet" disabled={busy} onClick={() => setReviewed(null)}>Sửa lựa chọn</button></TaskActions></section>
      : <><fieldset className="method-options" disabled={busy}><legend>1. Chọn cách phân bổ</legend><div className="method-grid">{methods.map(method => {
        const available = readiness?.strategies.find(item => item.strategy === method.id)?.available;
        return <div className={`method-choice ${strategy === method.id ? 'selected' : ''}`} key={method.id}><label className="method-choice-selection"><span className="method-choice-title"><input data-testid={`strategy-${method.id}`} type="radio" name="strategy" value={method.id} checked={strategy === method.id} onChange={() => onStrategy(method.id)}/><strong>{method.name}</strong><span className="badge">{strategyName(method.id)}</span></span><span className="muted">{method.description}</span><small>{strategy === method.id ? 'Đang chọn · ' : ''}{available ? 'Sẵn sàng' : method.id === 'BL_ML' ? 'Cần mô hình phù hợp / lựa chọn dự phòng' : 'Cần dữ liệu sẵn sàng'}</small></label><details className="method-help"><summary>Cách hoạt động và giới hạn</summary><p>{method.detail}</p></details></div>;
      })}</div></fieldset>
      {strategy === 'BL_ML' && <section className="fallback-section"><h2>2. Lựa chọn của bạn</h2><label className="check fallback-choice"><input type="checkbox" checked={fallback} onChange={event => onFallback(event.target.checked)} disabled={busy}/><span>Cho phép phương án EW nếu model chưa sẵn sàng<small>Chỉ dùng EW khi thiếu model phù hợp; dữ liệu hết hạn hoặc model không hợp lệ vẫn bị chặn.</small></span></label></section>}
      <section className="policy-limits"><h2>Quy tắc phân bổ của hệ thống</h2><p className="muted">Tối đa {portfolio.constraints.max_position_weight * 100}% mỗi tài sản. Giới hạn được xác định từ hồ sơ và không chỉnh trực tiếp tại bước này.</p></section>
      {!allowed && <p className="inline-warning" role="status">Dữ liệu hoặc phương pháp chưa sẵn sàng. Kiểm tra điều kiện phía trên; chỉ chủ động cho phép EW dự phòng khi thiếu model phù hợp.</p>}
      <TaskActions hint="Chọn phương pháp, sau đó xem lại trước khi gửi."><button data-testid="propose-portfolio" disabled={busy || !allowed} onClick={() => setReviewed(fingerprint)}>Xem lại yêu cầu</button><a className="button quiet" href={portfolioLink(portfolio.id, 'overview')}>Về tổng quan</a></TaskActions></>}
  </section>;
}


export function RiskProfileView({ portfolio }: { portfolio: Portfolio }) {
  const answers = portfolio.risk_profile?.answers;
  const levels: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
  const hasAnswers = answers && Number.isInteger(answers.horizon_months) && answers.horizon_months > 0 && levels[answers.liquidity_need] && levels[answers.loss_tolerance] && ['beginner', 'experienced'].includes(answers.experience);
  return <section className="panel risk-profile-view"><div className="section-heading"><h2>{profileName(portfolio.risk_profile?.profile)}</h2><a className="button quiet" href={portfolioLink(portfolio.id, 'risk-assessment')}>Đánh giá lại hồ sơ</a></div>
    <p className="muted">{portfolio.risk_profile ? 'Hồ sơ được hệ thống dùng để áp dụng giới hạn phân bổ. Đây không phải dự báo lợi nhuận hoặc mức thua lỗ tối đa.' : 'Chưa xác nhận hồ sơ rủi ro. Đánh giá hồ sơ trước khi tạo đề xuất phân bổ.'}</p>
    <section className="profile-allocation-rules"><h3>Giới hạn theo hồ sơ</h3><p>Tối đa {portfolio.constraints.max_position_weight * 100}% mỗi tài sản.</p><p className="muted small">Giới hạn được áp dụng khi tính phân bổ; không chỉnh trực tiếp tại đây.</p></section>
    <section className="profile-answers"><h3>Câu trả lời làm cơ sở</h3>{hasAnswers ? <dl className="review-list"><div><dt>Thời gian đầu tư</dt><dd>{answers.horizon_months} tháng</dd></div><div><dt>Nhu cầu rút vốn sớm</dt><dd>{levels[answers.liquidity_need]}</dd></div><div><dt>Khả năng chịu biến động</dt><dd>{levels[answers.loss_tolerance]}</dd></div><div><dt>Kinh nghiệm</dt><dd>{answers.experience === 'experienced' ? 'Đã có kinh nghiệm' : 'Mới bắt đầu'}</dd></div></dl> : <p className="muted">Chưa có câu trả lời đã lưu để hiển thị cho hồ sơ này. Đánh giá lại khi bạn muốn xác nhận thông tin hiện tại.</p>}</section>
    <details className="allocation-details"><summary>Thông số và phiên bản hồ sơ</summary><dl className="review-list"><div><dt>Mã quy tắc phân bổ (policy)</dt><dd>{portfolio.policy_version_id}</dd></div><div><dt>Tham số ngại rủi ro</dt><dd>{portfolio.constraints.risk_aversion}</dd></div><div><dt>Phiên bản hồ sơ</dt><dd>{portfolio.risk_profile?.version_id ?? 'Chưa ghi nhận'}</dd></div></dl></details>
  </section>;
}
