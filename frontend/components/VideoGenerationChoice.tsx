"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

export default function VideoGenerationChoice({ mode, onMode, plan, onPlan }: {
  mode: "IMAGE_MOTION" | "VEO";
  onMode: (mode: "IMAGE_MOTION" | "VEO") => void;
  plan: "PREVIEW" | "THREE_SCENES";
  onPlan: (plan: "PREVIEW" | "THREE_SCENES") => void;
}) {
  const [options, setOptions] = useState<{ media_budget: number; campaign_budget: number; model: string; cost_per_scene: number | null } | null>(null);
  useEffect(() => {
    fetch(`${API_BASE}/api/video-generation-options`).then(r => r.ok ? r.json() : Promise.reject())
      .then(setOptions).catch(() => setOptions(null));
  }, []);
  const count = plan === "PREVIEW" ? 1 : 3;
  const estimate = options?.cost_per_scene == null ? null : count * options.cost_per_scene;
  const overBudget = estimate !== null && options &&
    ((options.media_budget >= 0 && estimate > options.media_budget) || (options.campaign_budget >= 0 && estimate > options.campaign_budget));
  return <fieldset className="mb-4 min-w-0">
    <legend className="mb-2 text-sm font-bold">영상 제작 방식</legend>
    <div className="grid gap-2 sm:grid-cols-2">
      {([
        ["IMAGE_MOTION", "이미지 모션", "정지 이미지에 줌·이동 효과를 넣습니다."],
        ["VEO", "실제 움직이는 영상 · Veo", "인물의 동작과 배경의 움직임을 생성합니다."],
      ] as const).map(([value, title, description]) => <label key={value}
        className={`cursor-pointer rounded-lg border p-3 ${mode === value ? "border-primary bg-primary/5" : "border-hairline"}`}>
        <span className="flex items-center gap-2 text-sm font-bold"><input type="radio" name="video-mode"
          value={value} checked={mode === value} onChange={() => onMode(value)} />{title}</span>
        <span className="mt-1 block text-xs">{description}</span>
      </label>)}
    </div>
    <p className="mt-2 text-xs">두 방식 모두 음성과 한국어 자막을 합쳐 MP4로 제작합니다.</p>
    {mode === "VEO" && <div className="mt-3 rounded-lg border border-hairline p-3">
      <label htmlFor="veo-plan" className="text-sm font-bold">이번 작업의 Veo 생성 범위</label>
      <select id="veo-plan" value={plan} onChange={e => onPlan(e.target.value as typeof plan)}
        className="mt-2 block w-full rounded border border-hairline bg-surface-1 p-2 text-sm">
        <option value="PREVIEW">1장면 체험 · Veo 한도 $3.50</option>
        <option value="THREE_SCENES">최대 3장면 · Veo 한도 $10</option>
      </select>
      <p className="mt-2 text-xs">전체 작업에서 앞쪽 최대 {plan === "PREVIEW" ? "1" : "3"}개 장면을 Veo로 만들고, 나머지는 이미지 모션으로 제작합니다. 장면당 8초를 생성한 뒤 대사 길이에 맞춰 편집합니다.</p>
      <p className="mt-2 text-xs">{estimate === null ? "현재 모델의 예상 비용은 확인이 필요합니다." : `Veo 예상 비용 $${estimate.toFixed(2)} (${options?.model}).`} 이미지·음성 비용은 별도입니다. 기존 작업·미디어·일일·월간 한도도 함께 적용됩니다.</p>
      {options && <p className="mt-2 text-xs">현재 미디어 한도: {options.media_budget < 0 ? "무제한" : `$${options.media_budget.toFixed(2)}`} / 작업 한도: {options.campaign_budget < 0 ? "무제한" : `$${options.campaign_budget.toFixed(2)}`}</p>}
      {overBudget && <p role="alert" className="mt-2 text-sm font-bold">선택한 생성량이 현재 예산을 초과합니다. 이 상태에서는 제작을 시작할 수 없습니다. 이미지 모션을 선택하거나 예산 설정을 확인하세요.</p>}
      <p className="mt-2 text-xs">선택만으로는 결제되지 않습니다. 제작 시작 시 유료 생성을 요청합니다.</p>
    </div>}
  </fieldset>;
}
