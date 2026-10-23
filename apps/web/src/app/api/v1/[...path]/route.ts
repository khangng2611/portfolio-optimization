import { handler } from '../../../../server/runtime';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const GET = handler('proxy');
export const POST = handler('proxy');
export const PATCH = handler('proxy');
