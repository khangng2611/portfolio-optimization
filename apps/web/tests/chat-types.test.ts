import { describe, expect, it } from 'vitest';
import { chatError, chatStopped, createSseParser, sameFacts, storageKey, readPending } from '../src/lib/chat-types';

describe('durable Chat browser helpers', () => {
  it('decodes fragmented CRLF/multiline SSE without publishing incomplete events', () => {
    const parser = createSseParser();
    expect(parser.push(': heartbeat\r\n\r\nid: 4\r\nevent: stage_changed\r\ndata: {"stage":\r')).toEqual([]);
    expect(parser.push('\ndata: "WAIT_ALLOCATION"}\r\n\r\n')).toEqual([{ id: 4, event: 'stage_changed', data: { stage: 'WAIT_ALLOCATION' } }]);
    expect(parser.push('event: reset_required\ndata: {}\n\n')).toEqual([{ id: null, event: 'reset_required', data: {} }]);
  });
  it('rejects invalid sequences and malformed/oversized stream payloads', () => {
    expect(() => createSseParser().push('id: bad\ndata: {}\n\n')).toThrow();
    expect(() => createSseParser().push('id: 1\ndata: not-json\n\n')).toThrow();
    expect(() => createSseParser().push('x'.repeat(262145))).toThrow();
  });
  it('compares full canonical facts including nested provenance and array order', () => {
    expect(sameFacts({ weights: ['.5'], provenance: { source: 'one', rows: 2 } }, { provenance: { rows: 2, source: 'one' }, weights: ['.5'] })).toBe(true);
    expect(sameFacts({ provenance: { source: 'one' } }, { provenance: { source: 'other' } })).toBe(false);
    expect(sameFacts({ assets: ['A', 'B'] }, { assets: ['B', 'A'] })).toBe(false);
  });
  it('separates replay/pending storage by owner and resource and validates drafts', () => {
    expect(storageKey('owner-a', 'job-a', 'sequence')).not.toBe(storageKey('owner-b', 'job-a', 'sequence'));
    expect(storageKey('owner-a', 'job-a', 'sequence')).not.toBe(storageKey('owner-a', 'job-a', 'pending'));
    expect(readPending('{"content":"hello","client_message_id":"bad"}')).toBeNull();
    const body = { content: 'hello', client_message_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', strategy: 'MVO' };
    expect(readPending(JSON.stringify(body))).toEqual(body);
    expect(readPending('{"access_token":"secret"}')).toBeNull();
  });
  it('stops input/authorization jobs and gives safe recovery instead of raw errors', () => {
    for (const value of ['SUCCEEDED', 'WAITING_INPUT', 'FAILED', 'AUTHORIZATION_REQUIRED', 'CANCELLED']) expect(chatStopped(value)).toBe(true);
    expect(chatStopped('WAITING_DEPENDENCY')).toBe(false);
    expect(chatError(429)).toContain('thử lại');
    expect(chatError(401)).toContain('Đăng nhập lại');
    expect(chatError(503)).not.toContain('503');
  });
});
