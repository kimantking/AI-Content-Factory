# 3D WEB REFERENCE AUDIT

> Pre-implementation research for the "AI CONTENT FACTORY 3D OPERATIONS OFFICE" concept.
> Date: 2026-09-02. No code written yet. All findings verified against official sources
> (pmndrs docs, three.js forum, Spline docs, studio sites) as of Sept 2026.

## 0. Context / constraints carried in

- Frontend: **Next.js 15.5.24 / React 19.0.0 / TypeScript / Tailwind 3.4**, standalone Docker (`node server.js`).
- Current bundle: **~103 kB First Load JS shared**, per-route 104-118 kB. Zero runtime deps beyond framework.
- The 2D design system (`DESIGN.md` Linear near-black tokens, `components/ui/*`, dark+light) stays as the shell. 3D is additive on Home / ops screens only.
- Hard rules from brief: no backend changes, no fake agent state, honest perf numbers, lazy 3D load, `prefers-reduced-motion`, real mobile fallback, Korean-first UI, real browser test, STOP after MVP.

---

## 1. Source-by-source audit

### A. Spline

| Field | Finding |
|---|---|
| Reference | spline.design, `@splinetool/react-spline` (+ `/next` entry), Spline Viewer web component, Spline Community |
| Technique | Visual 3D scene authoring in-browser; export as hosted `.splinecode` runtime or `<spline-viewer>`. `@splinetool/react-spline/next` renders an auto-generated blurred placeholder (SSR) and lazy-hydrates. Default **render-on-demand** (frames only on scene change). Pointer/scroll/variable events exposed to JS via `onSplineMouseDown` / `spline.emitEvent` / `spline.setVariable`. |
| Why useful | Fastest path to a polished, art-directed room with lighting/materials baked; no GLSL. Good for a single hero scene. |
| Performance cost | Runtime `@splinetool/runtime` ~**0.8-1.2 MB JS** + the `.splinecode` scene payload (**commonly 1-8 MB**, textures dominate). Scene is fetched from Spline's CDN unless self-hosted. Weak fine-grained control over draw calls / LOD. Heavier floor than hand-built R3F for the same complexity. |
| Mobile suitability | Viewer downscales, but no true capability tiering; large scenes stutter on mid-range phones. Needs an explicit static fallback. |
| License | **Community scenes: CC0 1.0** (commercial OK, remix OK, no attribution). Runtime lib: MIT. Self-authored scenes: yours. |
| Verdict | **Reference only.** Great for mood/lighting study and as a possible later hero. Rejected as the MVP engine: opaque payload weight, CDN dependency, and weak per-frame control conflict with the perf budget and "wired to real state" requirement. |

### B. React Three Fiber (`@react-three/fiber`)

| Field | Finding |
|---|---|
| Reference | `pmndrs/react-three-fiber`, official docs `r3f.docs.pmnd.rs`, Examples/Showcase |
| Technique | Declarative React renderer over three.js. Scene = JSX. `<Canvas frameloop="demand">` for on-demand rendering; `invalidate()` to request a frame; `useFrame` for per-frame logic; `performance.regress()` for movement regression; `<Suspense>` for progressive load. |
| Why useful | State-driven scene graph = **agent job status maps directly to props** (position, material, animation) with no imperative glue. React 19 compatible. Full control over draw calls, LOD, DPR, effects. Composes with the existing 2D React tree (overlay UI stays normal DOM). |
| Performance cost | `@react-three/fiber@9` is small (~10 kB) but `<Canvas>` pulls **three.js (~155 kB gzip, poor tree-shaking)**. Realistic add for fiber+three: **~170-190 kB gzip**. Fully controllable at runtime (frameloop, DPR, culling). |
| Mobile suitability | Excellent with `PerformanceMonitor` + adaptive DPR + `frameloop="demand"`; can drop to a 2.5D or static path per device. |
| License | **MIT.** |
| Verdict | **Use (core engine).** `@react-three/fiber@9` pinned for React 19. |

### C. Drei (`@react-three/drei`)

| Field | Finding |
|---|---|
| Reference | `pmndrs/drei`, current **10.7.x**, depends on R3F v9 (React 19 path). |
| Technique | Helper components. Relevant here: `PerformanceMonitor` (fps-driven quality tiering via `onDecline`/`onIncline`), `AdaptiveDpr`, `AdaptiveEvents`, `BakeShadows`, `Instances`/`Instance` (draw-call merge), `Detailed` (LOD), `Environment` (IBL, can use bundled presets - no network), `SoftShadows`/`ContactShadows`/`AccumulativeShadows`, `MeshTransmissionMaterial` (glass), `Float`, `Sparkles`, `Html` (DOM anchored to 3D), `Bounds`/`CameraControls` (smooth focus), `PresentationControls` (clamped orbit), `Preload`. |
| Why useful | `PerformanceMonitor`, `Instances`, `AdaptiveDpr`, `CameraControls`, `Html` cover ~90% of the MVP without custom plumbing. `Html` lets the click-panel live in normal DOM anchored to a workstation. |
| Performance cost | Tree-shakeable per-import. A **curated subset (~8-10 components)** adds roughly **40-90 kB gzip**. `MeshTransmissionMaterial` and heavy shadow bakers are the expensive ones - use sparingly. |
| Mobile suitability | `PerformanceMonitor` + `AdaptiveDpr` + `AdaptiveEvents` are the mobile strategy. |
| License | **MIT.** |
| Verdict | **Use (curated subset only).** Import individual components, never `import * from`. |

### D. three.js

| Field | Finding |
|---|---|
| Reference | `threejs.org` examples (lighting, materials, `EffectComposer` post, `InstancedMesh`, `GLTFLoader` + Draco/KTX2, `LOD`). |
| Technique | The engine under R3F. Examples inform: 3-point studio lighting, `MeshStandardMaterial`/`MeshPhysicalMaterial`, `ACESFilmicToneMapping`, `PMREMGenerator` env, `InstancedMesh`, `LOD`. |
| Why useful | Reference for lighting rig and material setup; consumed through R3F, not directly. |
| Performance cost | **~155 kB gzip**, tree-shaking is limited (known: importing `Canvas` bundles most of three). This is the single biggest line item. |
| Mobile suitability | Fine if DPR capped (<=1.5), antialias off on mobile, shadows baked/soft-limited. |
| License | **MIT.** |
| Verdict | **Use (transitive, via R3F).** Pin one version; align with R3F v9's peer range. |

### E. GitHub 3D projects (maintained, R3F/three/Next)

| Repo | Technique | Why useful | Perf | Mobile | License | Verdict |
|---|---|---|---|---|---|---|
| `pmndrs/examples` + R3F Showcase | Canonical patterns: transmission, portals, scroll, instancing, post-processing, camera rigs | Authoritative pattern source | n/a | varies | MIT | **Reference** |
| "AI Office" isometric scene (React 19 + three.js, 9 AI agents that walk/talk/meet) | Isometric office, per-agent state, camera framing | Closest conceptual match to the "3D Operations Office" | unknown, likely heavy (animated characters) | unknown | check per-repo | **Reference only** - study composition/camera, do not lift assets or code |
| `Sandrafongshurui/3dDashboard` | three + three-fiber dashboard | Layout of data UI over a 3D stage | small | unknown | check | **Reference** |
| `AndyLow14/Tiny-Room` | Isometric voxel rooms in R3F | Miniature-room framing, lighting on primitives | light (primitives) | ok | check | **Reference** - validates the "procedural primitives, no GLB" path |
| `pmndrs/react-three-fiber` docs `advanced/scaling-performance` | frameloop=demand, `invalidate`, `InstancedMesh`, `Detailed`, `PerformanceMonitor`, adaptive DPR, `performance.regress()` | The performance playbook we will implement | n/a | n/a | MIT | **Use (as method)** |
| `tsogjavklann/awwwards-3d` (Claude skill, three r170 + GSAP + Lenis) | Scroll-driven premium scene recipe | Confirms the premium stack; **not installed here** | n/a | n/a | check | **Reference** |

### F. Premium studio references (analysis, not copy)

| Studio | Camera language | Motion | Depth / material | UI overlay | Loading | Perf / mobile |
|---|---|---|---|---|---|---|
| **Lusion** | Slow, deliberate dollies; subject stays centered; parallax on pointer is tiny (<2 deg) | Spring physics, nothing linear; transitions are single strong moves | Transmissive glass, precise color grading, shallow DOF as focus tool | Minimal type over the scene, high contrast, generous margins | Branded hold, then one reveal move | EffectComposer used surgically; mobile gets reduced effects |
| **Active Theory** | Game-engine framing, purposeful cuts | GLSL distortion, hand-tuned bloom/dispersion | Custom shaders, layered lighting | Type cut into / masked by the scene | Sequenced reveal | "Game engine on the web" - aggressive LOD + custom pipelines |
| **Studio Freight** | Static or very gentle; scroll does the work | Lenis smoothing, restraint | Minimal, one material story | Editorial, lots of whitespace | Fast, near-instant | Lightweight; smoothness over spectacle |
| **14islands / Resn** | Contained scenes, controlled orbit | Motivated, never idle-jitter | Soft studio lighting, ambient IBL | Panels beside the scene, not floating randomly | Skeleton then scene | Progressive enhancement |

**Extracted principles for ACF (not visual copy):**
1. Camera = slow, motivated, subject-centered. Pointer parallax <= ~2 degrees. Click = one smooth focus move; back = one move to overview. No idle jitter, no mouse-tracked wobble.
2. One material story: matte surfaces + one accent glow (Linear lavender `#5e6ad2`) + one glass element max. No neon stack.
3. Post-processing is surgical: at most tone mapping + a restrained bloom. Never the full stack.
4. UI overlay is editorial and legible - the existing 2D `PageHeader`/`Card`/composer sit over/beside the scene, not floating chaotically.
5. Loading: 2D shell + critical data first, then the scene fades in. The scene never blocks first paint.
6. Mobile is a different design, not a shrink: static premium render or 2.5D, full feature parity in the 2D layer.

---

## 2. Technical decision

### Options

| | OPTION A - Spline-centric | OPTION B - R3F-centric | OPTION C - Hybrid |
|---|---|---|---|
| Engine | `@splinetool/react-spline/next` | `@react-three/fiber` + `drei` + `three` | R3F for the 3D stage; existing Next.js 2D components for all data UI; CSS/Motion for 2D transitions |
| State wiring | Emit events / set variables into a black-box scene | Job status -> React props -> scene graph | Same as B |
| Added weight (gzip) | ~1-1.5 MB runtime + 1-8 MB scene | ~250-350 MB... **~250-350 kB** (three+fiber+curated drei), procedural geometry = ~0 asset bytes | Same as B |
| Runtime control | Low | High (frameloop, DPR, LOD, culling, effects) | High |
| CDN dependency | Yes (scene) unless self-hosted | No | No |
| Art pipeline | Author in Spline (not possible in this env) or remix CC0 (needs Spline app) | Procedural primitives in code, or GLB assets | Procedural primitives in code |
| Fit to "wired to real state" + perf budget + no-cheap-assets | Weak | Strong | **Strongest** |

### Selected: **OPTION C - Hybrid**, engine = **React Three Fiber + curated Drei**, geometry = **fully procedural (no GLB, no external assets)**.

**Reasoning**
- The office must reflect **real `Campaign`/`Job` state** with no fake animation. R3F's state-driven graph makes `job.status -> workstation visual` a pure prop mapping; Spline would need imperative event glue into an opaque scene.
- **No cheap assets / unified art direction / no template**: procedural geometry (extruded desks, capsule/orb "AI worker" avatars, panel meshes, soft area lights) is authored entirely in code - zero license risk, zero asset MB, one consistent art direction, trivially themeable to the `DESIGN.md` palette. This is the "abstract AI worker / low-poly premium" path the brief explicitly allows, and `AndyLow14/Tiny-Room` proves primitives can look premium with good lighting.
- **Perf budget**: three.js (~155 kB) is the unavoidable cost of any real WebGL path; Spline is strictly heavier. With `frameloop="demand"` (a mostly-static office), `PerformanceMonitor` + `AdaptiveDpr`, `Instances`, capped DPR, and lazy init behind the 2D shell, the scene runs cheap. Target: **First Load JS for `/` stays <= ~140 kB** (3D chunk lazy-loaded, not in the initial bundle), 60 fps desktop / >=30 fps mid mobile or auto-fallback.
- **2D stays 2D**: Library, tables, settings, analytics detail, forms, prompt editor keep the current components untouched. Only Home (and later Autopilot / Current Pipeline / System overview) get the 3D stage.

### Dependencies to add (pending approval - brief requires review before install)

| Package | Version target | gzip (approx) | License | Why |
|---|---|---|---|---|
| `three` | pinned to R3F v9 peer range (three 0.17x) | ~155 kB | MIT | engine |
| `@react-three/fiber` | `^9` (React 19) | ~10 kB | MIT | renderer |
| `@react-three/drei` | `^10` | ~40-90 kB (curated imports only) | MIT | PerformanceMonitor, AdaptiveDpr, Instances, CameraControls, Html, Environment, ContactShadows |
| `@types/three` (dev) | match `three` | 0 (dev) | MIT | types |

**Not adding**: `@react-three/postprocessing` (evaluate later; MVP uses R3F/three tone mapping + at most a cheap bloom via drei if it fits budget), GSAP (not justified for the MVP; drei `CameraControls` + `useFrame` lerp covers camera; existing CSS/Motion covers 2D), Lenis, any GLB loader / Draco / KTX2 (no external models in MVP), Spline runtime.

All 3D code isolated under `frontend/components/office/` and dynamically imported (`next/dynamic`, `ssr: false`) so the WebGL chunk never touches the initial payload or non-3D routes.

---

## 3. MVP scope (Home only)

- **2D shell first**: existing `AppShell` + top command bar + Quick Create composer + priority cards render immediately with real data. Unchanged.
- **3D stage** occupies the hero area (desktop ~60-65% width, or a full-bleed band behind a minimal overlay), lazy-mounted after first paint.
- **4 workstations**: 리서치 에이전트 (Research), 대본 에이전트 (Script), 영상 에이전트 (Video), 게시 에이전트 (Publishing). Procedural desk + monitor + abstract avatar + area light per station.
- **Real state**: each station reads from `supportSnapshot()` pipeline + `getCampaign()` for the focused job. States: 대기 / 작업 중 / 주의 / 오류 / 완료 -> subtle per-station signal (monitor emissive, avatar idle vs. working motion, small beacon). No state the backend does not report.
- **Interaction**: clamped orbit (`PresentationControls` or `CameraControls` with limits) + <=2 deg pointer parallax; hover highlight; click a station -> `drei/Html` or existing side panel with agent name/role/current job/campaign/stage/model/provider/progress/elapsed/cost + actions 작업 보기 / 로그 보기 / 관련 콘텐츠. Click empty space or "뒤로" -> smooth return to overview.
- **Camera**: isometric-ish overview, one smooth focus move on select, one move back. No vertigo.
- **Perf**: `frameloop="demand"`, `PerformanceMonitor` tiering (DPR 1.5 -> 1 -> pause), `AdaptiveDpr`, `Instances` for repeated geometry, `BakeShadows`/`ContactShadows` not dynamic shadow maps.
- **Mobile (390x844)**: no WebGL office. A static premium render (pre-captured `<img>`) or a flat 2.5D CSS diagram of the 4 stations with the same state colors; Quick Create / 작업 현황 / Agent status / Review fully usable in 2D.
- **Reduced motion**: `prefers-reduced-motion` -> scene renders one static frame, no idle motion, camera moves become instant.

## 4. Measurement plan (report real numbers)

Before vs. after, recorded from a real build + real browser (agent-browser, 1440x900 and 390x844):
- `next build` First Load JS for `/` and shared.
- Scene chunk size (separate lazy chunk).
- FPS at overview and during a focus move (desktop; mid-tier mobile emulation).
- JS heap after scene mount.
- Time to first paint of the 2D shell (must be unchanged).
- Draw calls / triangles (drei `PerformanceMonitor` / r3f-perf during dev only).

## 5. Risks

- three.js weight is fixed (~155 kB); mitigated by lazy chunk + it never loads on non-3D routes or mobile.
- Next 15 + R3F v9 + React 19 had reported edge cases (`ReactCurrentOwner`); mitigation: latest `@react-three/fiber@9` + `@react-three/drei@10`, `ssr:false` dynamic import, verify on a throwaway route before wiring Home.
- Docker standalone build must still succeed with the new deps (no native addons in this set - all pure JS/WASM-free, low risk).
- "Premium not game-y" is a craft bar, not a checkbox - depends on lighting + restraint; procedural path is judged in-browser, iterated.

## 6. Recommendation to proceed

1. Install the 4 packages above (pinned).
2. Build the Home 3D Office MVP per section 3, isolated + lazy.
3. Real browser + perf + mobile test, honest numbers.
4. Korean final report, then STOP (no API keys / OAuth / publishing).
