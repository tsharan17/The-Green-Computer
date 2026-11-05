import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { CameraRig, Label } from "../map3d/Map3DView";
import type { Camera, Palette } from "../map3d/palette";
import { type BoardPart, type BoardSpec, heatColor, heatField } from "./model";

const W = 10;
const D = 7;
const GRID = 72;
const MAP_Y = 2.45; // the heat map floats above the hardware, so neither hides the other
const MAP_H = 2.3;

const px = (x: number) => (x - 0.5) * W;
const pz = (y: number) => (y - 0.5) * D;

const PART_LOOK: Record<string, { color: string; h: number }> = {
  compute: { color: "#1c2522", h: 0.18 }, memory: { color: "#23292d", h: 0.2 }, storage: { color: "#23292d", h: 0.16 },
  link: { color: "#3d4a46", h: 0.28 }, power: { color: "#2c332f", h: 0.3 }, cooling: { color: "#8c98a0", h: 0.2 }, ic: { color: "#1c2522", h: 0.16 }, passive: { color: "#a68d5b", h: 0.07 },
};

function Instanced({ items, color, metalness = 0.3, roughness = 0.6, y = 0 }: {
  items: { x: number; z: number; sx: number; sz: number; h: number }[]; color: string; metalness?: number; roughness?: number; y?: number;
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const m = ref.current;
    if (!m) return;
    const t = new THREE.Object3D();
    items.forEach((it, i) => {
      t.position.set(it.x, y + it.h / 2, it.z);
      t.scale.set(it.sx, it.h, it.sz);
      t.updateMatrix();
      m.setMatrixAt(i, t.matrix);
    });
    m.instanceMatrix.needsUpdate = true;
  }, [items, y]);
  if (!items.length) return null;
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, items.length]} key={items.length}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color={color} metalness={metalness} roughness={roughness} />
    </instancedMesh>
  );
}

/** Copper, vias and small parts. Thin boxes rather than lines, so they keep their width on any screen. */
function Circuit({ board, lift }: { board: BoardSpec; lift: number }) {
  const copper = useMemo(() => board.wires.map((w) => {
    const horizontal = Math.abs(w.x1 - w.x0) * W > Math.abs(w.y1 - w.y0) * D;
    const len = Math.hypot((w.x1 - w.x0) * W, (w.y1 - w.y0) * D);
    const straight = w.x0 === w.x1 || w.y0 === w.y1;
    const t = w.bus ? 0.028 : 0.022;
    return straight
      ? { x: px((w.x0 + w.x1) / 2), z: pz((w.y0 + w.y1) / 2), sx: horizontal ? len + t : t, sz: horizontal ? t : len + t, h: 0.012 }
      : null;
  }).filter((x) => x !== null), [board]);
  // A board file's nets run straight between parts, at any angle.
  const nets = useMemo(() => board.wires.filter((w) => w.x0 !== w.x1 && w.y0 !== w.y1), [board]);
  const small = useMemo(() => board.dots.filter((d) => !d.via).map((d, i) => {
    const horizontal = i % 2 === 0;
    return { x: px(d.x), z: pz(d.y), sx: horizontal ? 0.11 : 0.06, sz: horizontal ? 0.06 : 0.11, h: 0.05 };
  }), [board]);
  const vias = useMemo(() => board.dots.filter((d) => d.via).map((d) => ({ x: px(d.x), z: pz(d.y), sx: 0.05, sz: 0.05, h: 0.012 })), [board]);
  return (
    <group position={[0, lift, 0]}>
      <Instanced items={copper} color="#d0a24c" metalness={0.85} roughness={0.32} y={0.002} />
      <Instanced items={small} color="#a68d5b" metalness={0.4} />
      <Instanced items={vias} color="#e0c273" metalness={0.9} roughness={0.25} y={0.002} />
      {nets.map((w, i) => {
        const a = new THREE.Vector3(px(w.x0), 0.012, pz(w.y0));
        const b = new THREE.Vector3(px(w.x1), 0.012, pz(w.y1));
        const dir = new THREE.Vector3().subVectors(b, a);
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), dir.clone().normalize());
        return (
          <mesh key={i} position={new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5)} quaternion={q}>
            <boxGeometry args={[dir.length(), 0.012, 0.022]} />
            <meshStandardMaterial color="#d0a24c" metalness={0.85} roughness={0.32} />
          </mesh>
        );
      })}
    </group>
  );
}

function Part({ p, lift, glow, heatF, showDie }: { p: BoardPart; lift: number; glow: boolean; heatF: number; showDie: boolean }) {
  const look = PART_LOOK[p.kind] ?? PART_LOOK.ic;
  const sx = p.w * W;
  const sz = p.h * D;
  const emissive = useMemo(() => {
    const [r, g, b] = heatColor(heatF);
    return glow ? new THREE.Color("#4cbb17") : new THREE.Color(r, g, b);
  }, [glow, heatF]);
  const memoryChips = p.kind === "memory" ? [-0.25, 0.25].flatMap((a) => [-0.25, 0.25].map((b) => [a * sx, b * sz] as const)) : [];
  return (
    <group position={[px(p.x), lift, pz(p.y)]}>
      {p.kind === "memory" ? (
        <>
          <mesh position={[0, 0.015, 0]}><boxGeometry args={[sx, 0.03, sz]} /><meshStandardMaterial color="#0c3320" /></mesh>
          {memoryChips.map(([x, z], i) => (
            <mesh key={i} position={[x, 0.03 + look.h / 2, z]}>
              <boxGeometry args={[sx * 0.42, look.h, sz * 0.42]} />
              <meshStandardMaterial color={look.color} roughness={0.5} metalness={0.3} emissive={emissive} emissiveIntensity={glow ? 0.9 : heatF * 0.5} />
            </mesh>
          ))}
        </>
      ) : (
        <mesh position={[0, look.h / 2, 0]}>
          <boxGeometry args={[sx, look.h, sz]} />
          <meshStandardMaterial color={look.color} roughness={0.5} metalness={0.3} emissive={emissive} emissiveIntensity={glow ? 0.9 : heatF * 0.45} />
        </mesh>
      )}
      {p.kind === "compute" && showDie && (
        <mesh position={[0, look.h + 0.02, 0]}>
          <boxGeometry args={[sx * 0.55, 0.04, sz * 0.55]} />
          <meshStandardMaterial color="#6d7d86" metalness={0.92} roughness={0.25} emissive={emissive} emissiveIntensity={heatF * 0.7} />
        </mesh>
      )}
    </group>
  );
}

function Fan({ animate, size, y }: { animate: boolean; size: number; y: number }) {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    if (animate && ref.current) ref.current.rotation.y += dt * 9;
  });
  return (
    <group position={[0, y, 0]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[size * 0.5, 0.05, 8, 40]} /><meshStandardMaterial color="#2a3133" /></mesh>
      <group ref={ref}>
        <mesh><cylinderGeometry args={[size * 0.14, size * 0.14, 0.09, 20]} /><meshStandardMaterial color="#16201c" /></mesh>
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <mesh key={i} rotation={[0.45, (i * Math.PI * 2) / 7, 0]} position={[Math.sin((i * Math.PI * 2) / 7) * size * 0.3, 0, Math.cos((i * Math.PI * 2) / 7) * size * 0.3]}>
            <boxGeometry args={[size * 0.13, 0.015, size * 0.32]} />
            <meshStandardMaterial color="#3a4648" roughness={0.45} />
          </mesh>
        ))}
      </group>
    </group>
  );
}

/** Air or coolant moving away from the chip. Speed and spread show the kind of cooling, not a flow solve. */
function Flow({ kind, animate, radius, y0 }: { kind: "fan" | "liquid" | "fins"; animate: boolean; radius: number; y0: number }) {
  const n = kind === "fins" ? 28 : 70;
  const ref = useRef<THREE.Points>(null);
  const seeds = useMemo(() => Array.from({ length: n }, (_, i) => ({ a: (i * 2.399963) % (Math.PI * 2), r: 0.25 + ((i * 37) % 100) / 130, p: ((i * 61) % 100) / 100 })), [n]);
  const positions = useMemo(() => new Float32Array(n * 3), [n]);
  const colors = useMemo(() => new Float32Array(n * 3), [n]);
  const clock = useRef(0);
  const place = (dt: number) => {
    clock.current += dt * (kind === "fins" ? 0.1 : 0.42);
    const reach = kind === "fins" ? 1.3 : 3.2;
    seeds.forEach((s, i) => {
      const f = (s.p + clock.current) % 1;
      positions[3 * i] = Math.cos(s.a) * radius * s.r * (1 + f * reach);
      positions[3 * i + 1] = y0 + (kind === "fins" ? f * 1.5 : 0.65 - f * 0.45 + Math.sin(f * 6 + s.a) * 0.06);
      positions[3 * i + 2] = Math.sin(s.a) * radius * s.r * (1 + f * reach);
      // Cool air arrives and carries heat off.
      const [r, g, b] = heatColor(0.72 - f * 0.65);
      colors[3 * i] = r;
      colors[3 * i + 1] = g;
      colors[3 * i + 2] = b;
    });
    const geo = ref.current?.geometry;
    if (geo) {
      geo.attributes.position.needsUpdate = true;
      geo.attributes.color.needsUpdate = true;
    }
  };
  useEffect(() => place(0));
  useFrame((_, dt) => { if (animate) place(dt); });
  return (
    <points ref={ref} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.09} vertexColors transparent opacity={0.85} depthWrite={false} sizeAttenuation />
    </points>
  );
}

function Cooler({ board, lift, animate, showFlow }: { board: BoardSpec; lift: number; animate: boolean; showFlow: boolean }) {
  const chip = board.parts.find((p) => p.kind === "compute");
  if (!chip || board.cooler === "none") return null;
  const sx = chip.w * W * 0.92;
  const sz = chip.h * D * 0.92;
  const base = 0.24;
  const fins = Math.max(Math.round(sx / 0.17), 6);
  return (
    <group position={[px(chip.x), lift, pz(chip.y)]}>
      {board.cooler === "liquid" ? (
        <>
          <mesh position={[0, base + 0.09, 0]}><boxGeometry args={[sx, 0.18, sz]} /><meshStandardMaterial color="#a9b6bd" metalness={0.9} roughness={0.25} /></mesh>
          {[-0.22, 0.22].map((o) => (
            <mesh key={o} position={[sx * o, base + 0.44, sz / 2 + 0.35]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.42, 0.06, 10, 24, Math.PI]} />
              <meshStandardMaterial color="#1b5e8a" roughness={0.35} />
            </mesh>
          ))}
        </>
      ) : (
        <>
          <mesh position={[0, base + 0.04, 0]}><boxGeometry args={[sx, 0.08, sz]} /><meshStandardMaterial color="#b6c0c6" metalness={0.92} roughness={0.28} /></mesh>
          {Array.from({ length: fins }, (_, i) => (
            <mesh key={i} position={[(i - (fins - 1) / 2) * (sx / fins), base + 0.34, 0]}>
              <boxGeometry args={[0.05, 0.52, sz]} />
              <meshStandardMaterial color="#c5ced3" metalness={0.92} roughness={0.3} />
            </mesh>
          ))}
          {board.cooler === "fan" && <Fan animate={animate} size={Math.min(sx, sz) * 0.92} y={base + 0.68} />}
        </>
      )}
      {showFlow && <Flow kind={board.cooler} animate={animate} radius={Math.min(sx, sz) * 0.6} y0={base + 0.3} />}
    </group>
  );
}

/** The temperature map. Height and colour both carry temperature, and it eases when the cooling changes. */
function HeatMap({ board, tempC, scaleMaxC, animate, invalidateTick }: { board: BoardSpec; tempC: number; scaleMaxC: number; animate: boolean; invalidateTick: number }) {
  const mesh = useRef<THREE.Mesh>(null);
  const field = useMemo(() => heatField(board.parts, GRID), [board.parts]);
  const shown = useRef(tempC);
  const geo = useMemo(() => new THREE.PlaneGeometry(W, D, GRID - 1, GRID - 1).rotateX(-Math.PI / 2), []);
  const colors = useMemo(() => new Float32Array(GRID * GRID * 3), []);
  useEffect(() => {
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return () => geo.dispose();
  }, [geo, colors]);
  const apply = (t: number) => {
    const span = Math.max(scaleMaxC - board.ambientC, 1);
    const rise = t - board.ambientC;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    for (let k = 0; k < field.length; k++) {
      const f = (rise * field[k]) / span;
      pos.setY(k, f * MAP_H);
      const [r, g, b] = heatColor(f);
      colors[3 * k] = r * r; // the ramp is written in screen colours; WebGL blends in linear light
      colors[3 * k + 1] = g * g;
      colors[3 * k + 2] = b * b;
    }
    pos.needsUpdate = true;
    const col = geo.getAttribute("color");
    if (col) col.needsUpdate = true;
    geo.computeVertexNormals();
  };
  useLayoutEffect(() => {
    if (!animate) shown.current = tempC;
    apply(shown.current);
  }, [field, tempC, scaleMaxC, invalidateTick]); // eslint-disable-line react-hooks/exhaustive-deps
  useFrame((_, dt) => {
    if (Math.abs(shown.current - tempC) < 0.05) return;
    shown.current += (tempC - shown.current) * Math.min(dt * 2.6, 1);
    apply(shown.current);
  });
  return (
    <mesh ref={mesh} geometry={geo} position={[0, MAP_Y, 0]}>
      <meshStandardMaterial vertexColors side={THREE.DoubleSide} transparent opacity={0.86} roughness={0.7} metalness={0} />
    </mesh>
  );
}

function OneBoard({ board, offsetX, explode, showHeat, showCircuit, showFlow, showLabels, activeIds, glowKinds, tempC, scaleMaxC, animate, limit, pal, k }: {
  board: BoardSpec; offsetX: number; explode: number; showHeat: boolean; showCircuit: boolean; showFlow: boolean; showLabels: boolean;
  activeIds: Set<string>; glowKinds: Set<string>; tempC: number | null; scaleMaxC: number; animate: boolean; limit: boolean; pal: Palette; k: number;
}) {
  const hot = Math.max(...board.parts.map((p) => p.heatW), 0.0001);
  const rise = tempC !== null ? tempC - board.ambientC : 0;
  const span = Math.max(scaleMaxC - board.ambientC, 1);
  const chipsLift = 0.06 + explode * 0.75;
  const coolerLift = 0.06 + explode * 1.9;
  const y = (c: number) => MAP_Y + ((c - board.ambientC) / span) * MAP_H;
  return (
    <group position={[offsetX, 0, 0]}>
      <mesh position={[0, -0.04, 0]}>
        <boxGeometry args={[W, 0.08, D]} />
        <meshStandardMaterial color="#0d4a2c" roughness={0.65} metalness={0.15} />
      </mesh>
      {showCircuit && <Circuit board={board} lift={0.002} />}
      {board.connectors.map((c) => (
        <mesh key={c.name} position={[px(c.x), 0.11, pz(c.y)]}>
          <boxGeometry args={[c.w * W, 0.22, c.h * D]} />
          <meshStandardMaterial color="#59646a" metalness={0.75} roughness={0.35} />
        </mesh>
      ))}
      {board.parts.map((p) => (
        <Part key={p.id} p={p} lift={chipsLift} glow={activeIds.has(p.id) || glowKinds.has(p.kind)} showDie={board.cooler === "none" || explode > 0.1}
          heatF={tempC !== null ? (p.heatW / hot) * Math.min(rise / span, 1) : 0} />
      ))}
      <Cooler board={board} lift={coolerLift} animate={animate} showFlow={showFlow && tempC !== null} />
      {showHeat && tempC !== null && <HeatMap board={board} tempC={tempC} scaleMaxC={scaleMaxC} animate={animate} invalidateTick={0} />}
      {limit && (
        <mesh position={[0, showHeat && tempC !== null ? y(board.throttleC) : 1.9, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[W * 1.03, D * 1.03]} />
          <meshBasicMaterial color="#d9402b" transparent opacity={0.16} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      )}
      {limit && <Label text={`Slows down at ${board.throttleC.toFixed(0)} °C`} pos={[0, (showHeat && tempC !== null ? y(board.throttleC) : 1.9) + 0.2, -D / 2 - 0.1]} pal={pal} scale={k * 0.95} />}
      {showLabels && board.parts.filter((p) => p.kind !== "passive" && p.kind !== "ic").map((p) => (
        <Label key={p.id} text={`${p.name}${p.heatW > 0 ? ` · ${p.heatW.toPrecision(2)} W` : ""}`} pos={[px(p.x), chipsLift + 0.72, pz(p.y) + (p.h * D) / 2 + 0.12]} pal={pal} scale={k * 1.05} />
      ))}
      {board.label && <Label text={board.label} pos={[0, 0.45, D / 2 + 0.75]} pal={pal} scale={k * 1.2} />}
    </group>
  );
}

export default function Board3DView({ boards, temps, scaleMaxC, cam, pal, animate, explode, showHeat, showCircuit, showFlow, showLabels, limit, activeIds, glowKinds, spin, onReady }: {
  boards: BoardSpec[]; temps: (number | null)[]; scaleMaxC: number; cam: Camera; pal: Palette; animate: boolean; explode: number;
  showHeat: boolean; showCircuit: boolean; showFlow: boolean; showLabels: boolean; limit: boolean; activeIds: Set<string>; glowKinds: Set<string>; spin?: boolean; onReady?: () => void;
}) {
  const gap = W + 2.4;
  const extent = boards.length > 1 ? 11.5 : 6.2;
  const center = useMemo<[number, number, number]>(() => [0, showHeat ? 1.2 : 0.5, 0], [showHeat]);
  const k = Math.max(1.05, extent / 6.2);
  return (
    <Canvas flat frameloop={animate ? "always" : "demand"} dpr={[1, 1.75]} camera={{ fov: 38, near: 0.1, far: 500 }} onCreated={() => onReady?.()}
      gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}>
      <hemisphereLight args={["#eaffef", "#10261a", 1.25]} />
      <ambientLight intensity={0.4} />
      <directionalLight position={[7, 13, 8]} intensity={1.9} />
      <directionalLight position={[-9, 6, -7]} intensity={0.55} color="#b8ffd8" />
      <CameraRig cam={cam} extent={extent} center={center} />
      <Spin on={!!spin && animate}>
        {boards.map((b, i) => (
          <OneBoard key={i} board={b} offsetX={(i - (boards.length - 1) / 2) * gap} explode={explode} showHeat={showHeat && b.mapped} showCircuit={showCircuit}
            showFlow={showFlow} showLabels={showLabels} activeIds={activeIds} glowKinds={glowKinds} tempC={temps[i] ?? null} scaleMaxC={scaleMaxC} animate={animate} limit={limit} pal={pal} k={k} />
        ))}
      </Spin>
    </Canvas>
  );
}

function Spin({ on, children }: { on: boolean; children: React.ReactNode }) {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => {
    if (on && ref.current) ref.current.rotation.y += dt * 0.14;
  });
  return <group ref={ref}>{children}</group>;
}
