import type { Allocation } from '../components/allocation-view';
import type { TraceReference } from './job-trace';
export type RiskAnswers = { questionnaire_version: string; horizon_months: number; liquidity_need: 'low' | 'medium' | 'high'; loss_tolerance: 'low' | 'medium' | 'high'; experience: 'beginner' | 'experienced' };
export type RiskProfile = { profile: string; answers?: RiskAnswers; version_id?: string; mapping_version?: string };
export type Portfolio = { id: string; name: string; capital_vnd: string; universe_id: string; version: number; constraints: { risk_aversion: number; max_position_weight: number }; risk_profile: RiskProfile | null; policy_version_id: string };
export type Recommendation = TraceReference & Allocation & { id: string; portfolio_id: string; portfolio_version: number };
export type Target = { id: string; recommendation_id: string; accepted_at: string; allocation: Recommendation; portfolio_version: number };
export type Dashboard = { portfolio: Portfolio; accepted_target: Target | null; proposal_count: number; target_matches_portfolio: boolean };
export type Api = <T>(path: string, init?: RequestInit) => Promise<T>;
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type PageApi = <T>(path: string) => Promise<Page<T>>;
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
export const dateTime = (date: string) => new Date(date).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
