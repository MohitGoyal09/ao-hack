import { Component, useEffect, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { ContactShadows, Float, Grid } from '@react-three/drei'
import * as THREE from 'three'
import { CHIPS, OrbitChip } from './chips'
import { Particles, Shards } from './field'
import { Core } from './core'

const PALETTE = {
  paper: '#f7f5ec',
  green: '#146f69',
  greenMid: '#0fb6ac',
}

class WebGLSafe extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    const msg = error && error.message ? error.message : String(error)
    window.__ruxWebGLError = msg
    if (window._ruxWebGLFallback) window._ruxWebGLFallback(msg)
  }

  render() {
    if (this.state.failed) return <CssFallback />
    return this.props.children
  }
}

function CssFallback() {
  return (
    <div className="webgl-fallback" aria-hidden="true">
      <div className="fallback-core" />
      <div className="fallback-ring" />
      <div className="fallback-ring slow" />
      <div className="fallback-chip" style={{ top: '18%', right: '12%' }}>
        Ratio 2.40x
      </div>
      <div className="fallback-chip" style={{ bottom: '24%', left: '10%' }}>
        Approved h:c3f7
      </div>
    </div>
  )
}

function Rig({ children }) {
  const group = useRef()
  const pointer = useRef({ x: 0, y: 0 })
  const scroll = useRef(0)
  const reduced = useRef(false)

  useEffect(() => {
    reduced.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const onMove = (e) => {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1
    }
    const onScroll = () => {
      scroll.current = window.scrollY
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('scroll', onScroll)
    }
  }, [])

  useFrame((_, delta) => {
    const g = group.current
    if (!reduced.current) {
      g.rotation.y += delta * 0.08
      g.rotation.x = THREE.MathUtils.damp(g.rotation.x, pointer.current.y * 0.16, 2.2, delta)
      g.rotation.z = THREE.MathUtils.damp(g.rotation.z, -pointer.current.x * 0.07, 2.2, delta)
    }
    g.position.y = THREE.MathUtils.damp(g.position.y, -scroll.current * 0.0014, 2.2, delta)
  })

  return <group ref={group}>{children}</group>
}

export default function RuxScene() {
  useEffect(() => {
    window._ruxWebGLFallback = () => {}
    return () => {
      delete window._ruxWebGLFallback
    }
  }, [])

  return (
    <div className="hero-scene" aria-hidden="true">
      <div className="scene-glow" />
      <WebGLSafe>
        <Canvas
          camera={{ position: [0, 0.6, 7.4], fov: 42 }}
          dpr={[1, 1.75]}
          gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
          fallback={<CssFallback />}
        >
        <ambientLight intensity={0.75} />
        <directionalLight position={[5, 7, 4]} intensity={1.6} color="#fff7ea" />
        <directionalLight position={[-6, 2, -3]} intensity={0.7} color="#a7f0e2" />
        <pointLight position={[0, 0, 3.6]} intensity={18} color="#9ff0e6" distance={11} />
        <pointLight position={[0, -2.4, 1.4]} intensity={9} color="#0fb6ac" distance={9} />

        <Rig>
          <Float speed={1.4} rotationIntensity={0.35} floatIntensity={0.7}>
            <Core />
          </Float>
          <Particles />
          <Shards />
          {CHIPS.map((chip) => (
            <OrbitChip key={chip.text} chip={chip} />
          ))}
        </Rig>

        <ContactShadows
          position={[0, -2.38, 0]}
          opacity={0.3}
          scale={12}
          blur={2.6}
          far={4.2}
          color={PALETTE.green}
        />

        <Grid
          position={[0, -2.4, 0]}
          infiniteGrid
          cellSize={0.42}
          sectionSize={1.7}
          sectionThickness={1}
          cellThickness={0.6}
          cellColor={PALETTE.green}
          sectionColor={PALETTE.greenMid}
          fadeDistance={13}
          fadeStrength={1.6}
          side={THREE.DoubleSide}
        />
        </Canvas>
      </WebGLSafe>
    </div>
  )
}