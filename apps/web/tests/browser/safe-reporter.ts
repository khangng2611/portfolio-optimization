import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { FullResult, Reporter, TestCase, TestResult } from '@playwright/test/reporter';

// Default HTML/JSON reporters include auth form values, URLs and call logs.
// Deliberately emit only static test names/status and an optional safe phase.
export default class SafeReporter implements Reporter {
  private tests: { title: string; status: string; duration_ms: number; phase?: string; assertion_line?: number }[] = [];
  onStdOut(chunk: string | Buffer) {
    const output = chunk.toString();
    if (/^BROWSER_PHASE: [a-z0-9-]+\n$/.test(output)) process.stdout.write(output);
  }
  onTestEnd(test: TestCase, result: TestResult) {
    const phase = result.annotations.find(item => item.type === 'safe-phase')?.description;
    const line = result.errors.map(error => error.stack?.match(/lifecycle\.e2e\.ts:(\d+):\d+/)?.[1]).find(Boolean);
    this.tests.push({ title: test.title, status: result.status, duration_ms: result.duration, ...(phase ? { phase } : {}), ...(line ? { assertion_line: Number(line) } : {}) });
    console.log(`${result.status.toUpperCase()}: ${test.title}${phase ? ` [${phase}]` : ''}${line ? ` (assertion line ${line})` : ''}`);
  }
  onEnd(result: FullResult) {
    const directory = resolve('../../output/playwright/sanitized');
    mkdirSync(directory, { recursive: true });
    const mode = process.env.BROWSER_VERIFY_RECEIPT === '1' ? 'persistence' : 'lifecycle';
    writeFileSync(resolve(directory, `${mode}.json`), JSON.stringify({ status: result.status, tests: this.tests }, null, 2) + '\n');
  }
}
