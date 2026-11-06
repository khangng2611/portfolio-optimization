# Portfolio Optimization — UI V2.3 handoff

Updated 2026-11-06. Uses ui-ux-pro-max and Impeccable to implement the accepted critique (2 P1, 3 P2) while preserving Be Vietnam Pro, green/cream colors, portfolio semantics and existing backend boundaries.

## Design and flow mapping

[Editable V2.3 section](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-195297). Earlier versions remain available. The section contains 38 desktop/mobile frames, including explicit-answer validation and legacy profile states. Native text, table rows, allocation shapes, icons and controls remain editable. Existing local component/style/variable foundations are reused. Layout tokens add task-specific widths; no replacement palette or typography system.

| Previous journey / issue | Updated position and behavior |
| --- | --- |
| Empty overview required searching for creation | [First-account start](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-196002): direct creation CTA, three understandable steps. Filtered empty, loading and failed requests stay separate. |
| Risk questionnaire preselected answers | [Unanswered risk](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-196423) → explicit choices → [review](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-197139) → confirm/create. Missing answers get inline errors and a keyboard-focusable summary. Back preserves choices. |
| Method acronyms and technical policy dominated choice | [Create proposal](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-197760): plain purpose, method name, optional explanation, immutable policy limits. Request confirmation remains separate from acceptance. |
| Existing proposals overlooked by “first proposal” CTA | [Overview with existing proposals](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-197560): review existing proposals first; generate-new secondary. Code routes to explicit history destination. |
| Review history and long technical blocks compete with allocation | [Review](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-198618): allocation and decision first, history/provenance disclosed. Compare button opens and focuses history in code. |
| Comparison appeared to prefer scenario A | [Compare](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-198712): equivalent A/B review actions, stable asset order and delta meaning. No “best” claim. |
| Chat result stretches across ultrawide screen | [Desktop chat](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-198393), [mobile chat](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=104-199240): bounded reading area, separate portfolio context, persistent composer/consent, compact result links to detailed decision. |
| Profile lacked meaningful context and guessed legacy answers | [Risk profile](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=103-198193), [legacy mobile](https://www.figma.com/design/YKRbiOAJNoVA9DaSZHc7Wc/?node-id=106-200899): saved facts only; absence explicit, reassessment fields blank when facts are missing. |

## Reference application

| Verified official source | Applied learning and limit |
| --- | --- |
| [Wealthfront](https://www.wealthfront.com/investing) | Guided first use, goals and a clear next action. Public investing page only; no authenticated journey claimed. |
| [Portfolio Lab](https://www.portfoliolab.app/tools/portfolio-optimizer) | Method name plus plain purpose, separation of configuration, constraints and result. No extra financial metrics. |
| [Portfolio Visualizer](https://www.portfoliovisualizer.com/optimize-portfolio) | Editable choices distinguished from policy-defined limits; advanced form stays outside onboarding. |
| [Diversiview 2024 dashboard](https://diversiview.online/blog/the-new-diversiview-dashboard/) | Link risk context, analysis and history. Historical reference, not a claim about current UI. |
| [Koyfin](https://www.koyfin.com/features/portfolio-tools/) | Relevant summary rows, stable columns and selective information density. No holdings/performance features imported. |
| [TCWealth](https://www.tcbs.com.vn/ca-nhan/san-pham/tcwealth/) | Vietnamese goal and financial-plan language; retrieved product content did not verify an authenticated journey. |
| [Composer](https://www.composer.trade/learn/creating-and-editing-algorithmic-trading-strategies-with-composer) | Connect inputs to results and keep decisions distinct. No strategy builder or trading automation. |

Retrieved sources and limitations are retained in `output/playwright/design-review-20261106/research/market-notes.json`.

## Data and prototype limits

- No API, algorithm, policy, risk scoring or role changes. Generation confirmation, target acceptance and actual trading remain distinct. No trading action is introduced.
- No Sharpe, expected return, frontier, NAV, drawdown or invented confidence score. Actual holdings/performance remain untracked.
- Saved questionnaire answers are optional in current responses. Missing answers remain missing; reassessment asks explicitly instead of inventing a history.
- Figma data is illustrative. Prototype simulates one deliberate answer sequence and selected transitions. Other answer combinations are supported by code, not a full Figma state machine. Existing V2 confirmation/progress/accepted/scenario-B frames and V2.2 management/chooser are reused where unchanged.
- Browser verification uses intercepted, sanitized API fixtures. It does not validate real backend persistence, numerical optimization, external LLM availability or paid calls. No physical-device soft keyboard or full screen-reader certification is claimed.
- Native Figma node serialization omits visibility. QA excludes only explicitly hidden text nodes confirmed by final screenshots; those hidden layers remain editable. No full-screen raster replacement is used.

## Verification evidence

See `output/playwright/guided-ui-v23/verification.json` for final commands, production image and health, responsive checks and limitations. Test scripts and final screenshots live alongside that file. Detector found two existing 3px side accents in `ui-refresh.css`; both were reduced to 1px. The same existing alert treatment in globals.css was reduced to 1px during the manual visual check. No detector rule was suppressed.
