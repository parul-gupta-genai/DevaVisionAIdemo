import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Sphere, MeshDistortMaterial } from '@react-three/drei'
import * as THREE from 'three'

function BrainParticles() {
  const points = useRef<THREE.Points>(null)
  
  const particleCount = 2000
  const positions = useMemo(() => {
    const pos = new Float32Array(particleCount * 3)
    for (let i = 0; i < particleCount; i++) {
      const theta = Math.random() * 2 * Math.PI
      const phi = Math.acos((Math.random() * 2) - 1)
      const r = 2.5 + Math.random() * 0.5
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta)
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      pos[i * 3 + 2] = r * Math.cos(phi)
    }
    return pos
  }, [])

  useFrame(({ clock }) => {
    if (points.current) {
      points.current.rotation.y = clock.getElapsedTime() * 0.1
      points.current.rotation.x = clock.getElapsedTime() * 0.05
    }
  })

  return (
    <points ref={points}>
      <bufferGeometry>
        {/* @ts-ignore */}
        <bufferAttribute
          attach="attributes-position"
          count={particleCount}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial size={0.02} color="#38BDF8" transparent opacity={0.7} sizeAttenuation />
    </points>
  )
}

function CoreNode() {
  const mesh = useRef<THREE.Mesh>(null)
  
  useFrame(({ clock }) => {
    if (mesh.current) {
      mesh.current.rotation.x = clock.getElapsedTime() * 0.2
      mesh.current.rotation.y = clock.getElapsedTime() * 0.3
    }
  })

  return (
    <Sphere ref={mesh} args={[1.5, 64, 64]}>
      <MeshDistortMaterial 
        color="#1565C0" 
        emissive="#1a237e"
        emissiveIntensity={2.5}
        wireframe={true}
        distort={0.4} 
        speed={2} 
        transparent 
        opacity={0.85}
      />
    </Sphere>
  )
}

export function AIBrain() {
  return (
    <div className="w-full h-full relative">
      <div className="absolute inset-0 bg-blue-900/10 rounded-full blur-[100px] pointer-events-none" />
      <Canvas camera={{ position: [0, 0, 8], fov: 45 }}>
        <ambientLight intensity={0.4} />
        <pointLight position={[10, 10, 10]} intensity={1.5} color="#38BDF8" />
        <pointLight position={[-10, -10, -10]} intensity={1.2} color="#1a237e" />
        <BrainParticles />
        <CoreNode />
        <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={0.5} />
      </Canvas>
    </div>
  )
}
