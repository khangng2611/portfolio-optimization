'use client';
import type { ReactNode } from 'react';
import { workspaceHash, type WorkspaceView } from '../lib/workspace-state';

export type { WorkspaceView } from '../lib/workspace-state';
export function DesignIcon({ name }: { name: 'overview' | 'portfolio' | 'chat' | 'views' | 'settings' | 'empty-portfolio' }) {
  const size = name === 'empty-portfolio' ? 28 : 20;
  return <img className="nav-icon" src={`/figma/${name}.svg`} width={size} height={size} alt="" aria-hidden="true"/>;
}

export function WorkspaceShell({ children, view, portfolioId, account, busy, onLogout, context, operator = false }: {
  children: ReactNode; view: WorkspaceView; account: string | null; busy: boolean;
  onLogout: () => void; context: string; portfolioId?: string; operator?: boolean;
}) {
  const link = (view: WorkspaceView) => workspaceHash({ view, ...(['portfolios', 'create'].includes(view) ? {} : { portfolioId }) });
  const market = view.startsWith('market');
  const dataLink = operator && <a href="#market" className={`nav-link ${market ? 'active' : ''}`} aria-current={market ? 'page' : undefined}><svg className="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/></svg>Dữ liệu</a>;
  const links = <>
    {dataLink}
    <a href={link('overview')} className={`nav-link ${view === 'overview' ? 'active' : ''}`} aria-current={view === 'overview' ? 'page' : undefined}><DesignIcon name="overview"/>Tổng quan</a>
    <a href="#portfolios" className={`nav-link ${['portfolios', 'create', 'proposal'].includes(view) ? 'active' : ''}`} aria-current={['portfolios', 'create', 'proposal'].includes(view) ? 'page' : undefined}><DesignIcon name="portfolio"/>Danh mục</a>
    <span className="nav-link unavailable" aria-disabled="true" title="Hội thoại chưa được triển khai"><DesignIcon name="chat"/>Hội thoại <small>Sắp có</small></span>
    <span className="nav-link unavailable" aria-disabled="true" title="Nhận định chưa được triển khai"><DesignIcon name="views"/>Nhận định <small>Sắp có</small></span>
    <a href={link('profile')} className={`nav-link ${view === 'profile' ? 'active' : ''}`} aria-current={view === 'profile' ? 'page' : undefined}><DesignIcon name="settings"/>Hồ sơ & cài đặt</a>
  </>;
  return <>
    <a className="skip-link" href="#main-content">Đến nội dung chính</a>
    <div className="environment-banner"><span>KHÔNG GIAN THỬ NGHIỆM · KHÔNG THỰC HIỆN GIAO DỊCH</span><span>Thị trường Việt Nam · VND</span></div>
    <div className="app-shell">
      <aside className="sidebar"><a className="brand" href="#overview" aria-label="portfolio. · Tổng quan">portfolio.</a><p className="eyebrow">{market ? 'KHÔNG GIAN LÀM VIỆC' : 'KHÔNG GIAN CỦA BẠN'}</p><nav aria-label="Điều hướng chính">{links}</nav><div className="sidebar-note"><p>Quyền được cấp theo vai trò.<br/>Dữ liệu riêng thuộc chủ sở hữu.</p><a href="#methodology">Dữ liệu & phương pháp</a></div></aside>
      <main id="main-content" className="workspace" tabIndex={-1}>
        <div className="contextbar"><a className="breadcrumb" href={account ? '#portfolios' : '#overview'}>{account ? context : 'Truy cập'}</a><div className="context-actions"><span className="account-name">{account ?? 'Không gian cá nhân'}</span>{account && <button className="quiet" onClick={onLogout} disabled={busy}>Đăng xuất</button>}</div></div>
        <details className="mobile-menu"><summary>Điều hướng</summary><nav aria-label="Điều hướng thu gọn" onClick={event => { if ((event.target as HTMLElement).closest('a')) event.currentTarget.parentElement?.removeAttribute('open'); }}>{links}</nav></details>
        {children}
        <footer className="page-footer"><span>Portfolio Optimization · Không thực hiện giao dịch</span><span>VND · Thời gian GMT+7</span></footer>
      </main>
    </div>
    <nav className="bottom-nav" aria-label="Điều hướng di động">
      <a href={link('overview')} aria-current={view === 'overview' ? 'page' : undefined}><DesignIcon name="overview"/><span>Tổng quan</span></a>
      <a href="#portfolios" aria-current={['portfolios', 'create'].includes(view) ? 'page' : undefined}><DesignIcon name="portfolio"/><span>Danh mục</span></a>
      <a href={link('proposal')} aria-current={view === 'proposal' ? 'page' : undefined}><DesignIcon name="views"/><span>Đề xuất</span></a>
      {operator ? <a href="#market" aria-current={market ? 'page' : undefined}><DesignIcon name="settings"/><span>Dữ liệu</span></a> : <a href={link('profile')} aria-current={view === 'profile' ? 'page' : undefined}><DesignIcon name="settings"/><span>Hồ sơ</span></a>}
    </nav>
  </>;
}

export function Methodology() {
  return <details id="methodology" className="methodology"><summary>Chi tiết dữ liệu & phương pháp</summary><div className="methodology-body"><h2>Hiểu dữ liệu trước khi quyết định</h2><p>Đề xuất sử dụng bộ tài sản và ngày dữ liệu được ghi trên kết quả. Dữ liệu minh họa được gắn nhãn riêng; lợi nhuận tương lai không được bảo đảm.</p><p>Hồ sơ rủi ro và giới hạn phân bổ do policy của hệ thống xác định từ câu trả lời của bạn. Chấp nhận đề xuất chỉ lưu tỷ trọng mục tiêu, không tạo lệnh mua bán hoặc thay đổi tài sản đang nắm giữ.</p><p>Các phương pháp hiện có: phân bổ đều có ràng buộc (EW), tối ưu lợi nhuận / rủi ro (MVO), và Black–Litterman kết hợp model đã được duyệt (BL + ML). Bạn chủ động cho phép EW dự phòng khi model chưa sẵn sàng.</p></div></details>;
}
