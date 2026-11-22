'use client';
import { TaskActions } from './task-actions';
import { isSelectionReadiness } from '../lib/selection-types';
import { useState } from 'react';
import { AllocationMetadata, AllocationView, money, percentage, profileName, strategyName } from './allocation-view';
import { JobTrace } from './job-trace';
import { dateTime, type Dashboard, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { readinessAllows, workspaceHash, type Readiness } from '../lib/workspace-state';

const portfolioLink = (id: string, view: 'overview' | 'proposal' | 'history' | 'profile' | 'edit' | 'chat' | 'risk-assessment') => workspaceHash({ view, portfolioId: id });

export function ProposalReview({ portfolio, recommendation, accepted, stale, conflict, busy, onAccept, viewerBase }: {
  portfolio: Portfolio; recommendation: Recommendation; accepted: boolean; stale: boolean; conflict: boolean; busy: boolean; onAccept: () => void; viewerBase: string | null;
}) {
  return <section className="proposal-review results">
    <aside className={`notice review-status ${stale && !accepted ? 'warning' : ''}`}><strong>{accepted ? 'Đã chấp nhận làm mục tiêu' : stale ? 'Cần tính lại' : 'Chờ bạn xem xét'}</strong><p>{strategyName(recommendation.strategy)} · Ngày dữ liệu: {recommendation.as_of_date ?? 'Chưa xác định'}</p></aside>
    {recommendation.valid_until && <p className="muted small">Hiệu lực đến {dateTime(recommendation.valid_until)} · GMT+7</p>}
    {stale && !accepted && <aside className="notice warning" data-testid="stale-proposal-notice"><strong>{recommendation.portfolio_version !== portfolio.version ? 'Đầu vào đã thay đổi sau khi tính' : 'Đề xuất đã hết hiệu lực'}</strong><p>Kết quả thuộc phiên bản hoặc thời hạn cũ. Hãy tạo đề xuất mới từ dữ liệu hiện hành.</p></aside>}
    <TaskActions label="Quyết định đề xuất" hint="Chấp nhận chỉ lưu tỷ trọng mục tiêu, không đặt lệnh giao dịch.">        <button data-testid="accept-proposal" disabled={busy || accepted || stale || conflict} onClick={onAccept}>{accepted ? 'Đã lưu mục tiêu' : busy ? 'Đang lưu…' : stale ? 'Đề xuất cũ — hãy tạo lại' : 'Chấp nhận làm mục tiêu'}</button>
        {accepted && <a className="button" href={portfolioLink(portfolio.id, 'overview')}>Về tổng quan</a>}
</TaskActions>
    <div className="allocation-decision-layout">
      <div className="allocation-primary"><h2 className="sr-only">Phân bổ đề xuất</h2><AllocationView allocation={recommendation} metadata={false}/></div>
      <aside className="decision-rail" aria-label="Quyết định của bạn"><h2>Quyết định của bạn</h2><p>{accepted ? 'Tỷ trọng mục tiêu đã được lưu cho danh mục.' : 'Chấp nhận sẽ lưu tỷ trọng này làm mục tiêu của danh mục.'}</p><p className="muted">Không đặt lệnh mua bán và không thay đổi tài sản đang nắm giữ.</p>
        <button className="quiet" onClick={() => { const history = document.getElementById('proposal-history'); history?.closest('details')?.setAttribute('open', ''); requestAnimationFrame(() => { history?.scrollIntoView({ block: 'start' }); history?.focus(); }); }}>So sánh đề xuất đã lưu</button>
        <a className="button quiet" href={portfolioLink(portfolio.id, 'proposal')}>{stale ? 'Tạo đề xuất mới' : 'Tính lại đề xuất'}</a>
        <p className="muted small">Hồ sơ khi tính: {profileName(recommendation.risk_profile?.profile)}<br/>Tài sản được phân bổ: {recommendation.asset_ids.filter((_, index) => Number(recommendation.weights[index]) !== 0).join(' · ') || 'Chưa có'}</p>
      </aside>
    </div>
    <section className="allocation-basis"><h2>Cơ sở & giới hạn phân bổ</h2><p className="muted">Đề xuất được tính theo hồ sơ đã xác nhận và policy tại thời điểm gửi yêu cầu. Kết quả không bảo đảm lợi nhuận hoặc mức thua lỗ tối đa.</p><p>Giới hạn khi tính: tối đa {(recommendation.constraints?.max_position_weight ?? portfolio.constraints.max_position_weight) * 100}% mỗi tài sản. Đề xuất lưu theo phiên bản danh mục {recommendation.portfolio_version}.</p></section>
    <AllocationMetadata allocation={recommendation}/>
    <details className="diagnostics"><summary>Chẩn đoán kỹ thuật</summary><JobTrace reference={recommendation} viewerBase={viewerBase}/><pre>{JSON.stringify(recommendation, null, 2)}</pre></details>
  </section>;
}

export function PortfolioOverview({ portfolio, dashboard }: { portfolio: Portfolio; dashboard: Dashboard | null }) {
  const target = dashboard?.accepted_target;
  const hasProposals = (dashboard?.proposal_count ?? 0) > 0;
  const existingProposals = workspaceHash({ view: 'proposal', portfolioId: portfolio.id, focus: 'history' });
  const targetLink = target ? workspaceHash({ view: 'proposal', portfolioId: portfolio.id, proposalId: target.recommendation_id }) : '';
  return <section className="plan-overview">
    <header className="overview-summary"><h2 className="plan-name">{portfolio.name}</h2>
      <dl><div><dt>Vốn kế hoạch hiện tại</dt><dd>{money(portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ rủi ro</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div>{portfolio.risk_profile?.answers && <div><dt>Thời gian đầu tư</dt><dd>{portfolio.risk_profile.answers.horizon_months} tháng</dd></div>}</dl>
      <p className="overview-status">{target ? 'Đã chấp nhận mục tiêu' : 'Chưa có mục tiêu được chấp nhận'}{target && <> · Dữ liệu {target.allocation.as_of_date ?? 'chưa xác định'}</>}</p>
    </header>
    <details className="overview-candidates"><summary>{portfolio.asset_selection ? `${portfolio.asset_selection.candidate_asset_ids.length} tài sản được cân nhắc · Xem danh sách` : 'Bộ tài sản hiện tại · Xem chi tiết'}</summary><p>{portfolio.asset_selection ? <>Tài sản được phép cân nhắc hiện tại: {portfolio.asset_selection.candidate_asset_ids.join(' · ')}.</> : portfolio.universe_id}</p><p className="muted small">Đây là tập ứng viên, không phải tỷ trọng mục tiêu. Tập thực tế dùng trong phép tính nằm trong chi tiết của từng kết quả; tài sản được chọn vẫn có thể nhận 0%.</p></details>
    {target && !dashboard?.target_matches_portfolio && <aside className="notice warning overview-changed" role="status"><strong>Danh mục đã thay đổi sau lần chấp nhận này.</strong><p>Mục tiêu đã lưu vẫn giữ nguyên theo vốn và đầu vào tại thời điểm chấp nhận.</p></aside>}
    {target ? <div className="overview-target-layout"><div className="overview-next-step"><h2>Bước tiếp theo</h2><p className="muted">Xem lại kết quả đã chấp nhận và đầu vào được ghim của mục tiêu này.</p><a className="button" href={targetLink}>Xem mục tiêu đã lưu</a></div><section className="allocation-primary" aria-label="Mục tiêu đã chấp nhận"><h2>Phân bổ mục tiêu</h2><p className="muted small">{strategyName(target.allocation.strategy)} · <time dateTime={target.accepted_at} title={dateTime(target.accepted_at)}>Chấp nhận {new Date(target.accepted_at).toLocaleDateString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })}</time></p><AllocationView allocation={target.allocation} summaryFirst capitalLabel="Vốn đã ghim khi chấp nhận"/></section><aside className="next-steps overview-other-actions"><h2>Các hành động khác</h2><a className="button quiet" href={portfolioLink(portfolio.id, 'proposal')}>Tạo đề xuất mới</a><a className="button quiet" href={portfolioLink(portfolio.id, 'chat')}>Trao đổi về danh mục</a><a className="button quiet" href={portfolioLink(portfolio.id, 'history')}>Lịch sử mục tiêu</a></aside></div>
      : <section className="plan-empty"><h2>Chưa có mục tiêu được chấp nhận</h2><p>{portfolio.risk_profile ? hasProposals ? 'Bạn đã có đề xuất để xem lại. Mở kết quả và quyết định có lưu làm mục tiêu hay không.' : 'Hồ sơ đã được xác nhận. Bước tiếp theo là tạo đề xuất, xem phân bổ và chủ động chấp nhận nếu phù hợp.' : 'Chưa xác nhận hồ sơ rủi ro. Hãy xem lại mục tiêu và câu trả lời trước khi tạo phương án phân bổ.'}</p><div className="actions"><a className="button" href={portfolio.risk_profile && hasProposals ? existingProposals : portfolioLink(portfolio.id, portfolio.risk_profile ? 'proposal' : 'risk-assessment')}>{portfolio.risk_profile ? hasProposals ? 'Xem các đề xuất' : 'Tạo đề xuất đầu tiên' : 'Xác nhận hồ sơ rủi ro'}</a>{portfolio.risk_profile && hasProposals && <a className="button quiet" href={portfolioLink(portfolio.id, 'proposal')}>Tạo đề xuất mới</a>}<a className="button quiet" href={portfolioLink(portfolio.id, 'chat')}>Trao đổi qua hội thoại</a></div></section>}
    <aside className="notice holdings-note"><strong>Tài sản thực tế: chưa theo dõi</strong><p>Vốn kế hoạch và tỷ trọng mục tiêu không phải số dư hoặc hiệu suất đầu tư. Chấp nhận không tạo lệnh giao dịch.</p></aside>
  </section>;
}

export function ProposalRequest({ portfolio, readiness, busy, onSubmit }: {
  portfolio: Portfolio; readiness: Readiness | null; busy: boolean; onSubmit: () => void;
}) {
  const [reviewed, setReviewed] = useState<string | null>(null);
  const fingerprint = JSON.stringify([portfolio.id, portfolio.version, readiness]);
  const reviewing = reviewed === fingerprint;
  const allowed = readinessAllows(readiness, 'HYBRID', false);
  const custom = isSelectionReadiness(readiness) ? readiness : null;
  return <section className="proposal-request" aria-label="Tạo đề xuất phân bổ">
    <dl className="plan-context"><div><dt>Danh mục</dt><dd>{portfolio.name}</dd></div><div><dt>Vốn kế hoạch</dt><dd>{money(portfolio.capital_vnd)}</dd></div><div><dt>Hồ sơ</dt><dd>{profileName(portfolio.risk_profile?.profile)}</dd></div></dl>
    {reviewing ? <section className="request-review"><h2>Xem lại yêu cầu</h2>
      <dl className="review-list"><div><dt>Tài sản được cân nhắc</dt><dd>{custom?.candidate_asset_ids.join(' · ')}</dd></div><div><dt>Ngày dữ liệu</dt><dd>{custom?.decision_session ?? 'Chưa xác định'}</dd></div><div><dt>Tỷ trọng tối đa mỗi mã</dt><dd>{percentage(custom?.effective_constraints?.max_position_weight ?? portfolio.constraints.max_position_weight)}</dd></div></dl>
      <TaskActions hint="Bạn có thể xem tỷ trọng trước khi lưu làm mục tiêu."><button data-testid="confirm-proposal" disabled={busy || !allowed} onClick={() => { if (allowed && !busy) { setReviewed(null); onSubmit(); } }}>Xác nhận tạo đề xuất</button><button className="quiet" disabled={busy} onClick={() => setReviewed(null)}>Quay lại</button></TaskActions>
    </section> : <>
      <p>Hệ thống tính tỷ trọng từ rổ tài sản, hồ sơ rủi ro và dữ liệu thị trường.</p>
      <TaskActions><button data-testid="propose-portfolio" disabled={busy || !allowed} onClick={() => setReviewed(fingerprint)}>Xem lại yêu cầu</button><a className="button quiet" href={portfolioLink(portfolio.id, 'overview')}>Về tổng quan</a></TaskActions>
    </>}
  </section>;
}

export function RiskProfileView({ portfolio }: { portfolio: Portfolio }) {
  const answers = portfolio.risk_profile?.answers;
  const levels: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
  const hasAnswers = answers && Number.isInteger(answers.horizon_months) && answers.horizon_months > 0 && levels[answers.liquidity_need] && levels[answers.loss_tolerance] && ['beginner', 'experienced'].includes(answers.experience);
  return <section className="panel risk-profile-view"><div className="section-heading"><h2>{profileName(portfolio.risk_profile?.profile)}</h2><a className="button quiet" href={portfolioLink(portfolio.id, 'risk-assessment')}>Đánh giá lại hồ sơ</a></div>
    <p className="muted">{portfolio.risk_profile ? 'Hồ sơ được hệ thống dùng để áp dụng giới hạn phân bổ. Đây không phải dự báo lợi nhuận hoặc mức thua lỗ tối đa.' : 'Chưa xác nhận hồ sơ rủi ro. Đánh giá hồ sơ trước khi tạo đề xuất phân bổ.'}</p>
    <section className="profile-allocation-rules"><h3>Giới hạn theo hồ sơ</h3><p>Tối đa {portfolio.constraints.max_position_weight * 100}% mỗi tài sản.</p>{portfolio.universe_id === 'VN_PHASE1_FULL' && <p>VFF phòng thủ tối thiểu {percentage(portfolio.constraints.min_defensive_weight ?? .15)}; nhóm còn lại gồm GOLD tối đa {percentage(portfolio.constraints.max_non_defensive_weight ?? .7)}. Regime có thể tăng mức ngại rủi ro khi tạo đề xuất.</p>}<p className="muted small">Giới hạn được áp dụng khi tính phân bổ; không chỉnh trực tiếp tại đây.</p></section>
    <section className="profile-answers"><h3>Câu trả lời làm cơ sở</h3>{hasAnswers ? <dl className="review-list"><div><dt>Thời gian đầu tư</dt><dd>{answers.horizon_months} tháng</dd></div><div><dt>Nhu cầu rút vốn sớm</dt><dd>{levels[answers.liquidity_need]}</dd></div><div><dt>Khả năng chịu biến động</dt><dd>{levels[answers.loss_tolerance]}</dd></div><div><dt>Kinh nghiệm</dt><dd>{answers.experience === 'experienced' ? 'Đã có kinh nghiệm' : 'Mới bắt đầu'}</dd></div></dl> : <p className="muted">Chưa có câu trả lời đã lưu để hiển thị cho hồ sơ này. Đánh giá lại khi bạn muốn xác nhận thông tin hiện tại.</p>}</section>
    <details className="allocation-details"><summary>Thông số và phiên bản hồ sơ</summary><dl className="review-list"><div><dt>Mã quy tắc phân bổ (policy)</dt><dd>{portfolio.policy_version_id}</dd></div><div><dt>Tham số ngại rủi ro</dt><dd>{portfolio.constraints.risk_aversion}</dd></div><div><dt>Phiên bản hồ sơ</dt><dd>{portfolio.risk_profile?.version_id ?? 'Chưa ghi nhận'}</dd></div></dl></details>
  </section>;
}
