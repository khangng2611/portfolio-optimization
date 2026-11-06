import type { ButtonHTMLAttributes } from 'react';

export type ActionIconName = 'refresh' | 'previous' | 'next' | 'logout' | 'options' | 'send' | 'search' | 'filter' | 'sort' | 'auto' | 'portfolio' | 'profile' | 'market' | 'allocation' | 'explain' | 'help';
const paths: Record<ActionIconName, string> = {
 refresh: 'M20 7v5h-5 M19.2 12a7.5 7.5 0 1 1-2-6.2L20 8',
 previous: 'm14 6-6 6 6 6', next: 'm10 6 6 6-6 6',
 logout: 'M10 4H4v16h6 M9 12h11 m-4-4 4 4-4 4',
 options: 'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6',
 send: 'M12 20V4 m-6 6 6-6 6 6',
 search: 'M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15Z m5.5 13 5 5',
 filter: 'M4 5h16l-6 7v6l-4 2v-8Z', sort: 'M7 4v16 m-3-3 3 3 3-3 M13 6h7 M13 11h5 M13 16h3',
 auto: 'M5 5h14v14H5Z M8 9h8 M8 15h8 M10 7v4 M14 13v4',
 portfolio: 'M4 7h16v13H4Z M9 7V4h6v3', profile: 'M12 3 4 6v6c0 4 8 9 8 9s8-5 8-9V6Z m-4 12 3 3 5-6',
 market: 'M4 19V5 M4 19h16 M8 15l4-5 3 2 5-7', allocation: 'M5 20v-6h3v6 M11 20V8h3v12 M17 20V3h3v17',
 explain: 'M4 4h16v12H9l-5 4Z M8 8h8 M8 12h5', help: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z M9.5 9a2.5 2.5 0 1 1 4.3 1.7c-1 .7-1.8 1.2-1.8 2.8 M12 17h.01',
};
export function ActionIcon({ name }: { name: ActionIconName }) {
 return <svg className="action-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]}/></svg>;
}
export function IconButton({ icon, label, className = '', type = 'button', ...props }: { icon: ActionIconName; label: string } & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label'>) {
 return <button {...props} type={type} aria-label={label} className={`quiet icon-button ${className}`}><ActionIcon name={icon}/><span className="control-tooltip" aria-hidden="true">{label}</span></button>;
}
