"use client";

import { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox, Html } from "@react-three/drei";
import type { Group, Mesh, MeshStandardMaterial } from "three";
import { MathUtils } from "three";
import { STATE_META, type AgentMeta, type StationState } from "./office-data";

const DESK = "#23242a";
const PEDESTAL = "#191a1e";
const BEZEL = "#0c0d10";
const BODY = "#242834";
const INK = "#f7f8f8";

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
      avatar.current.position.y = 0.62 + Math.sin(t * spd + position[0]) * amp;
      avatar.current.rotation.z = working ? Math.sin(t * 2.2) * 0.03 : 0;
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
      {/* desk */}
      <RoundedBox args={[1.5, 0.09, 0.78]} radius={0.03} smoothness={3} position={[0, 0.5, 0]} castShadow>
        <meshStandardMaterial color={DESK} roughness={0.7} metalness={0.05} transparent opacity={op} />
      </RoundedBox>
      {/* pedestal */}
      <mesh position={[0, 0.25, 0]}>
        <cylinderGeometry args={[0.12, 0.18, 0.5, 16]} />
        <meshStandardMaterial color={PEDESTAL} roughness={0.9} transparent opacity={op} />
      </mesh>

      {/* monitor stand + panel */}
      <mesh position={[0, 0.6, -0.22]}>
        <boxGeometry args={[0.06, 0.16, 0.06]} />
        <meshStandardMaterial color={PEDESTAL} roughness={0.9} transparent opacity={op} />
      </mesh>
      <RoundedBox args={[0.86, 0.5, 0.04]} radius={0.02} smoothness={2} position={[0, 0.86, -0.24]}>
        <meshStandardMaterial color={BEZEL} roughness={0.6} transparent opacity={op} />
      </RoundedBox>
      <mesh ref={screen} position={[0, 0.86, -0.215]}>
        <planeGeometry args={[0.78, 0.42]} />
        <meshStandardMaterial
          color={meta.hex}
          emissive={meta.hex}
          emissiveIntensity={0.3}
          roughness={0.4}
          toneMapped={false}
        />
      </mesh>

      {/* abstract AI worker: capsule body + orb head */}
      <group ref={avatar} position={[0, 0.62, 0.36]}>
        <mesh castShadow>
          <capsuleGeometry args={[0.16, 0.34, 6, 16]} />
          <meshStandardMaterial color={BODY} roughness={0.4} metalness={0.25} transparent opacity={op} />
        </mesh>
        <mesh position={[0, 0.34, 0]} castShadow>
          <sphereGeometry args={[0.13, 24, 24]} />
          <meshStandardMaterial
            color={INK}
            roughness={0.2}
            metalness={0.1}
            emissive={meta.hex}
            emissiveIntensity={working ? 0.22 : 0.06}
            transparent
            opacity={op}
          />
        </mesh>
      </group>

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
