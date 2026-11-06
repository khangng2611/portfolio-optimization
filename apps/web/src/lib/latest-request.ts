/** Only the latest requested proposal may update the actionable preview. */
export class LatestRequest {
  private generation = 0;
  private pending?: { key: string; promise: Promise<unknown> };
  invalidate() { this.generation++; this.pending = undefined; }
  runFor<T>(key: string, request: () => Promise<T>): Promise<T | undefined> {
    if (this.pending?.key === key) return this.pending.promise as Promise<T | undefined>;
    const promise = this.run(request);
    const pending = { key, promise };
    this.pending = pending;
    const clear = () => { if (this.pending === pending) this.pending = undefined; };
    void promise.then(clear, clear);
    return promise;
  }
  async run<T>(request: () => Promise<T>): Promise<T | undefined> {
    const generation = ++this.generation;
    try {
      const value = await request();
      return generation === this.generation ? value : undefined;
    } catch (error) {
      if (generation === this.generation) throw error;
      return undefined;
    }
  }
}
