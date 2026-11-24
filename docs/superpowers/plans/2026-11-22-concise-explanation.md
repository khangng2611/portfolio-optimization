# Concise Explanation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. User authorized inline execution; preserve dirty source, no commits.

**Goal:** Trả lời ngắn đúng câu hỏi, mở thêm chi tiết và giữ immutable evidence/citations.
**Architecture:** Finite metric claims + summaries; constrained enum selector; v2 renderer; existing disclosure UI.
**Tech Stack:** Current Python/Pydantic/Responses and React/Next/Vitest; no new dependencies.
**Spec:** [Approved design](../specs/2026-11-22-concise-explanation-design.md).

## Global Constraints
- Không đổi numerical algorithms/model/data/facts/evidence hashes/confirmation/accept; không viết lại message cũ.
- Giữ đồng thời HYBRID/UI/strategy changes; không reset/stash/clean hoặc chạm research/secrets/volumes.
- Cap1USD giữ nguyên, không reset quotas/counters/Auto Recharge. Không commit/push/merge/Sheet.

## Review Focus
1. PARTIAL views không được suy ra không có view âm — task1 regression.
2. Metric hỏi mã thiếu hoặc nhiều mã không lấy dữ liệu mã khác — task1 regression.
3. Provider ID sai/missing required/hash vẫn bị chặn — task1 regression.
4. V2 prose chỉ hiện sau canonical/evidence validation; legacy đọc được — task2 regression.
5. Citations/hash và saved receipt không đổi sau restart — task3 real verify.

## Task1 — Claims, renderer and provider
Files: `services/chat/src/chat_service/{explanation,openai_provider,workflow}.py`, `tests/software/test_chat_explanation_evidence.py`.
Interfaces: `render_claims(claims,ids,*,concise=False)` giữ legacy default; `default_ids(claims,question)` trả metric-focused IDs; `detail_requested(question)`; claim.summary optional. Provider schema giới hạn IDs theo required set, validator vẫn độc lập.
- [x] RED: RSI-only, confidence units, summary-vs-detail, absent negative COMPLETE/PARTIAL, missing/named assets, constrained provider plan, no repeated corpus prose.
- [x] Implement minimal builder/selector/v2 workflow; GREEN all relevant Chat tests.
- [x] Real backend explanation on existing native recommendation before UI integration. No allocation required.

## Task2 — Disclosure UI
Files: `apps/web/src/components/chat-workspace.tsx`, `apps/web/src/lib/chat-types.ts`, `apps/web/tests/chat-workspace.test.tsx`.
- [x] RED: v2 validated prose visible while detailed evidence closed, legacy opening retained, mismatch hides answer.
- [x] Implement only v2 display path, preserve current controls/tokens; web tests/typecheck.

## Task3 — Eval, real provider and handoff
Files: `scripts/eval_allocation_explanation.py`, new frozen `tests/fixtures/knowledge/eval-allocation-explanation-vi-v2.*`, eval tests, runbook/status.
- [x] Freeze additional Vietnamese focused/absence/detail cases; compare same questions against old renderer baseline with explicit concision/correctness rubric. v1 fixture unchanged.
- [x] Full Python/core, web, TypeScript, Ruff, host production build and independent review. Regression covers material findings.
- [x] Capped real OpenAI smoke on the first v2 implementation, existing native receipt, citation and usage audit.
- [x] Rebuild and deploy final Chat and Web images after Docker recovery. Final OpenAI smoke passed 8/8 under cap 1 USD with 16 verified citations.
- [x] Final browser checks passed at 1440, 390 and 375 CSS px. Verified four exact receipts after restarting Chat API, Chat worker and Web. The verification added zero provider calls.
- [x] Report actual passes/skips/estimate vs invoice; docs + Sheet checklist proposal only.
