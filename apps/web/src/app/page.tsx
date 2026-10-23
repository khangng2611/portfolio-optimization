import Home from './home';
import { traceViewerBase } from '../lib/job-trace';

export const dynamic = 'force-dynamic';

export default function Page() {
  return <Home viewerBase={traceViewerBase(process.env.TRACE_VIEWER_URL)}/>;
}
