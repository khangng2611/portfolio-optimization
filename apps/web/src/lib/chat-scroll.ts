export type TranscriptPosition = { offset: number; lastId: string | undefined };
export function transcriptScrollAction(previous: TranscriptPosition | null, next: TranscriptPosition, latestPage: boolean, nearEnd: boolean): 'start' | 'end' | 'preserve' {
  if (!previous) return latestPage ? 'end' : 'start';
  if (previous.offset !== next.offset) return latestPage ? nearEnd ? 'end' : 'preserve' : 'start';
  return previous.lastId !== next.lastId && nearEnd ? 'end' : 'preserve';
}
