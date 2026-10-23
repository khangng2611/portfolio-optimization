import { readConfig } from './config';
import { connectStore } from './store';
import { createIdentityProvider } from './oidc';
import { createBff } from './bff';
let pending: Promise<ReturnType<typeof createBff>> | undefined;
async function runtimeBff() {
  pending ??= (async () => {
    const config = readConfig();
    // Allocate the persistent connection only after discovery succeeds; failed
    // initialization must not leave an orphan Redis client on each request.
    const identity = await createIdentityProvider(config);
    const store = await connectStore(config.redisUrl, config.key);
    return createBff(config, store, identity);
  })().catch(error => { pending = undefined; throw error; });
  return pending;
}
export function handler(action: 'login' | 'callback' | 'session' | 'logout' | 'proxy') {
  return async (request: Request) => {
    try { return await (await runtimeBff())[action](request); }
    catch { return Response.json({ error: 'Authentication service unavailable' }, { status: 503, headers: { 'cache-control': 'no-store' } }); }
  };
}
