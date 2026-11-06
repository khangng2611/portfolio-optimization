import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import './ui-refresh.css';

const beVietnamPro = localFont({
  src: [
    { path: './fonts/be-vietnam-pro-400.ttf', weight: '400', style: 'normal' },
    { path: './fonts/be-vietnam-pro-500.ttf', weight: '500', style: 'normal' },
    { path: './fonts/be-vietnam-pro-600.ttf', weight: '600', style: 'normal' },
    { path: './fonts/be-vietnam-pro-700.ttf', weight: '700', style: 'normal' },
  ],
  display: 'swap', variable: '--font-be-vietnam-pro',
});
export const metadata: Metadata = { title: 'portfolio. · Kế hoạch đầu tư của bạn', description: 'Đánh giá rủi ro, xem đề xuất phân bổ và chủ động chọn tỷ trọng mục tiêu.' };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="vi"><body className={beVietnamPro.variable}>{children}</body></html>; }
