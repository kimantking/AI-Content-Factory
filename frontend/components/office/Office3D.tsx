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

function CloudWindow() {
  const clouds = [
    [-3.7, 1.45, 0.72], [-2.85, 1.6, 0.95], [-1.8, 1.42, 0.66],
    [0.1, 1.55, 0.82], [1.2, 1.38, 0.62], [2.35, 1.58, 0.92], [3.45, 1.4, 0.7],
  ] as const;

  return (
    <group position={[0, 0, -4.1]}>
      {/* softly glowing sky beyond the glass */}
      <mesh position={[0, 2.2, -0.12]}>
        <planeGeometry args={[9.5, 3.1]} />
        <meshBasicMaterial color="#cfe9f4" toneMapped={false} />
      </mesh>
      <mesh position={[0, 1.25, -0.1]}>
        <planeGeometry args={[9.5, 1.2]} />
        <meshBasicMaterial color="#f7dfdc" transparent opacity={0.82} toneMapped={false} />
      </mesh>
      {clouds.map(([x, y, scale], index) => (
        <group key={index} position={[x, y, -0.02]} scale={[scale * 1.5, scale * 0.58, scale * 0.4]}>
          <mesh><sphereGeometry args={[0.5, 18, 12]} /><meshBasicMaterial color={index % 2 ? "#fff4f2" : "#eee5f4"} /></mesh>
          <mesh position={[0.45, 0.05, 0]}><sphereGeometry args={[0.38, 18, 12]} /><meshBasicMaterial color="#f8edf1" /></mesh>
          <mesh position={[-0.42, -0.04, 0]}><sphereGeometry args={[0.34, 18, 12]} /><meshBasicMaterial color="#f3e8f4" /></mesh>
        </group>
      ))}

      {/* architectural frame and lightly reflective glazing */}
      <mesh position={[0, 3.6, 0.08]}><boxGeometry args={[10, 0.28, 0.18]} /><meshStandardMaterial color="#e8e4e6" roughness={0.7} /></mesh>
      <mesh position={[0, 0.62, 0.08]}><boxGeometry args={[10, 0.32, 0.22]} /><meshStandardMaterial color="#d7d3d8" roughness={0.65} /></mesh>
      {[-4.85, -2.45, 0, 2.45, 4.85].map((x) => (
        <mesh key={x} position={[x, 2.1, 0.1]}><boxGeometry args={[0.1, 2.78, 0.16]} /><meshStandardMaterial color="#9698a8" metalness={0.55} roughness={0.28} /></mesh>
      ))}
      <mesh position={[0, 2.1, 0.14]}>
        <planeGeometry args={[9.7, 2.7]} />
        <meshPhysicalMaterial color="#ddecf3" transparent opacity={0.12} roughness={0.08} metalness={0.08} transmission={0.45} depthWrite={false} />
      </mesh>
    </group>
  );
}

function SideWindow() {
  return (
    <group position={[-5.02, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
      <mesh position={[0, 2.2, -0.12]}><planeGeometry args={[8.2, 3.1]} /><meshBasicMaterial color="#c9e5f1" side={THREE.DoubleSide} toneMapped={false} /></mesh>
      <mesh position={[0, 1.2, -0.1]}><planeGeometry args={[8.2, 1.05]} /><meshBasicMaterial color="#f4cadb" side={THREE.DoubleSide} toneMapped={false} /></mesh>
      <mesh position={[0, 3.6, 0.08]}><boxGeometry args={[8.4, 0.28, 0.18]} /><meshStandardMaterial color="#e8dfe4" roughness={0.55} /></mesh>
      <mesh position={[0, 0.62, 0.08]}><boxGeometry args={[8.4, 0.32, 0.22]} /><meshStandardMaterial color="#d4c7ce" roughness={0.55} /></mesh>
      {[-4.1, -2.05, 0, 2.05, 4.1].map((z) => (
        <mesh key={z} position={[z, 2.1, 0.1]}><boxGeometry args={[0.1, 2.78, 0.16]} /><meshStandardMaterial color="#8b8d98" metalness={0.68} roughness={0.2} /></mesh>
      ))}
      <mesh position={[0, 2.1, 0.14]}><planeGeometry args={[8.2, 2.7]} /><meshPhysicalMaterial color="#e7f5fa" transparent opacity={0.1} roughness={0.04} transmission={0.58} depthWrite={false} side={THREE.DoubleSide} /></mesh>
    </group>
  );
}

function Planter({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.3, 0]}><cylinderGeometry args={[0.34, 0.28, 0.6, 20]} /><meshStandardMaterial color="#f0d1c8" roughness={0.72} /></mesh>
      <mesh position={[0, 0.83, 0]}><cylinderGeometry args={[0.055, 0.07, 0.75, 10]} /><meshStandardMaterial color="#6e806f" roughness={0.85} /></mesh>
      {[-0.28, 0, 0.28].map((x, index) => (
        <mesh key={x} position={[x, 1.05 + index * 0.08, 0]} rotation={[0, 0, x * 1.2]}>
          <sphereGeometry args={[0.3, 16, 12]} />
          <meshStandardMaterial color={index === 1 ? "#91a58f" : "#7e987f"} roughness={0.9} />
        </mesh>
      ))}
    </group>
  );
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
      <fog attach="fog" args={["#eadce4", 14, 30]} />
      <hemisphereLight args={["#f8f1f5", "#8d91ad", 1.4]} />
      <directionalLight position={[5, 9, 5]} intensity={2.6} color="#fff8f4" />
      <directionalLight position={[-6, 5, -2]} intensity={0.9} color="#b8c2cc" />
      <spotLight position={[0, 9, 2]} angle={0.72} penumbra={0.9} intensity={80} distance={24} color="#fff6e8" />
      <pointLight position={[-4, 2.8, -3]} intensity={34} distance={17} color="#efb8d2" />
      <pointLight position={[3.5, 2.2, 4]} intensity={18} distance={12} color="#f6c4dc" />

      <CameraRig selected={selected} />

      {/* airy pastel studio architecture */}
      <RoundedBox args={[10.2, 0.32, 8.6]} radius={0.06} smoothness={3} position={[0, 0.3, 0]} receiveShadow>
        <meshStandardMaterial color="#c9c8d7" roughness={0.72} metalness={0.05} />
      </RoundedBox>
      <mesh position={[0, 0.465, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[10, 8.4]} />
        <meshPhysicalMaterial color="#eee7eb" roughness={0.2} metalness={0.08} clearcoat={0.72} clearcoatRoughness={0.18} />
      </mesh>
      <CloudWindow />
      <SideWindow />

      {/* photo-inspired ceiling, warm cove lighting and concrete core */}
      <mesh position={[0, 3.92, 0]}><boxGeometry args={[10.2, 0.18, 8.6]} /><meshStandardMaterial color="#ded7da" roughness={0.7} /></mesh>
      {[-3.15, 0, 3.15].map((x) => (
        <mesh key={x} position={[x, 3.8, 0.35]} rotation={[Math.PI / 2, 0, 0]}><planeGeometry args={[1.65, 0.78]} /><meshBasicMaterial color="#fff6f8" toneMapped={false} /></mesh>
      ))}
      <pointLight position={[0, 3.65, 0.35]} intensity={24} distance={9} color="#ffd4e5" />
      <mesh position={[0.1, 2.18, -2.85]}><cylinderGeometry args={[0.62, 0.7, 3.35, 40]} /><meshStandardMaterial color="#a9a2a5" roughness={0.88} metalness={0.02} /></mesh>
      <mesh position={[0.1, 2.18, -2.85]}><cylinderGeometry args={[0.64, 0.72, 3.36, 40]} /><meshStandardMaterial color="#c7bfc3" transparent opacity={0.24} roughness={1} /></mesh>

      {/* broad sunlight reflections sell the high-rise glass-room feeling */}
      {[[-2.7, -1.45, -0.22], [0.15, -1.15, 0.12], [2.75, -1.3, -0.18]].map(([x, z, r], index) => (
        <mesh key={index} position={[x, 0.49, z]} rotation={[-Math.PI / 2, 0, r]}><planeGeometry args={[1.25, 2.15]} /><meshBasicMaterial color="#fff3f8" transparent opacity={0.24} depthWrite={false} /></mesh>
      ))}

      {/* soft furnishings and greenery keep the room from feeling like a closed set */}
      <mesh position={[0, 0.485, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[2.2, 48]} /><meshStandardMaterial color="#e8bfd2" roughness={0.96} /></mesh>
      <Planter position={[-4.3, 0.5, -3.2]} />
      <Planter position={[4.25, 0.5, -3.25]} />

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
