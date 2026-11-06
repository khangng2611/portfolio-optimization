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

it('shares an in-flight snapshot per resource without starving slow reads and rejects older selections', async () => {
  const loader = new LatestRequest();
  let finishOld: (value: string) => void = () => {};
  let finishNew: (value: string) => void = () => {};
  let calls = 0;
  const first = loader.runFor('old-job:page0', () => { calls++; return new Promise<string>(resolve => { finishOld = resolve; }); });
  const repeated = loader.runFor('old-job:page0', async () => { calls++; return 'unexpected'; });
  expect(calls).toBe(1);
  const second = loader.runFor('new-job:page50', () => new Promise<string>(resolve => { finishNew = resolve; }));
  finishNew('new snapshot');
  expect(await second).toBe('new snapshot');
  finishOld('old snapshot');
  expect(await first).toBeUndefined();
  expect(await repeated).toBeUndefined();
  expect(await loader.runFor('old-job:page0', async () => 'fresh read')).toBe('fresh read');
});
