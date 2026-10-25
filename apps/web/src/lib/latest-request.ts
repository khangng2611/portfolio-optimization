/** Only the latest requested proposal may update the actionable preview. */
export class LatestRequest {
  private generation = 0;
  invalidate() { this.generation++; }
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
