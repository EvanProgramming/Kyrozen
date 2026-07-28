# Kyrozen Desktop Final Test Report

Date: 2026-07-28  
Build: `desktop/release/Kyrozen-0.1.0-arm64.dmg`  
Installed app: `/Applications/Kyrozen.app`  
User-flow projects: **阳台香草浇水提醒器**, **家庭食材保质期助手**

## Release-candidate verification

The latest DMG was mounted, copied into Applications, launched, and operated
through the macOS UI. The installed bundle passes `codesign --verify --deep
--strict`. It is ad-hoc signed and intentionally not notarized because no paid
Apple Developer credentials are configured.

The final user flow created a meaningful second project, described a real
household food-waste problem in ordinary Chinese, answered an AI choice card,
opened the project canvas, initialized Git, and created the real commit
`chore: initialize Kyrozen project`.

## Requested issues

1. GitHub avatar and logout menu are implemented and the avatar rendered.
2. PlatformIO, workspace, sync, model, and tool logs no longer enter chat.
3. Discovery asks one plain-language question at a time, up to four, and now
   requires deeper problem/impact coverage before stopping.
4. Chat and canvas render Markdown/GFM, including headings and tables.
5. High-risk confirmations use inline chat cards; full-trust confirmation is
   also an in-app DESIGN_SYSTEM modal rather than a native alert.
6. The task plan is collapsible and uses outlined/blue/red/green status dots;
   current activity is a single rotating status line.
7. Final answers show an expandable operation record. This was verified with
   `save_problem_brief` and `assess_confidence` operations.
8. Project home is now a focused summary of goal, stage, next action, artifacts,
   and task results.
9. Canvas navigation is reduced to seven clearly named user-facing sections.
10. Progress polls live project state and refreshes after Agent replies.
11. Free accounts can complete one full project; later stages are not gated.
12. The configured developer account displayed `开发者账户 · 无限制` and
    successfully created a second project.
13. Git initialization created `main` and `.gitignore`; local commit completed
    with zero remaining changes. GitHub repository creation/push code uses a
    transient auth header and never stores credentials in the remote URL.
14. New UI was checked against `DESIGN_SYSTEM.md`; obsolete colors, large
    radii, shadows, and native confirmation prompts were removed from this flow.

Additional release fixes found during this run: server restart recovery now
re-exchanges the persisted JWT instead of looping on an expired in-memory WebSocket
token; session-resume events no longer race page load; HS256 local verification
does not wait for remote JWKS; conversations reset when projects change; and
synchronous Agent final replies return through IPC so they cannot disappear
after a question-card answer.

## GitHub login regression (2026-07-28)

The public login flow was reproduced against `https://kyrozen.chat`. GitHub
authorization completed, but the callback returned `Invalid or expired OAuth
state`. The server kept OAuth state in process memory, so a callback handled by
another worker or a restarted process could not validate it. OAuth state is now
a ten-minute HMAC-signed payload that is independent of worker memory, with a
legacy fallback for requests started immediately before deployment. Logout also
resets a packaged client to its production server instead of retaining a local
test URL, and an interrupted login re-enables the button after 30 seconds.

The rebuilt arm64 DMG was reinstalled and the timeout recovery was verified in
the installed app. Production still returned a legacy 32-character state at the
end of this run, so the backend patch must be deployed before the public login
flow can pass end to end.

## Automated evidence

- OAuth/desktop credential regression tests: **4 passed**.
- Full Python suite: **294 passed, 1 unrelated performance-threshold failure**
  (`/api/chat` mock p95 was 431 ms versus the 200 ms target), plus one
  third-party Starlette deprecation warning.
- Desktop lint: passed with zero warnings.
- Desktop unit tests: **4 passed**, including real local Git commit and remote
  credential-safety tests.
- Renderer/Electron build and both x64/arm64 DMG packaging: passed.

## Remaining release constraint

Apple notarization is still absent. The app can be ad-hoc signed and locally
verified, but Gatekeeper behavior on other Macs cannot be guaranteed without
notarization. Physical ESP32 flashing was not tested because no board was in
scope for this UI repair run.
