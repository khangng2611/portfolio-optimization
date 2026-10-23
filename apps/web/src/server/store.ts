import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';
import { createClient } from 'redis';
export interface Backend {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, seconds: number, nx?: boolean): Promise<boolean>;
  take(key: string): Promise<string | null>;
  del(key: string): Promise<void>;
  unlock(key: string, owner: string): Promise<void>;
  guardedSet(key: string, value: string, seconds: number, lock: string, owner: string): Promise<boolean>;
}
export class EncryptedStore {
  constructor(private backend: Backend, private key: Buffer) { if (key.length !== 32) throw new Error('Invalid encryption key'); }
  private seal(key: string, value: unknown) {
    const iv = randomBytes(12);
    const cipher = createCipheriv('aes-256-gcm', this.key, iv);
    cipher.setAAD(Buffer.from(key));
    const encrypted = Buffer.concat([cipher.update(JSON.stringify(value), 'utf8'), cipher.final()]);
    return Buffer.concat([iv, cipher.getAuthTag(), encrypted]).toString('base64url');
  }
  private open<T>(key: string, value: string | null): T | null {
    if (value === null) return null;
    const data = Buffer.from(value, 'base64url');
    const cipher = createDecipheriv('aes-256-gcm', this.key, data.subarray(0, 12));
    cipher.setAAD(Buffer.from(key));
    cipher.setAuthTag(data.subarray(12, 28));
    return JSON.parse(Buffer.concat([cipher.update(data.subarray(28)), cipher.final()]).toString('utf8')) as T;
  }
  async get<T>(key: string) { return this.open<T>(key, await this.backend.get(key)); }
  async take<T>(key: string) { return this.open<T>(key, await this.backend.take(key)); }
  async put(key: string, value: unknown, seconds: number) { await this.backend.set(key, this.seal(key, value), seconds); }
  async del(key: string) { await this.backend.del(key); }
  async lock(id: string, owner: string) { return this.backend.set(`lock:${id}`, owner, 15, true); }
  async unlock(id: string, owner: string) { await this.backend.unlock(`lock:${id}`, owner); }
  async saveRefreshed(id: string, value: unknown, seconds: number, owner: string) {
    return this.backend.guardedSet(`session:${id}`, this.seal(`session:${id}`, value), seconds, `lock:${id}`, owner);
  }
}
export async function connectStore(url: string, key: Buffer) {
  const redis = createClient({ url, socket: { connectTimeout: 3000, reconnectStrategy: retries => Math.min(100 * 2 ** Math.min(retries, 5), 2000) + Math.floor(Math.random() * 100) }, disableOfflineQueue: true });
  redis.on('error', () => { /* Requests fail closed; do not log token-bearing values. */ });
  // Startup has a deadline; an established client keeps retrying with a bounded delay.
  // Commands never queue while disconnected, so outage requests fail closed immediately.
  let deadline: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([redis.connect(), new Promise<never>((_, reject) => {
      deadline = setTimeout(() => reject(new Error('Session store connection timed out')), 4000);
    })]);
  } catch (error) { if (redis.isOpen) redis.destroy(); throw error; }
  finally { clearTimeout(deadline); }
  const backend: Backend = {
    get: key => redis.get(key),
    set: async (key, value, seconds, nx = false) => (await redis.set(key, value, { EX: seconds, ...(nx ? { NX: true } : {}) })) === 'OK',
    take: key => redis.getDel(key),
    del: async key => { await redis.del(key); },
    unlock: async (key, owner) => { await redis.eval("if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) else return 0 end", { keys: [key], arguments: [owner] }); },
    guardedSet: async (key, value, seconds, lock, owner) => (await redis.eval("if redis.call('GET',KEYS[2]) == ARGV[1] and redis.call('EXISTS',KEYS[1]) == 1 then redis.call('SET',KEYS[1],ARGV[2],'EX',ARGV[3]); return 1 else return 0 end", { keys: [key, lock], arguments: [owner, value, String(seconds)] })) === 1,
  };
  return new EncryptedStore(backend, key);
}
