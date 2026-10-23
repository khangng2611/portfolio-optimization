export interface Config {
  origin: string; issuer: string; internalOrigin?: string; clientId: string; clientSecret: string;
  audience: string; scope: string; redisUrl: string; key: Buffer; portfolioUrl: string;
  allowHttp: boolean; secureCookies: boolean; sessionSeconds: number;
}
export function readConfig(env: Record<string, string | undefined> = process.env): Config {
  const required = (name: string) => { const value = env[name]; if (!value) throw new Error(`Missing ${name}`); return value; };
  const origin = new URL(required('APP_ORIGIN'));
  const allowHttp = env.ALLOW_INSECURE_HTTP === 'true';
  if (origin.origin !== required('APP_ORIGIN') || origin.username || origin.password) throw new Error('APP_ORIGIN must be an origin');
  if (origin.protocol !== 'https:' && !(allowHttp && origin.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname))) throw new Error('APP_ORIGIN requires HTTPS (or explicit localhost development mode)');
  const issuer = new URL(required('OIDC_ISSUER'));
  const internal = env.OIDC_INTERNAL_ORIGIN ? new URL(env.OIDC_INTERNAL_ORIGIN) : undefined;
  const portfolio = new URL(required('PORTFOLIO_API_URL'));
  for (const url of [issuer, internal, portfolio].filter((v): v is URL => !!v)) {
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Invalid service URL');
  }
  if (issuer.protocol !== 'https:' && !allowHttp) throw new Error('OIDC requires HTTPS');
  if (internal && (internal.origin !== env.OIDC_INTERNAL_ORIGIN || (internal.protocol !== 'https:' && !allowHttp))) throw new Error('Invalid OIDC_INTERNAL_ORIGIN');
  if (portfolio.pathname !== '/') throw new Error('PORTFOLIO_API_URL must be an origin');
  const key = Buffer.from(required('SESSION_ENCRYPTION_KEY'), 'base64');
  if (key.length !== 32) throw new Error('SESSION_ENCRYPTION_KEY must encode 32 random bytes');
  const sessionSeconds = Number(env.SESSION_TTL_SECONDS ?? '28800');
  if (!Number.isInteger(sessionSeconds) || sessionSeconds < 60 || sessionSeconds > 86400) throw new Error('SESSION_TTL_SECONDS must be 60..86400');
  return { origin: origin.origin, issuer: issuer.href.replace(/\/$/, ''), internalOrigin: internal?.origin, clientId: env.OIDC_CLIENT_ID ?? 'portfolio-web', clientSecret: required('OIDC_CLIENT_SECRET'), audience: env.OIDC_AUDIENCE ?? 'portfolio-api', scope: env.OIDC_SCOPE ?? 'openid profile email portfolio:read portfolio:write', redisUrl: required('REDIS_URL'), key, portfolioUrl: portfolio.origin, allowHttp, secureCookies: origin.protocol === 'https:', sessionSeconds };
}
