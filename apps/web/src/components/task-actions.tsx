import type { ReactNode } from 'react';

/** Remains inside the owning form so native submit/validation and disabled gates still apply. */
export function TaskActions({ children, hint, label = 'Hành động của bước này' }: { children: ReactNode; hint?: string; label?: string }) {
  return <div className="task-actions" role="group" aria-label={label}><div className="task-actions-inner">{hint && <p className="muted small">{hint}</p>}<div className="actions">{children}</div></div></div>;
}
