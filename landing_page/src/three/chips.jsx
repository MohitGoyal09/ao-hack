import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard } from '@react-three/drei'
import { makeLabelTexture } from './textures'

export const CHIPS = [
  { text: 'Covenant 3.1', radius: 3.05, speed: 0.2, y: 1.1, scale: 0.72 },
  { text: 'Ratio 2.40x', radius: 3.4, speed: -0.15, y: -0.35, scale: 0.68 },
  { text: 'Aon PDF parsed', radius: 2.75, speed: 0.28, y: -1.25, scale: 0.6 },
  { text: 'Approved h:c3f7', radius: 3.25, speed: 0.12, y: 1.85, scale: 0.62 },
]

export function OrbitChip({ chip }) {
  const ref = useRef()
  const tex = useMemo(() => makeLabelTexture(chip.text), [chip.text])

  useEffect(() => {
    let mounted = true
    const refresh = () => {
      if (mounted) tex.needsUpdate = true
    }
    if (document.fonts?.load) {
      document.fonts
        .load('500 62px "JetBrains Mono", monospace')
        .then(refresh)
        .catch(() => {})
    }
    return () => {
      mounted = false
    }
  }, [tex])

  useFrame((state) => {
    const r = ref.current
    const t = state.clock.elapsedTime
    r.position.x = Math.cos(t * chip.speed) * chip.radius
    r.position.z = Math.sin(t * chip.speed) * chip.radius
    r.position.y = chip.y + Math.sin(t * 0.9 + chip.radius) * 0.16
  })

  return (
    <group ref={ref} position={[chip.radius, chip.y, 0]}>
      <Billboard>
        <mesh scale={[chip.scale, chip.scale * 0.3125, 1]}>
          <planeGeometry args={[3.2, 1]} />
          <meshBasicMaterial
            map={tex}
            transparent
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </Billboard>
    </group>
  )
}