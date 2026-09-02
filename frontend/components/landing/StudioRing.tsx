"use client";

import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Lightformer } from "@react-three/drei";
import * as THREE from "three";
import { MathUtils, type Mesh } from "three";

/** Section 05 — a single brushed-chrome ring, studio-lit, slow rotation. */
function Ring({ reduced }: { reduced: boolean }) {
  const m = useRef<Mesh>(null);
  useFrame((_, dt) => {
    if (!m.current || reduced) return;
    m.current.rotation.y += dt * 0.35;
    m.current.rotation.x = MathUtils.damp(m.current.rotation.x, 0.35, 4, dt);
  });
  return (
    <mesh ref={m} rotation={[0.35, 0, 0.2]}>
      <torusGeometry args={[1.1, 0.34, 40, 96]} />
      <meshStandardMaterial color="#0a0a0a" metalness={0.92} roughness={0.34} envMapIntensity={1.4} />
    </mesh>
  );
}

export default function StudioRing({ reduced = false }: { reduced?: boolean }) {
  return (
    <Canvas
      dpr={[1, 2]}
      frameloop={reduced ? "demand" : "always"}
      gl={{ alpha: true, antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}
      camera={{ position: [0, 0.4, 4.6], fov: 32 }}
      style={{ width: "100%", height: "100%", background: "transparent" }}
    >
      <ambientLight intensity={0.5} />
      <directionalLight position={[3, 5, 4]} intensity={2.6} />
      <directionalLight position={[-4, 1, 2]} intensity={0.8} />
      <Environment resolution={192}>
        <Lightformer form="rect" intensity={3.4} position={[0, 3, 3]} scale={[7, 3, 1]} />
        <Lightformer form="rect" intensity={1.4} position={[-3, 0, 2]} scale={[3, 4, 1]} />
      </Environment>
      <Ring reduced={reduced} />
      <ContactShadows position={[0, -1.55, 0]} opacity={0.24} blur={2.6} scale={9} far={3} frames={1} color="#0a0a0a" />
    </Canvas>
  );
}
