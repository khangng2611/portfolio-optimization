import { it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseWorkspaceHash, workspaceHash } from '../src/lib/workspace-state';
import { WorkspaceShell } from '../src/components/workspace-shell';

const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const job = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
it('preserves Chat conversation and job destinations across login/reload', () => {
  const route = { view: 'chat' as const, conversationId: id, jobId: job };
  expect(parseWorkspaceHash(workspaceHash(route))).toEqual(route);
  expect(parseWorkspaceHash('#chat?conversation=bad').invalid).toBe(true);
  expect(parseWorkspaceHash(`#chat?conversation=${id}&conversation=${job}`).invalid).toBe(true);
});
it('exposes an active Chat navigation route in the existing shell', () => {
  const html = renderToStaticMarkup(<WorkspaceShell view="chat" account="Alice" busy={false} onLogout={() => {}} context="Hội thoại"><p>Chat</p></WorkspaceShell>);
  expect(html).toContain('href="#chat"');
  expect(html).not.toContain('Hội thoại chưa được triển khai');
});
it('keeps nested portfolio tasks active in desktop and mobile navigation', () => {
  for (const view of ['proposal', 'compare', 'history', 'edit'] as const) {
    const html = renderToStaticMarkup(<WorkspaceShell view={view} portfolioId={id} account="Minh họa" busy={false} onLogout={() => {}} context="Kế hoạch"><p>UI</p></WorkspaceShell>);
    expect((html.match(/href="#portfolios"[^>]*aria-current="page"/g) ?? []).length).toBe(3);
  }
});
it('returns from the breadcrumb to its named workspace rather than the portfolio list', () => {
  for (const [view, expected] of [['chat', '#chat?portfolio=' + id], ['history', '#overview?portfolio=' + id], ['market-quality', '#market'], ['model-review', '#models']] as const) {
    const html = renderToStaticMarkup(<WorkspaceShell view={view} portfolioId={id} account="Minh họa" busy={false} onLogout={() => {}} context="Ngữ cảnh"><p>UI</p></WorkspaceShell>);
    expect(html).toContain(`class="breadcrumb" href="${expected}"`);
  }
});
