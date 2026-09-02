"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { AdaptiveDpr, ContactShadows, PerformanceMonitor, RoundedBox } from "@react-three/drei";
import { Vector3 } from "three";
import * as THREE from "three";
import { Workstation } from "./Workstation";
import { AGENTS, type AgentId, type OfficeModel } from "./office-data";

const SPACING_X = 3.35;
const SPACING_Z = 2.8;

function slotToPos([col, row]: [number, number]): [number, number, number] {
  return [(col - 0.5) * SPACING_X, 0, (row - 0.5) * SPACING_Z];
}

const OVERVIEW = new Vector3(6.8, 4.35, 7.4);
const OVERVIEW_TARGET = new Vector3(0, 0.72, -0.2);

function CameraRig({ selected }: { selected: AgentId | null }) {
  const { camera, pointer } = useThree();
  const target = useRef(OVERVIEW_TARGET.clone());

  const focus = useMemo(() => {
    if (!selected) return { pos: OVERVIEW, tgt: OVERVIEW_TARGET };
    const a = AGENTS.find((x) => x.id === selected)!;
    const [x, , z] = slotToPos(a.slot);
    return {
      pos: new Vector3(x + 2.65, 2.45, z + 3.25),
      tgt: new Vector3(x, 0.78, z),
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
      <fog attach="fog" args={["#dfeaf2", 10, 24]} />
      <hemisphereLight args={["#f8f1f5", "#8d91ad", 1.4]} />
      <directionalLight position={[5, 9, 5]} intensity={2.3} color="#fff8ed" />
      <directionalLight position={[-6, 5, -2]} intensity={0.9} color="#b8c2cc" />
      <spotLight position={[0, 9, 2]} angle={0.72} penumbra={0.9} intensity={80} distance={24} color="#fff6e8" />
      <pointLight position={[-4, 2.8, -3]} intensity={30} distance={17} color="#d9b5d4" />
      <pointLight position={[3.5, 2.2, 4]} intensity={14} distance={12} color="#f4c8b8" />

      <CameraRig selected={selected} />

      {/* gallery-like architecture: concrete plinth, walls and orange identity plane */}
      <RoundedBox args={[10.2, 0.32, 8.6]} radius={0.06} smoothness={3} position={[0, 0.3, 0]} receiveShadow>
        <meshStandardMaterial color="#c9c8d7" roughness={0.72} metalness={0.05} />
      </RoundedBox>
      <mesh position={[0, 0.465, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[10, 8.4]} />
        <meshStandardMaterial color="#e9e4e8" roughness={0.72} metalness={0.03} />
      </mesh>
      <mesh position={[0, 2.05, -4.12]}><boxGeometry args={[10, 3.2, 0.12]} /><meshStandardMaterial color="#d8d5ce" roughness={0.82} /></mesh>
      <mesh position={[-5, 2.05, 0]}><boxGeometry args={[0.12, 3.2, 8.3]} /><meshStandardMaterial color="#bfc0bd" roughness={0.88} /></mesh>
      <mesh position={[2.35, 2.1, -4.02]}><boxGeometry args={[4.1, 2.55, 0.06]} /><meshStandardMaterial color="#eeb4aa" roughness={0.52} emissive="#eeb4aa" emissiveIntensity={0.04} /></mesh>
      <mesh position={[-2.9, 2.2, -4.0]}><boxGeometry args={[2.75, 1.5, 0.07]} /><meshStandardMaterial color="#111110" roughness={0.58} /></mesh>

      {/* ceiling rails / softbox panels */}
      {[-2.7, 0, 2.7].map((x) => (
        <group key={x} position={[x, 3.72, -0.25]}>
          <mesh><boxGeometry args={[0.045, 0.045, 7]} /><meshStandardMaterial color="#111" metalness={0.7} roughness={0.35} /></mesh>
          <mesh position={[0, -0.04, 0.5]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[0.7, 1.8]} /><meshStandardMaterial color="#fff8ed" emissive="#fff8ed" emissiveIntensity={1.1} toneMapped={false} /></mesh>
        </group>
      ))}

      {/* central material table creates a believable shared studio */}
      <RoundedBox args={[1.9, 0.09, 0.9]} radius={0.03} smoothness={3} position={[0, 0.54, 0]}>
        <meshStandardMaterial color="#111110" roughness={0.45} metalness={0.5} />
      </RoundedBox>
      <mesh position={[0, 0.28, 0]}><boxGeometry args={[0.42, 0.5, 0.42]} /><meshStandardMaterial color="#121211" metalness={0.55} roughness={0.45} /></mesh>

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
      camera={{ position: [6.8, 4.35, 7.4], fov: 34, near: 0.1, far: 100 }}
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
