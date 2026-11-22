'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent } from 'react';

const signupKey = 'portfolio.registered-username';
// Match Python's string.punctuation in the registration API.
const passwordPunctuation = /[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]/;

function registrationPasswordError(password: string) {
  const length = [...password].length;
  if (length < 6) return 'Mật khẩu cần ít nhất 6 ký tự.';
  if (length > 128) return 'Mật khẩu chỉ được tối đa 128 ký tự.';
  if (!passwordPunctuation.test(password)) return 'Mật khẩu cần ít nhất một ký tự đặc biệt như !, @ hoặc #.';
  return '';
}

export function AuthForm({ register = false }: { register?: boolean }) {
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [registered, setRegistered] = useState(false);
  const usernameField = useRef<HTMLInputElement>(null);
  const passwordField = useRef<HTMLInputElement>(null);
  const errorField = useRef<HTMLParagraphElement>(null);
  const title = register ? 'Đăng ký' : 'Đăng nhập';

  useEffect(() => {
    setReady(true);
    if (register) return;
    try {
      const username = sessionStorage.getItem(signupKey);
      sessionStorage.removeItem(signupKey);
      if (username && usernameField.current && !usernameField.current.value) {
        usernameField.current.value = username;
        setRegistered(true);
      }
    } catch { /* Autofill is optional. */ }
  }, [register]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    setError('');
    const invalidPassword = register ? registrationPasswordError(String(body.password)) : '';
    setPasswordError(invalidPassword);
    if (invalidPassword) {
      passwordField.current?.focus();
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(register ? '/auth/register' : '/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error ?? 'Dịch vụ đăng nhập chưa sẵn sàng.');
      }
      if (register) {
        try { sessionStorage.setItem(signupKey, String(body.username).trim().toLowerCase()); } catch { /* Autofill is optional. */ }
        window.location.replace('/login');
      } else {
        window.location.replace('/?signed-in=1');
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Dịch vụ đăng nhập chưa sẵn sàng.');
      requestAnimationFrame(() => errorField.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page">
    <Link href="/" className="wordmark">portfolio.</Link>
    <form className="panel auth-form" method="post" onSubmit={submit} aria-busy={busy}>
      <h1>{title}</h1>
      {registered && <p className="notice" role="status">Đã tạo tài khoản. Hãy đăng nhập để bắt đầu.</p>}
      {error && <p className="error" role="alert" ref={errorField} tabIndex={-1}>{error}</p>}
      {register && <label>Tên hiển thị<input name="name" autoComplete="name" required maxLength={120}/></label>}
      <label>Tên đăng nhập<input ref={usernameField} name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} required maxLength={128} aria-describedby={register ? 'username-hint' : undefined}/></label>
      {register && <p className="muted small" id="username-hint">Dùng 3–32 chữ cái không dấu, số, dấu gạch ngang hoặc gạch dưới.</p>}
      <label>Mật khẩu<input
        ref={passwordField} name="password" type="password"
        autoComplete={register ? 'new-password' : 'current-password'}
        required maxLength={256} aria-invalid={Boolean(passwordError) || undefined}
        aria-describedby={register ? 'password-hint' : undefined}
        onChange={() => setPasswordError('')}
      /></label>
      {register && (passwordError
        ? <p className="error" id="password-hint" role="alert">{passwordError}</p>
        : <p className="muted small" id="password-hint">Dùng 6–128 ký tự, có ít nhất một ký tự đặc biệt như !, @ hoặc #.</p>)}
      <button type="submit" disabled={!ready || busy}>{busy ? 'Đang xử lý…' : title}</button>
      {register ? <p>Đã có tài khoản? <Link href="/login">Đăng nhập</Link></p> : <p>Chưa có tài khoản? <Link href="/register">Đăng ký</Link></p>}
    </form>
  </main>;
}
