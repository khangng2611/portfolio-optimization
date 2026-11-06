'use client';
import type { ReactNode } from 'react';
import { ActionIcon } from './action-controls';
import { workspaceHash, type WorkspaceView } from '../lib/workspace-state';

export type { WorkspaceView } from '../lib/workspace-state';
export function DesignIcon({ name }: { name: 'overview' | 'portfolio' | 'chat' | 'views' | 'settings' | 'empty-portfolio' | 'model' | 'model-inactive' }) {
  const size = name === 'empty-portfolio' ? 28 : 20;
  return <img className="nav-icon" src={`/figma/${name}.svg`} width={size} height={size} alt="" aria-hidden="true"/>;
}

export function WorkspaceShell({ children, view, portfolioId, account, busy, onLogout, context, operator = false, reviewer = false }: {
  children: ReactNode; view: WorkspaceView; account: string | null; busy: boolean;
  onLogout: () => void; context: string; portfolioId?: string; operator?: boolean; reviewer?: boolean;
}) {
  const link = (view: WorkspaceView) => workspaceHash({ view, ...(['portfolios', 'create'].includes(view) ? {} : { portfolioId }) });
  const portfolioTask = ['portfolios', 'create', 'proposal', 'compare', 'history', 'edit'].includes(view);
  const taskWorkspace = view === 'create' || !!portfolioId && ['overview', 'proposal', 'profile', 'edit', 'compare', 'risk-assessment', 'history'].includes(view);
  const market = view.startsWith('market');
  const model = ['models', 'model-training', 'model-review'].includes(view);
  const contextHref = !account ? '#overview' : view === 'chat' ? link('chat') : market ? '#market' : model ? '#models' : portfolioId ? link('overview') : ['profile', 'risk-assessment'].includes(view) ? '#profile' : '#portfolios';
  const dataLink = operator && <a href="#market" className={`nav-link ${market ? 'active' : ''}`} aria-current={market ? 'page' : undefined}><svg className="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/></svg>Dữ liệu</a>;
  const links = <>
    {dataLink}
    {(operator || reviewer) && <a href="#models" className={`nav-link ${model ? 'active' : ''}`} aria-current={model ? 'page' : undefined}><DesignIcon name={model ? "model" : "model-inactive"}/>Mô hình</a>}
    <a href={link('overview')} className={`nav-link ${view === 'overview' ? 'active' : ''}`} aria-current={view === 'overview' ? 'page' : undefined}><DesignIcon name="overview"/>Tổng quan</a>
    <a href="#portfolios" className={`nav-link ${portfolioTask ? 'active' : ''}`} aria-current={portfolioTask ? 'page' : undefined}><DesignIcon name="portfolio"/>Danh mục</a>
    <a href={link('chat')} className={`nav-link ${view === 'chat' ? 'active' : ''}`} aria-current={view === 'chat' ? 'page' : undefined}><DesignIcon name="chat"/>Hội thoại</a>
    <span className="nav-link unavailable" aria-disabled="true" title="Nhận định chưa được triển khai"><DesignIcon name="views"/>Nhận định <small>Sắp có</small></span>
    <a href={link('profile')} className={`nav-link ${['profile', 'risk-assessment'].includes(view) ? 'active' : ''}`} aria-current={['profile', 'risk-assessment'].includes(view) ? 'page' : undefined}><DesignIcon name="settings"/>Hồ sơ rủi ro</a>
  </>;
  return <>
    <a className="skip-link" href="#main-content">Đến nội dung chính</a>
    <div className="environment-banner"><span>KHÔNG GIAN THỬ NGHIỆM · KHÔNG THỰC HIỆN GIAO DỊCH</span><span>Thị trường Việt Nam · VND</span></div>
    <div className="app-shell">
      <aside className="sidebar"><a className="brand" href="#overview" aria-label="portfolio. · Tổng quan">portfolio.</a><p className="eyebrow">{market || model ? 'KHÔNG GIAN LÀM VIỆC' : 'KHÔNG GIAN CỦA BẠN'}</p><nav aria-label="Điều hướng chính">{links}</nav><div className="sidebar-note"><p>Quyền được cấp theo vai trò.<br/>Dữ liệu riêng thuộc chủ sở hữu.</p><a href="#methodology">Dữ liệu & phương pháp</a></div></aside>
      <main id="main-content" className={`workspace workspace-${view}${taskWorkspace ? ' workspace-task' : ''}`} data-view={view} tabIndex={-1}>
        <div className="contextbar"><a className="breadcrumb" href={contextHref}>{account ? context : 'Truy cập'}</a></div>
        {account && <div className="context-actions account-actions"><span className="account-name" title={account}>{account}</span><button className="quiet account-logout" aria-label="Đăng xuất" title="Đăng xuất" onClick={onLogout} disabled={busy}><ActionIcon name="logout"/><span>Đăng xuất</span></button></div>}
        <details className="mobile-menu" onKeyDown={event => { if (event.key === 'Escape') { event.currentTarget.removeAttribute('open'); event.currentTarget.querySelector('summary')?.focus(); } }}><summary aria-label="Điều hướng"><svg className="mobile-menu-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg><span className="mobile-menu-label">Điều hướng</span></summary><nav aria-label="Điều hướng thu gọn" onClick={event => { if ((event.target as HTMLElement).closest('a')) event.currentTarget.parentElement?.removeAttribute('open'); }}>{links}</nav>{account && <div className="mobile-account-actions"><span>{account}</span></div>}</details>
        {children}
        <footer className="page-footer"><span>Portfolio Optimization · Không thực hiện giao dịch</span><span>VND · Thời gian GMT+7</span></footer>
      </main>
    </div>
    <nav className="bottom-nav" aria-label="Điều hướng di động">
      <a href={link('overview')} aria-current={view === 'overview' ? 'page' : undefined}><DesignIcon name="overview"/><span>Tổng quan</span></a>
      <a href="#portfolios" aria-current={portfolioTask ? 'page' : undefined}><DesignIcon name="portfolio"/><span>Danh mục</span></a>
      <a href={link('chat')} aria-current={view === 'chat' ? 'page' : undefined}><DesignIcon name="chat"/><span>Hội thoại</span></a>
      {reviewer && !operator ? <a href="#models" aria-current={model ? 'page' : undefined}><DesignIcon name={model ? "model" : "model-inactive"}/><span>Mô hình</span></a> : operator ? <a href="#market" aria-current={market ? 'page' : undefined}><DesignIcon name="settings"/><span>Dữ liệu</span></a> : <a href={link('profile')} aria-current={['profile', 'risk-assessment'].includes(view) ? 'page' : undefined}><DesignIcon name="settings"/><span>Hồ sơ</span></a>}
    </nav>
  </>;
}

export function Methodology() {
  return <details id="methodology" className="methodology"><summary>Cách hệ thống hoạt động</summary><div className="methodology-body"><h2>Hiểu dữ liệu trước khi quyết định</h2><p>Đề xuất sử dụng bộ tài sản và ngày dữ liệu được ghi trên kết quả. Dữ liệu minh họa được gắn nhãn riêng; lợi nhuận tương lai không được bảo đảm.</p><p>Hồ sơ rủi ro và giới hạn phân bổ do policy của hệ thống xác định từ câu trả lời của bạn. Chấp nhận đề xuất chỉ lưu tỷ trọng mục tiêu, không tạo lệnh mua bán hoặc thay đổi tài sản đang nắm giữ.</p><p>Các phương pháp hiện có: phân bổ đều có ràng buộc (EW), tối ưu lợi nhuận / rủi ro (MVO), và Black–Litterman kết hợp model đã được duyệt (BL + ML). Bạn chủ động cho phép EW dự phòng khi model chưa sẵn sàng.</p></div></details>;
}
