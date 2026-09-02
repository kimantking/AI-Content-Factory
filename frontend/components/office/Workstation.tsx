"use client";

import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox, Html } from "@react-three/drei";
import type { Group, Mesh, MeshStandardMaterial } from "three";
import { MathUtils } from "three";
import { STATE_META, type AgentMeta, type StationState } from "./office-data";

const DESK = "#dedbd5";
const PEDESTAL = "#171716";
const BEZEL = "#090909";
const BODY = "#20201f";
const INK = "#d8b39c";

export function Workstation({
  agent,
  state,
  position,
  focused,
  dimmed,
  reducedMotion,
  onSelect,
}: {
  agent: AgentMeta;
  state: StationState;
  position: [number, number, number];
  focused: boolean;
  dimmed: boolean;
  reducedMotion: boolean;
  onSelect: () => void;
}) {
  const group = useRef<Group>(null);
  const avatar = useRef<Group>(null);
  const screen = useRef<Mesh>(null);
  const beacon = useRef<Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const meta = STATE_META[state];
  const working = state === "RUNNING";

  useFrame((s, dt) => {
    if (!group.current) return;
    const t = s.clock.elapsedTime;

    // hover / focus lift
    const targetY = position[1] + (hovered || focused ? 0.06 : 0);
    group.current.position.y = MathUtils.damp(group.current.position.y, targetY, 6, dt);
    const targetScale = focused ? 1.04 : 1;
    const sc = MathUtils.damp(group.current.scale.x, targetScale, 6, dt);
    group.current.scale.setScalar(sc);

    if (!reducedMotion && avatar.current) {
      // subtle breathing; a touch more when working
      const amp = working ? 0.045 : 0.02;
      const spd = working ? 1.6 : 0.9;
      avatar.current.position.y = 0.64 + Math.sin(t * spd + position[0]) * amp;
      avatar.current.rotation.z = working ? Math.sin(t * 2.2) * 0.018 : 0;
    }

    // screen + beacon emissive pulse
    const pulse = working && !reducedMotion ? 0.7 + Math.sin(t * 3) * 0.25 : meta.dim ? 0.32 : 0.6;
    if (screen.current) {
      const m = screen.current.material as MeshStandardMaterial;
      m.emissiveIntensity = MathUtils.damp(m.emissiveIntensity, dimmed ? pulse * 0.3 : pulse, 5, dt);
    }
    if (beacon.current) {
      const m = beacon.current.material as MeshStandardMaterial;
      m.emissiveIntensity = MathUtils.damp(m.emissiveIntensity, dimmed ? 0.4 : working ? 1.6 : 0.9, 5, dt);
    }
  });

  const op = dimmed ? 0.4 : 1;

  return (
    <group
      ref={group}
      position={position}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "";
      }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
    >
      {/* architectural desk: pale stone slab + black steel frame */}
      <RoundedBox args={[1.58, 0.08, 0.82]} radius={0.025} smoothness={3} position={[0, 0.52, 0]} castShadow>
        <meshStandardMaterial color={DESK} roughness={0.58} metalness={0.04} transparent opacity={op} />
      </RoundedBox>
      {[-0.64, 0.64].map((x) => (
        <mesh key={x} position={[x, 0.26, 0]}><boxGeometry args={[0.045, 0.52, 0.62]} /><meshStandardMaterial color={PEDESTAL} roughness={0.45} metalness={0.55} transparent opacity={op} /></mesh>
      ))}

      {/* monitor stand + panel */}
      <mesh position={[0, 0.6, -0.22]}>
        <boxGeometry args={[0.06, 0.16, 0.06]} />
        <meshStandardMaterial color={PEDESTAL} roughness={0.9} transparent opacity={op} />
      </mesh>
      <RoundedBox args={[0.94, 0.54, 0.035]} radius={0.018} smoothness={2} position={[0, 0.88, -0.24]}>
        <meshStandardMaterial color={BEZEL} roughness={0.6} transparent opacity={op} />
      </RoundedBox>
      <mesh ref={screen} position={[0, 0.86, -0.215]}>
        <planeGeometry args={[0.86, 0.46]} />
        <meshStandardMaterial
          color={meta.hex}
          emissive={meta.hex}
          emissiveIntensity={0.3}
          roughness={0.4}
          toneMapped={false}
        />
      </mesh>

      {/* seated studio operator with articulated typing pose */}
      <group ref={avatar} position={[0, 0.64, 0.34]}>
        <mesh position={[0, -0.12, 0.13]} castShadow><boxGeometry args={[0.48, 0.08, 0.42]} /><meshStandardMaterial color="#111110" roughness={0.7} /></mesh>
        <mesh position={[0, 0.08, 0.31]} rotation={[-0.12, 0, 0]} castShadow><boxGeometry args={[0.48, 0.52, 0.09]} /><meshStandardMaterial color="#111110" roughness={0.72} /></mesh>
        <mesh castShadow position={[0, 0.06, 0]} rotation={[0.08, 0, 0]}>
          <capsuleGeometry args={[0.18, 0.34, 8, 20]} />
          <meshStandardMaterial color={BODY} roughness={0.62} transparent opacity={op} />
        </mesh>
        <mesh position={[0, 0.38, -0.01]} castShadow>
          <sphereGeometry args={[0.145, 28, 28]} />
          <meshStandardMaterial
            color={INK}
            roughness={0.2}
            metalness={0.02}
            emissive={meta.hex}
            emissiveIntensity={working ? 0.22 : 0.06}
            transparent
            opacity={op}
          />
        </mesh>
        {/* arms, angled toward keyboard */}
        {[-1, 1].map((side) => (
          <group key={side} position={[side * 0.2, 0.12, -0.05]} rotation={[0.72, 0, side * 0.28]}>
            <mesh><capsuleGeometry args={[0.045, 0.27, 6, 12]} /><meshStandardMaterial color={BODY} roughness={0.62} /></mesh>
            <mesh position={[0, -0.18, 0]}><sphereGeometry args={[0.055, 14, 14]} /><meshStandardMaterial color={INK} roughness={0.48} /></mesh>
          </group>
        ))}
      </group>

      {/* keyboard and desk lamp add readable workplace detail */}
      <mesh position={[0, 0.57, 0.12]} rotation={[-0.18, 0, 0]}><boxGeometry args={[0.5, 0.025, 0.16]} /><meshStandardMaterial color="#151514" roughness={0.55} /></mesh>
      <mesh position={[0.62, 0.72, -0.08]} rotation={[0, 0, -0.42]}><cylinderGeometry args={[0.018, 0.018, 0.35, 10]} /><meshStandardMaterial color="#151514" metalness={0.6} /></mesh>
      <mesh position={[0.51, 0.87, -0.08]} rotation={[0, 0, -0.42]}><coneGeometry args={[0.11, 0.18, 18]} /><meshStandardMaterial color={meta.hex} emissive={meta.hex} emissiveIntensity={working ? 0.55 : 0.12} /></mesh>

      {/* status beacon */}
      <mesh ref={beacon} position={[0.66, 0.62, 0.3]}>
        <sphereGeometry args={[0.035, 16, 16]} />
        <meshStandardMaterial color={meta.hex} emissive={meta.hex} emissiveIntensity={0.9} toneMapped={false} />
      </mesh>

      {/* label */}
      <Html position={[0, 0.14, 0.42]} center distanceFactor={8} occlude={false} pointerEvents="none">
        <div
          style={{
            fontFamily: "var(--font-text)",
            fontSize: 12,
            fontWeight: 500,
            color: dimmed ? "#62666d" : "#f7f8f8",
            whiteSpace: "nowrap",
            textAlign: "center",
            opacity: op,
          }}
        >
          {agent.name}
          <span style={{ display: "block", fontSize: 10, color: meta.hex, fontWeight: 600 }}>{meta.ko}</span>
        </div>
      </Html>
    </group>
  );
}
