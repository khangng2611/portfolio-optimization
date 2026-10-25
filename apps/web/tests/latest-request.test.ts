import { expect, it } from 'vitest';
import { LatestRequest } from '../src/lib/latest-request';

it('ignores older proposal replies and failures after a newer selection', async () => {
  const loader = new LatestRequest();
  let older: (value: string) => void = () => {};
  const first = loader.run(() => new Promise<string>(resolve => { older = resolve; }));
  const second = loader.run(async () => 'proposal B');
  expect(await second).toBe('proposal B');
  older('proposal A');
  expect(await first).toBeUndefined();
  let fail: (error: Error) => void = () => {};
  const pending = loader.run(() => new Promise<string>((_, reject) => { fail = reject; }));
  loader.invalidate();
  fail(new Error('outdated request failed'));
  expect(await pending).toBeUndefined();
  await expect(loader.run(async () => { throw new Error('current failure'); })).rejects.toThrow('current failure');
});
