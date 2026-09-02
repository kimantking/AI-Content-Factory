# RESPONSIVE DESIGN (V3)

Principle (from the "Dashboards Layout Ideas" study): **mobile is a
re-composition, not a scale-down.** At each breakpoint we re-decide information
priority, navigation, 3D presence, panel layout, form layout, action placement.

## Breakpoints (verified in real browser)

| Name | Width | Layout decisions |
|---|---|---|
| Desktop XL | 1440 | NavigationRail (icon, hover-expand) + transparent CommandBar. Full-bleed 3D studio band (~520px). Glass CommandComposer above it. Priority = 3-col grid. Agent Inspector = right glass drawer. |
| Desktop | 1280 | Same; grids hold 3-up; studio ~500px. |
| Laptop / tablet-landscape | 1024 | Rail stays icon-only. Studio kept, `quality="low"` (DPR 1, contact-shadows off). Priority = 2-col. Composer full width. |
| Tablet | 768 | Rail -> hidden; content full width. 3D still on but reduced. Card grid 2-up -> priority stack. Filters -> inline row. |
| Mobile L | 430 | BottomNav (홈/콘텐츠/+/검수/더보기). **No WebGL** -> `OfficeFallback` 2.5D grid. Composer full width; platform/goal chips wrap; advanced = accordion. |
| Mobile | 390 | Same as 430. Priority stack: Composer -> 현재 작업 -> 검수 필요 -> Mini office -> 최근 콘텐츠 -> 알림. Analytics last. Headline scales `text-[21px]`. |
| Mobile S | 375 | Same; verify no horizontal scroll; touch targets >= 44px (BottomNav 54px). |

## Navigation transformation

- Desktop/laptop: left **NavigationRail** (icon, active = lavender). Toggle to labelled 236px (persisted).
- Tablet: rail hidden; primary nav via CommandBar + Cmd-K palette + BottomNav appears < 768.
- Mobile: **BottomNav** 5 slots, centre "+" = 만들기; overflow in "더보기" bottom sheet.

## 3D presence by device

| Device | 3D |
|---|---|
| >= 768 + WebGL + not reduced-motion | full R3F studio, `PerformanceMonitor` auto-tiers DPR 1.75 -> 1 -> pause |
| >= 768 + reduced-motion | R3F studio, `frameloop="demand"`, no idle motion, instant camera |
| < 768 or no WebGL | `OfficeFallback` - 2.5D CSS grid, same 4 stations, same real-state colours, tappable |

## Progressive disclosure

Anything not top-priority is behind accordion / tab / drawer / bottom-sheet -
never hidden unconditionally, never all shown at once. Composer advanced options,
library filters (mobile -> full-screen overlay), agent detail (drawer).

## Layout mechanics

CSS Grid for scaffolding, Flexbox for component alignment. Intrinsic sizing
(`min-w-0`, `flex-1`, `minmax`, `clamp` where useful). No fixed pixel
width/height on content containers; the 3D stage is the only fixed-height band
and it is responsive (`h-[360px] sm:h-[440px] lg:h-[520px]`).
