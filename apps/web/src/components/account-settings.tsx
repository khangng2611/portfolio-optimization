'use client';

import { useState } from 'react';
import './investor-account.css';
import type { WorkspaceView } from '../lib/workspace-state';

type Unavailable = { title: string; message: string; research?: boolean };

export const unavailableWorkspaces: Partial<Record<WorkspaceView, Unavailable>> = {
  views: {
    title: 'Nhận định của bạn',
    message: 'Đề xuất hệ thống hiện sử dụng mô hình đã duyệt và quy tắc phân bổ. Ứng dụng chưa hỗ trợ lưu và áp dụng nhận định do bạn nhập.',
  },
  research: {
    title: 'Thí nghiệm và backtest',
    message: 'Chưa có dịch vụ thí nghiệm để lưu cấu hình, theo dõi tác vụ và đọc kết quả đã đăng ký theo quyền truy cập.',
    research: true,
  },
};

export function UnavailableWorkspace({ content, canResearch, overviewHref }: { content: Unavailable; canResearch: boolean; overviewHref: string }) {
  return <section className="panel empty-state">
    <h2>{content.research && !canResearch ? 'Cần quyền nghiên cứu' : 'Chưa khả dụng'}</h2>
    <p>{content.research && !canResearch ? 'Mục này dành cho tài khoản có quyền nghiên cứu hoặc quản trị.' : content.message}</p>
    <a className="button quiet" href={overviewHref}>Về tổng quan</a>
  </section>;
}

const roleLabels: Record<string, string> = { investor: 'Nhà đầu tư', researcher: 'Nghiên cứu', 'data-operator': 'Vận hành dữ liệu', 'model-reviewer': 'Duyệt mô hình', 'system-admin': 'Quản trị hệ thống' };

export function AccountSettings({ name, roles, busy, logout, profileHref, overviewHref = '#overview' }: { name: string; roles: string[]; busy: boolean; logout: () => void; profileHref: string; overviewHref?: string }) {
  const [confirm, setConfirm] = useState(false);
  return <section className="investor-settings">
    <p className="muted investor-context">Tài khoản của bạn</p>
    <section className="investor-fact"><h2>Thông tin tài khoản</h2>
      <dl className="account-facts">
        <div><dt>Tên hiển thị</dt><dd>{name}</dd></div>
        <div><dt>Ngôn ngữ</dt><dd>Tiếng Việt</dd></div>
        <div><dt>Múi giờ</dt><dd>Giờ Việt Nam (GMT+7)</dd></div>
        <div><dt>Đơn vị tiền tệ</dt><dd>VND</dd></div>
        <div><dt>Quyền</dt><dd>{roles.map(role => roleLabels[role] ?? role).join(' · ')}</dd></div>
      </dl>
    </section>
    <div className="actions"><a className="button quiet" href={profileHref}>Hồ sơ rủi ro</a><a className="button quiet" href={overviewHref}>Quay lại</a></div>
    <details className="investor-disclosure"><summary>Phiên đăng nhập và quyền riêng tư</summary>
      <p>Ứng dụng hiện chưa hỗ trợ đổi thông tin cá nhân, quản lý phiên khác hoặc đóng tài khoản.</p>
      {confirm && <p>Đăng xuất sẽ đóng phiên hiện tại. Các mục tiêu và hội thoại đã lưu vẫn có trong tài khoản.</p>}
      <div className="actions">{confirm ? <><button type="button" disabled={busy} onClick={logout}>Xác nhận đăng xuất</button><button type="button" className="quiet" onClick={() => setConfirm(false)}>Quay lại</button></> : <button type="button" className="quiet" disabled={busy} onClick={() => setConfirm(true)}>Đăng xuất khỏi phiên này</button>}</div>
    </details>
  </section>;
}
