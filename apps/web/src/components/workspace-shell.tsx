'use client';
import type { ReactNode } from 'react';
import { ActionIcon } from './action-controls';
import { workspaceHash, type WorkspaceView } from '../lib/workspace-state';

export type { WorkspaceView } from '../lib/workspace-state';
export function DesignIcon({ name }: { name: 'overview' | 'portfolio' | 'chat' | 'views' | 'settings' | 'empty-portfolio' | 'model' | 'model-inactive' }) {
  const size = name === 'empty-portfolio' ? 28 : 20;
  return <img className="nav-icon" src={`/figma/${name}.svg`} width={size} height={size} alt="" aria-hidden="true"/>;
}

export function WorkspaceShell({ children, view, portfolioId, account, busy, onLogout, context, portfolioNavigation, portfolioMore, operator = false, reviewer = false, researcher = false }: {
  children: ReactNode; view: WorkspaceView; account: string | null; busy: boolean;
  onLogout: () => void; context: string; portfolioId?: string; portfolioNavigation?: ReactNode; portfolioMore?: ReactNode; operator?: boolean; reviewer?: boolean; researcher?: boolean;
}) {
  const link = (view: WorkspaceView) => workspaceHash({ view, ...(['portfolios', 'create'].includes(view) ? {} : { portfolioId }) });
  const portfolioTask = ['portfolios', 'create', 'proposal', 'compare', 'history', 'edit', 'holdings', 'rebalance'].includes(view);
  const taskWorkspace = view === 'create' || !!portfolioId && ['overview', 'proposal', 'profile', 'edit', 'compare', 'risk-assessment', 'history'].includes(view);
  const layout = account ? view : 'welcome';
  const market = view.startsWith('market');
  const model = ['models', 'model-training', 'model-review'].includes(view);
  const contextHref = !account ? '#overview' : view === 'chat' || view === 'asset-prices' ? link(view) : market ? '#market' : view === 'knowledge' ? '#knowledge' : model ? '#models' : portfolioId ? link('overview') : ['profile', 'risk-assessment'].includes(view) ? '#profile' : '#portfolios';
  const dataLink = operator && <a href="#market" className={`nav-link ${market ? 'active' : ''}`} aria-current={market ? 'page' : undefined}><svg className="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/></svg>Dữ liệu</a>;
  const links = <>
    {dataLink}
    {operator && <a href="#knowledge" className={`nav-link ${view === 'knowledge' ? 'active' : ''}`} aria-current={view === 'knowledge' ? 'page' : undefined}><DesignIcon name="chat"/>Kho tri thức</a>}
    {researcher && <a href="#research" className={`nav-link ${view === 'research' ? 'active' : ''}`} aria-current={view === 'research' ? 'page' : undefined}><DesignIcon name="views"/>Nghiên cứu</a>}
    {(operator || reviewer) && <a href="#models" className={`nav-link ${model ? 'active' : ''}`} aria-current={model ? 'page' : undefined}><DesignIcon name={model ? "model" : "model-inactive"}/>Mô hình</a>}
    <a href={link('overview')} className={`nav-link ${view === 'overview' ? 'active' : ''}`} aria-current={view === 'overview' ? 'page' : undefined}><DesignIcon name="overview"/>Tổng quan</a>
    <a href="#portfolios" className={`nav-link ${portfolioTask ? 'active' : ''}`} aria-current={portfolioTask ? 'page' : undefined}><DesignIcon name="portfolio"/>Danh mục</a>
    <a href={link('chat')} className={`nav-link ${view === 'chat' ? 'active' : ''}`} aria-current={view === 'chat' ? 'page' : undefined}><DesignIcon name="chat"/>Hội thoại</a>

    <a href={link('profile')} className={`nav-link ${['profile', 'risk-assessment'].includes(view) ? 'active' : ''}`} aria-current={['profile', 'risk-assessment'].includes(view) ? 'page' : undefined}><DesignIcon name="settings"/>Hồ sơ rủi ro</a>
    {account && <a href={link('asset-prices')} className={`nav-link ${view === 'asset-prices' ? 'active' : ''}`} aria-current={view === 'asset-prices' ? 'page' : undefined}><ActionIcon name="market"/>Giá tài sản</a>}
    {account && <a href={link('settings')} className={`nav-link ${view === 'settings' ? 'active' : ''}`} aria-current={view === 'settings' ? 'page' : undefined}><DesignIcon name="settings"/>Cài đặt</a>}
  </>;
  const investorHeader = !!account && (view === 'settings' || view === 'portfolios' || view === 'profile' && !!portfolioId);
  const moreMenu = portfolioNavigation || layout === 'asset-prices' || investorHeader;
  const mobileMenu = <details key={view} className="mobile-menu" onKeyDown={event => { if (event.key === 'Escape') { event.currentTarget.removeAttribute('open'); event.currentTarget.querySelector('summary')?.focus(); } }}><summary aria-label={moreMenu ? "Thêm" : "Điều hướng"}><svg className="mobile-menu-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>{layout === 'chat' && <span className="chat-mobile-brand">portfolio.</span>}<span className="mobile-menu-label">{moreMenu ? "Thêm" : "Điều hướng"}</span></summary><nav aria-label="Điều hướng thu gọn" onClick={event => { if ((event.target as HTMLElement).closest('a')) event.currentTarget.parentElement?.removeAttribute('open'); }}>{portfolioMore}{links}</nav>{layout === 'chat' && <Methodology id="mobile-chat-methodology"/>}{account && <div className="mobile-account-actions"><span>{account}</span>{(moreMenu || view === 'chat') && <button type="button" className="quiet" disabled={busy} onClick={onLogout}>Đăng xuất</button>}</div>}</details>;
  return <>
    <a className="skip-link" href="#main-content">Đến nội dung chính</a>
    <div className="environment-banner"><span>Không gian thử nghiệm · Không thực hiện giao dịch</span><span>Thị trường Việt Nam · VND</span></div>
    {account && <header className={`account-bar${moreMenu ? " account-portfolio" : ""}${view === "create" ? " account-wizard" : ""}`}>
      <div className="context-actions account-actions">
        <span className="account-name" title={account}>{account}</span>
        <button type="button" className="quiet account-logout" aria-label="Đăng xuất" title="Đăng xuất" onClick={onLogout} disabled={busy}><ActionIcon name="logout"/><span>Đăng xuất</span></button>
      </div>
    </header>}
    <div className="app-shell">
      <aside className="sidebar"><a className="brand" href="#overview" aria-label="portfolio. · Tổng quan">portfolio.</a>{(!account || market || model) && <p className="eyebrow">{account && (market || model) ? 'KHÔNG GIAN LÀM VIỆC' : 'KHÔNG GIAN CỦA BẠN'}</p>}<nav aria-label="Điều hướng chính">{links}</nav><div className="sidebar-note">
        <button className="nav-link sidebar-help" type="button" popoverTarget="sidebar-guide"><ActionIcon name="help"/>Dữ liệu và cách tính</button>
        <section key={layout} id="sidebar-guide" className="guide-popover" popover="auto" aria-labelledby="sidebar-guide-title">
          <h2 id="sidebar-guide-title">Dữ liệu và cách tính</h2>
          <MethodologyText/>
          {portfolioNavigation && <a href="#methodology" onClick={event => {
            const detail = document.getElementById('methodology');
            if (detail instanceof HTMLDetailsElement) {
              event.preventDefault();
              document.getElementById('sidebar-guide')?.hidePopover();
              for (let parent: HTMLDetailsElement | null = detail; parent; parent = parent.parentElement?.closest('details') ?? null) parent.open = true;
              detail.querySelector('summary')?.focus();
            }
          }}>Xem dữ liệu trên trang này</a>}
          <button className="quiet" type="button" popoverTarget="sidebar-guide" popoverTargetAction="hide">Đóng</button>
        </section>
      </div></aside>
      <main id="main-content" className={`workspace workspace-${layout}${account && taskWorkspace ? ' workspace-task' : ''}`} data-view={layout} tabIndex={-1}>
        {!account || layout === 'asset-prices' || investorHeader ? <div className="portfolio-header welcome-mobile-header"><a className="portfolio-mobile-brand brand" href="#overview">portfolio.</a>{mobileMenu}</div> : portfolioNavigation ? <div className="portfolio-header"><a className="portfolio-mobile-brand brand" href="#portfolios">portfolio.</a>{mobileMenu}{portfolioNavigation}</div> : <>
          {view === 'create' && account && <nav className="wizard-mobile-nav" aria-label="Điều hướng lập kế hoạch"><a className="brand" href="#portfolios">portfolio.</a><a className="button quiet" href="#portfolios">Danh mục</a></nav>}
          {account && <div className="contextbar"><a className="breadcrumb" href={contextHref}>{context}</a></div>}
          {mobileMenu}
        </>}
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

export function Methodology({ id = 'methodology' }: { id?: string } = {}) {
  return <details id={id} className="methodology"><summary>Dữ liệu và cách tính</summary><MethodologyText/></details>;
}

function MethodologyText() {
  return <div className="methodology-body"><p>Đề xuất dựa trên tài sản được cân nhắc, hồ sơ rủi ro và dữ liệu tại ngày ghi trên kết quả. Dữ liệu minh họa có nhãn riêng. Bạn có thể hỏi cách tính trong Hội thoại.</p><p>Khi bạn chấp nhận, ứng dụng lưu tỷ trọng mục tiêu. Bạn thực hiện giao dịch bên ngoài ứng dụng. Kết quả phân bổ không bảo đảm lợi nhuận.</p></div>;
}
