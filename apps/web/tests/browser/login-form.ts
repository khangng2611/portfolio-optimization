import { expect, type Page } from '@playwright/test';

export async function submitLogin(page: Page, account: { username: string; password: string }) {
  await expect(page.getByRole('heading', { name: 'Đăng nhập', exact: true })).toBeVisible();
  await page.getByLabel('Tên đăng nhập', { exact: true }).fill(account.username);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(account.password);
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/auth/login' && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  expect((await response).status()).toBe(204);
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
}
