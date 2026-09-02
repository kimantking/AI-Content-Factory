"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { AdaptiveDpr, ContactShadows, PerformanceMonitor, RoundedBox } from "@react-three/drei";
import { Vector3 } from "three";
import * as THREE from "three";
import { Workstation } from "./Workstation";
import { AGENTS, type AgentId, type OfficeModel } from "./office-data";

const SPACING_X = 3.1;
const SPACING_Z = 2.7;

function slotToPos([col, row]: [number, number]): [number, number, number] {
  return [(col - 0.5) * SPACING_X, 0, (row - 0.5) * SPACING_Z];
}

const OVERVIEW = new Vector3(5.6, 4.7, 5.9);
const OVERVIEW_TARGET = new Vector3(0, 0.62, 0);

function CameraRig({ selected }: { selected: AgentId | null }) {
  const { camera, pointer } = useThree();
  const target = useRef(OVERVIEW_TARGET.clone());

  const focus = useMemo(() => {
    if (!selected) return { pos: OVERVIEW, tgt: OVERVIEW_TARGET };
    const a = AGENTS.find((x) => x.id === selected)!;
    const [x, , z] = slotToPos(a.slot);
    return {
      pos: new Vector3(x + 3.0, 3.1, z + 3.6),
      tgt: new Vector3(x, 0.7, z),
    };
  }, [selected]);

  useFrame((_, dt) => {
    // <= ~2deg pointer parallax, disabled while focused
    const par = selected ? 0 : 0.5;
    const desired = focus.pos.clone().add(new Vector3(pointer.x * par, pointer.y * par * 0.4, 0));
    camera.position.lerp(desired, 1 - Math.pow(0.001, dt));
    target.current.lerp(focus.tgt, 1 - Math.pow(0.001, dt));
    camera.lookAt(target.current);
  });
  return null;
}

function Scene({
  model,
  selected,
  setSelected,
  reducedMotion,
  quality,
}: {
  model: OfficeModel;
  selected: AgentId | null;
  setSelected: (id: AgentId | null) => void;
  reducedMotion: boolean;
  quality: "high" | "low";
}) {
  return (
    <>
      <hemisphereLight args={["#565d80", "#0a0a0d", 1.5]} />
      <directionalLight position={[5, 9, 5]} intensity={2.7} color="#f4f5ff" />
      <directionalLight position={[-6, 5, -2]} intensity={1.1} color="#8b93c8" />
      <spotLight position={[0, 10, 1.5]} angle={0.8} penumbra={1} intensity={95} distance={26} color="#ffffff" />
      <pointLight position={[-4, 3, -3]} intensity={42} distance={20} color="#5e6ad2" />
      <pointLight position={[3.5, 2.4, 4]} intensity={20} distance={14} color="#828fff" />

      <CameraRig selected={selected} />

      {/* floor platform */}
      <RoundedBox args={[9.2, 0.4, 8]} radius={0.12} smoothness={3} position={[0, 0.28, 0]} receiveShadow>
        <meshStandardMaterial color="#15161a" roughness={0.92} metalness={0.04} />
      </RoundedBox>
      <mesh position={[0, 0.481, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[9, 7.8]} />
        <meshStandardMaterial color="#1c1d22" roughness={0.85} metalness={0.06} />
      </mesh>

      {AGENTS.map((a) => (
        <Workstation
          key={a.id}
          agent={a}
          state={model.stations[a.id]}
          position={slotToPos(a.slot)}
          focused={selected === a.id}
          dimmed={selected != null && selected !== a.id}
          reducedMotion={reducedMotion}
          onSelect={() => setSelected(selected === a.id ? null : a.id)}
        />
      ))}

      {quality === "high" && (
        <ContactShadows position={[0, 0.49, 0]} scale={11} blur={2.6} opacity={0.45} far={4} frames={reducedMotion ? 1 : 60} />
      )}

      {/* click empty space to deselect */}
      <mesh position={[0, -0.2, 0]} rotation={[-Math.PI / 2, 0, 0]} onClick={() => setSelected(null)}>
        <planeGeometry args={[60, 60]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </>
  );
}

export default function Office3D({
  model,
  selected,
  onSelect,
  reducedMotion,
}: {
  model: OfficeModel;
  selected: AgentId | null;
  onSelect: (id: AgentId | null) => void;
  reducedMotion: boolean;
}) {
  const [quality, setQuality] = useState<"high" | "low">("high");
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const onVis = () => setPaused(document.visibilityState === "hidden");
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const frameloop = paused ? "never" : reducedMotion ? "demand" : "always";

  return (
    <Canvas
      frameloop={frameloop}
      dpr={quality === "high" ? [1, 1.75] : [1, 1]}
      shadows={false}
      gl={{
        antialias: quality === "high",
        alpha: true,
        powerPreference: "high-performance",
        toneMapping: THREE.ACESFilmicToneMapping,
      }}
      camera={{ position: [5.6, 4.7, 5.9], fov: 36, near: 0.1, far: 100 }}
      onPointerMissed={() => onSelect(null)}
      style={{ width: "100%", height: "100%", background: "transparent" }}
    >
      <PerformanceMonitor
        onDecline={() => setQuality("low")}
        onIncline={() => setQuality("high")}
        flipflops={3}
        onFallback={() => setQuality("low")}
      />
      <AdaptiveDpr pixelated />
      <Scene
        model={model}
        selected={selected}
        setSelected={onSelect}
        reducedMotion={reducedMotion}
        quality={quality}
      />
    </Canvas>
  );
}
