import { expect, it } from 'vitest';
import { transcriptScrollAction } from '../src/lib/chat-scroll';
it('opens the latest history at its end, while an explicitly older page starts at its first message', () => {
  expect(transcriptScrollAction(null, { offset: 50, lastId: 'm99' }, true, true)).toBe('end');
  expect(transcriptScrollAction({ offset: 50, lastId: 'm99' }, { offset: 0, lastId: 'm49' }, false, true)).toBe('start');
});
it('does not pull someone away from the message they are reading when a new message arrives', () => {
  const previous = { offset: 0, lastId: 'm1' }, next = { offset: 0, lastId: 'm2' };
  expect(transcriptScrollAction(previous, next, true, false)).toBe('preserve');
  expect(transcriptScrollAction(previous, next, true, true)).toBe('end');
  expect(transcriptScrollAction(next, next, true, true)).toBe('preserve');
});
it('does not force an automatic page advance to the end while someone is reading above', () => {
  expect(transcriptScrollAction({ offset: 0, lastId: 'm49' }, { offset: 50, lastId: 'm50' }, true, false)).toBe('preserve');
});
