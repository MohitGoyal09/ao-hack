import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import * as THREE from 'three'
import { glowTexture } from './textures'

const PALETTE = {
  paperRaised: '#fdfcf6',
  green: '#146f69',
  greenMid: '#0fb6ac',
  greenPale: '#8ed3cc',
}

export function Particles() {
  const ref = useRef()
  const sprite = useMemo(
    () => glowTexture('rgba(255,255,255,1)', 'rgba(255,255,255,0)'),
    []
  )

  const positions = useMemo(() => {
    const n = 900
    const arr = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) {
      const r = 4.6 + Math.random() * 3.4
      const th = Math.random() * Math.PI * 2
      const ph = Math.acos(2 * Math.random() - 1)
      arr[i * 3] = r * Math.sin(ph) * Math.cos(th)
      arr[i * 3 + 1] = r * Math.cos(ph) * 0.8
      arr[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th)
    }
    return arr
  }, [])

  useFrame((state, delta) => {
    const p = ref.current
    p.rotation.y += delta * 0.02
    p.rotation.x = Math.sin(state.clock.elapsedTime * 0.06) * 0.09
  })

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.065}
        map={sprite}
        color={PALETTE.greenMid}
        transparent
        opacity={0.6}
        depthWrite={false}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

export function Shards() {
  const shards = useMemo(
    () =>
      Array.from({ length: 8 }, (_, i) => {
        const r = 2.7 + Math.random() * 1.7
        const th = Math.random() * Math.PI * 2
        return {
          pos: [Math.cos(th) * r, (Math.random() - 0.5) * 2.4, Math.sin(th) * r],
          scale: 0.07 + Math.random() * 0.13,
          color:
            i % 2 ? PALETTE.green : i % 3 ? PALETTE.paperRaised : PALETTE.greenMid,
        }
      }),
    []
  )

  return (
    <>
      {shards.map((s, i) => (
        <Float key={i} speed={1.6} rotationIntensity={1.8} floatIntensity={1.2}>
          <mesh position={s.pos} scale={s.scale}>
            <octahedronGeometry args={[1, 0]} />
            <meshStandardMaterial
              color={s.color}
              roughness={0.3}
              flatShading
              emissive={s.color}
              emissiveIntensity={s.color === PALETTE.greenPale ? 0.5 : 0.18}
            />
          </mesh>
        </Float>
      ))}
    </>
  )
}