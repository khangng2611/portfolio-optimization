import { readConfig } from './config';
import { connectStore } from './store';
import { createIdentityProvider } from './identity';
import { createBff } from './bff';
let pending: Promise<ReturnType<typeof createBff>> | undefined;
async function runtimeBff() {
  pending ??= (async () => {
    const config = readConfig();
    const identity = createIdentityProvider(config);
    const store = await connectStore(config.redisUrl, config.key);
    return createBff(config, store, identity);
  })().catch(error => { pending = undefined; throw error; });
  return pending;
}
export function handler(action: 'login' | 'register' | 'session' | 'logout' | 'proxy') {
  return async (request: Request) => {
    try { return await (await runtimeBff())[action](request); }
    catch { return Response.json({ error: 'Authentication service unavailable' }, { status: 503, headers: { 'cache-control': 'no-store' } }); }
  };
}
