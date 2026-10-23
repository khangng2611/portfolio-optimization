export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const { configureTracing } = await import('./server/tracing');
    configureTracing();
  }
}
