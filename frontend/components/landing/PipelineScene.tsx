"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Environment, Lightformer } from "@react-three/drei";
import { MathUtils, type Group } from "three";
import * as THREE from "three";

/**
 * Studio product-render: smooth achromatic capsules + rings drifting along the X
 * axis (content flowing through the line). Glossy black, 3-point softbox, soft
 * contact shadow. Sits on the same off-white as the page so only the objects
 * read. No neon, no glow, no post-processing.
 */

const COUNT = 7;
const SPAN = 9; // x travel before wrap
const SPEED = 0.9;

function Line({ reduced }: { reduced: boolean }) {
  const group = useRef<Group>(null);
  const { pointer } = useThree();

  const items = useMemo(
    () =>
      Array.from({ length: COUNT }).map((_, i) => ({
        x: -SPAN / 2 + (i / COUNT) * SPAN,
        y: (i % 3) * 0.5 - 0.5,
        z: ((i * 37) % 7) / 7 - 0.5,
        ring: i % 3 === 1,
        s: 0.7 + ((i * 53) % 5) / 12,
      })),
    [],
  );

  useFrame((state, dt) => {
    if (!group.current) return;
    // inertial rotation toward pointer, damping ~0.06
    const ry = reduced ? 0 : MathUtils.clamp(pointer.x, -1, 1) * 0.14;
    const rx = reduced ? 0 : MathUtils.clamp(pointer.y, -1, 1) * -0.06;
    group.current.rotation.y = MathUtils.damp(group.current.rotation.y, ry, 6, dt);
    group.current.rotation.x = MathUtils.damp(group.current.rotation.x, rx, 6, dt);

    if (reduced) return;
    group.current.children.forEach((c) => {
      c.position.x += SPEED * dt;
      if (c.position.x > SPAN / 2) c.position.x -= SPAN;
      c.rotation.z += dt * 0.4;
    });
  });

  return (
    <group ref={group}>
      {items.map((it, i) => (
        <mesh key={i} position={[it.x, it.y, it.z]} rotation={[0, 0, i * 0.7]} scale={it.s}>
          {it.ring ? (
            <torusGeometry args={[0.55, 0.16, 24, 48]} />
          ) : (
            <capsuleGeometry args={[0.28, 0.9, 8, 24]} />
          )}
          <meshStandardMaterial color="#0a0a0a" metalness={0.55} roughness={0.16} envMapIntensity={1.25} />
        </mesh>
      ))}
    </group>
  );
}

export default function PipelineScene({ reduced = false }: { reduced?: boolean }) {
  return (
    <Canvas
      dpr={[1, 2]}
      frameloop={reduced ? "demand" : "always"}
      gl={{ alpha: true, antialias: true, powerPreference: "high-performance", toneMapping: THREE.ACESFilmicToneMapping }}
      camera={{ position: [0, 1.1, 7.5], fov: 34, near: 0.1, far: 40 }}
      style={{ width: "100%", height: "100%", background: "transparent" }}
    >
      {/* 3-point softbox rig */}
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 6, 5]} intensity={2.4} color="#ffffff" />
      <directionalLight position={[-5, 2, 2]} intensity={0.7} color="#ffffff" />
      <directionalLight position={[0, 3, -6]} intensity={1.1} color="#ffffff" />

      {/* studio reflections for the chrome - no HDR fetch */}
      <Environment resolution={192}>
        <Lightformer form="rect" intensity={3} position={[0, 4, 3]} scale={[8, 3, 1]} />
        <Lightformer form="rect" intensity={1.2} position={[-4, 1, 2]} scale={[3, 4, 1]} />
        <Lightformer form="ring" intensity={0.8} position={[3, 2, -3]} scale={3} />
      </Environment>

      <Line reduced={reduced} />

      <ContactShadows position={[0, -1.4, 0]} opacity={0.22} blur={3} scale={16} far={4} frames={1} color="#0a0a0a" />
    </Canvas>
  );
}
