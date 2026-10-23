import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Danh mục • Portfolio Lab', description: 'Quản lý danh mục và thử nghiệm phân bổ với dữ liệu minh họa.' };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="vi"><body>{children}</body></html>; }
