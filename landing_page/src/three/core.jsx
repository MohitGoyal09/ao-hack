import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { glowTexture } from './textures'

const PALETTE = {
  paper: '#f7f5ec',
  paperRaised: '#fdfcf6',
  green: '#146f69',
  greenMid: '#0fb6ac',
  greenPale: '#8ed3cc',
}

export function Core() {
  const ringA = useRef()
  const ringB = useRef()
  const inner = useRef()

  const glow = useMemo(
    () => glowTexture('rgba(141, 211, 204, 0.9)', 'rgba(15, 182, 172, 0)'),
    []
  )

  useFrame((state, delta) => {
    ringA.current.rotation.z += delta * 0.18
    ringB.current.rotation.y += delta * 0.1
    ringB.current.rotation.x =
      Math.PI / 2.4 + Math.sin(state.clock.elapsedTime * 0.34) * 0.14
    inner.current.rotation.y -= delta * 0.12
  })

  return (
    <group>
      {/* outer wire lattice */}
      <mesh>
        <icosahedronGeometry args={[1.52, 1]} />
        <meshBasicMaterial
          color={PALETTE.greenPale}
          wireframe
          transparent
          opacity={0.45}
        />
      </mesh>

      {/* glass shell */}
      <mesh>
        <icosahedronGeometry args={[1.46, 1]} />
        <meshPhysicalMaterial
          color={PALETTE.green}
          transparent
          opacity={0.16}
          roughness={0.18}
          metalness={0.02}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* inner lattice */}
      <mesh ref={inner}>
        <icosahedronGeometry args={[1.04, 1]} />
        <meshBasicMaterial
          color={PALETTE.greenMid}
          wireframe
          transparent
          opacity={0.55}
        />
      </mesh>

      {/* solid heart */}
      <mesh>
        <icosahedronGeometry args={[0.62, 2]} />
        <meshStandardMaterial
          color={PALETTE.green}
          roughness={0.28}
          metalness={0.15}
          emissive={PALETTE.greenMid}
          emissiveIntensity={0.4}
          flatShading
        />
      </mesh>

      {/* bloom */}
      <sprite scale={[4.6, 4.6, 1]}>
        <spriteMaterial
          map={glow}
          color={PALETTE.greenPale}
          transparent
          opacity={0.55}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </sprite>

      {/* orbit rings */}
      <mesh ref={ringA} rotation={[Math.PI / 2.05, 0.15, 0]}>
        <torusGeometry args={[2.55, 0.012, 24, 220]} />
        <meshBasicMaterial color={PALETTE.paperRaised} transparent opacity={0.9} />
      </mesh>

      <mesh ref={ringB} rotation={[1.25, 0.4, 0.2]}>
        <torusGeometry args={[3.05, 0.022, 24, 240]} />
        <meshStandardMaterial
          color={PALETTE.green}
          roughness={0.35}
          emissive={PALETTE.greenMid}
          emissiveIntensity={0.5}
        />
      </mesh>

      <mesh rotation={[Math.PI / 1.75, 0.6, 0.4]}>
        <torusGeometry args={[2.08, 0.006, 12, 160]} />
        <meshBasicMaterial color={PALETTE.paper} transparent opacity={0.45} />
      </mesh>
    </group>
  )
}