export interface Config {
  origin: string; issuer: string; authUrl: string; authWebSecret: string;
  redisUrl: string; key: Buffer; portfolioUrl: string; marketUrl?: string; quantUrl?: string; mlUrl?: string; chatUrl?: string; knowledgeUrl?: string;
  allowHttp: boolean; secureCookies: boolean; sessionSeconds: number;
}
export function readConfig(env: Record<string, string | undefined> = process.env): Config {
  const required = (name: string) => { const value = env[name]; if (!value) throw new Error(`Missing ${name}`); return value; };
  const origin = new URL(required('APP_ORIGIN'));
  const allowHttp = env.ALLOW_INSECURE_HTTP === 'true';
  if (origin.origin !== required('APP_ORIGIN') || origin.username || origin.password) throw new Error('APP_ORIGIN must be an origin');
  if (origin.protocol !== 'https:' && !(allowHttp && origin.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname))) throw new Error('APP_ORIGIN requires HTTPS (or explicit localhost development mode)');
  const issuer = new URL(required('OIDC_ISSUER'));
  const auth = new URL(required('AUTH_API_URL'));
  const portfolio = new URL(required('PORTFOLIO_API_URL'));
  const market = env.MARKET_API_URL ? new URL(env.MARKET_API_URL) : undefined;
  const quant = env.QUANT_API_URL ? new URL(env.QUANT_API_URL) : undefined;
  const ml = env.ML_API_URL ? new URL(env.ML_API_URL) : undefined;
  const chat = env.CHAT_API_URL ? new URL(env.CHAT_API_URL) : undefined;
  const knowledge = env.KNOWLEDGE_API_URL ? new URL(env.KNOWLEDGE_API_URL) : undefined;
  for (const url of [issuer, auth, portfolio, market, quant, ml, chat, knowledge].filter((v): v is URL => !!v)) {
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Invalid service URL');
  }
  if (issuer.protocol !== 'https:' && !allowHttp) throw new Error('OIDC requires HTTPS');
  if (auth.pathname !== '/' || (auth.protocol !== 'https:' && !allowHttp)) throw new Error('Invalid AUTH_API_URL');
  if ([portfolio, market, quant, ml, chat, knowledge].some(url => url && url.pathname !== '/')) throw new Error('Service API URL must be an origin');
  const key = Buffer.from(required('SESSION_ENCRYPTION_KEY'), 'base64');
  if (key.length !== 32) throw new Error('SESSION_ENCRYPTION_KEY must encode 32 random bytes');
  const sessionSeconds = Number(env.SESSION_TTL_SECONDS ?? '28800');
  if (!Number.isInteger(sessionSeconds) || sessionSeconds < 60 || sessionSeconds > 86400) throw new Error('SESSION_TTL_SECONDS must be 60..86400');
  return { origin: origin.origin, issuer: issuer.href.replace(/\/$/, ''), authUrl: auth.origin, authWebSecret: required('AUTH_WEB_SECRET'), redisUrl: required('REDIS_URL'), key, portfolioUrl: portfolio.origin, marketUrl: market?.origin, quantUrl: quant?.origin, mlUrl: ml?.origin, chatUrl: chat?.origin, knowledgeUrl: knowledge?.origin, allowHttp, secureCookies: origin.protocol === 'https:', sessionSeconds };
}
