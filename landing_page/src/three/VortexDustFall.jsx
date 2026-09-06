// Vortex Dust Fall — Originkit (React WebGL Particle Engine in Dark Green & Cream)
"use client"

import * as React from "react"
import { useEffect, useRef } from "react"

/* ---------------------------------------------------------------- constants */

const DPR_CAP = 1.5
const FOV_DEG = 42
const TAU = Math.PI * 2

/** Points per unit of `Density`. Density 160 -> 48,000 sprites. */
const PTS_PER_DENSITY = 300

/** `Radius` is a percent of this, so the dial is a whole number. */
const RADIUS_REF = 300
/** `Dot Size` is a percent of this world radius. */
const DOT_REF = 2.0
/** `Blur` is a percent of this. World-area units: coc_px = K*focal/rz^2. */
const BLUR_REF = 5000

/** One particle life, in seconds, at `Speed` 50 — the rate it shipped at. */
const LIFE_AT_50 = 3.2

/** Outward flare over one life. */
const DRIFT = 0.05
/** Spin decay constant. Higher = the swirl dies off sooner as dust falls. */
const SPIN_LAMBDA = 3.0
/** Descent exponent. */
const FALL_EASE = 1.35
/** Fraction of a life at which the rim puff peaks. */
const SPRAY_PEAK = 0.08
/** Birth radius, normalised, at which the rim puff starts to apply. */
const SPRAY_RIM = 0.5
/** Framing: how far ABOVE the frame's centre the ring sits. */
const FRAME_SHIFT = 0.22
/** Birth radius band, as a fraction of `Radius`. */
const BIRTH_R0 = 0.35
/** Emission coherence. */
const ARM_SPREAD = TAU * 0.75
const ARM_TURNS = 2.0
/** Ribbon half-width as a multiple of the ring's core half-width. */
const RIBBON = 3.0
/** Ring tessellation. */
const RING_SEG = 720

/* ------------------------------------------------------------------ shaders */

const VERT_DUST = `
precision highp float;

attribute vec4 aA;
attribute vec2 aB;

uniform vec2  uRes;
uniform float uFocal;
uniform float uPhase;
uniform float uRadius;
uniform float uRise;
uniform float uFall;
uniform float uSpinTurns;
uniform float uScatter;
uniform float uDotWorld;
uniform float uBlurK;
uniform float uCamDist;
uniform float uTilt;
uniform float uYPx;
uniform float uAlpha;

varying float vAlpha;

const float TAU = 6.2831853;

void main() {
    float tau = fract(aA.y + uPhase);

    float ang = aA.x * ${ARM_SPREAD.toFixed(6)} + aA.y * TAU * ${ARM_TURNS.toFixed(1)};
    float rN = mix(${BIRTH_R0.toFixed(3)}, 1.0, sqrt(aA.z));
    float r  = uRadius * rN * (1.0 + ${DRIFT.toFixed(3)} * tau);

    float tp   = ${SPRAY_PEAK.toFixed(3)};
    float bump = (tau / tp) * exp(1.0 - tau / tp);
    float rimW = smoothstep(${SPRAY_RIM.toFixed(3)}, 1.0, rN);
    float y    = uRise * bump * rimW - uFall * pow(tau, ${FALL_EASE.toFixed(2)});

    float L  = ${SPIN_LAMBDA.toFixed(1)};
    float sp = (1.0 - exp(-L * tau)) / (1.0 - exp(-L));
    float th = ang + uSpinTurns * TAU * sp;

    vec3 p = vec3(r * cos(th), y, r * sin(th));

    float n = aA.w * TAU;
    p.x += uScatter * tau * sin(n * 3.1 + tau * 5.3);
    p.z += uScatter * tau * sin(n * 4.7 + tau * 4.1 + 1.7);
    p.y += uScatter * tau * 0.6 * sin(n * 2.3 + tau * 6.7 + 3.3);

    float ct = cos(uTilt), st = sin(uTilt);
    float y2 =  p.y * ct - p.z * st;
    float z2 =  p.y * st + p.z * ct;
    float rz = uCamDist - z2;

    float live = step(1.0, rz);
    rz = max(rz, 1.0);

    vec2 s = vec2(p.x, y2) * uFocal / rz;
    s.y += uYPx;
    gl_Position = vec4(s / (uRes * 0.5), 0.0, 1.0);

    float sizePx = uDotWorld * (0.75 + 0.8 * aB.x) * uFocal / rz;
    float coc    = uBlurK * uFocal / (rz * rz);
    float tot    = sizePx + coc;
    float ratio  = max(tot / max(sizePx, 0.0001), 1.0);

    gl_PointSize = clamp(tot, 1.0, 64.0);

    float fadeIn  = smoothstep(0.0, 0.03, tau);
    float fadeOut = pow(1.0 - tau, 0.72);
    vAlpha = uAlpha * live * fadeIn * fadeOut
           * (0.5 + 0.5 * aB.y) * pow(ratio, -0.9);
}
`

const FRAG_DUST = `
precision highp float;
uniform vec3 uColor;
varying float vAlpha;
void main() {
    vec2 d = gl_PointCoord - 0.5;
    float r2 = dot(d, d) * 4.0;
    if (r2 > 1.0) discard;
    float a = vAlpha * exp(-r2 * 2.8);
    gl_FragColor = vec4(uColor, a);
}
`

const VERT_RING = `
precision highp float;

attribute vec2 aRing;

uniform vec2  uRes;
uniform float uFocal;
uniform float uRadius;
uniform float uCamDist;
uniform float uTilt;
uniform float uYPx;
uniform float uThick;
uniform float uSeg;

varying float vSide;
varying float vNear;

const float TAU = 6.2831853;

vec2 projPx(float a, out float rz) {
    vec3 p = vec3(uRadius * cos(a), 0.0, uRadius * sin(a));
    float ct = cos(uTilt), st = sin(uTilt);
    float y2 = p.y * ct - p.z * st;
    float z2 = p.y * st + p.z * ct;
    rz = max(uCamDist - z2, 1.0);
    return vec2(p.x, y2) * uFocal / rz + vec2(0.0, uYPx);
}

void main() {
    float a0 = aRing.x * TAU;
    float a1 = a0 + TAU / uSeg;
    float rz0, rz1;
    vec2 s0 = projPx(a0, rz0);
    vec2 s1 = projPx(a1, rz1);

    vec2 d  = s1 - s0;
    float dl = max(length(d), 0.0001);
    vec2 nrm = vec2(-d.y, d.x) / dl;

    float near   = uCamDist / rz0;
    float halfW  = uThick * 0.5 * ${RIBBON.toFixed(1)} * near;
    vec2 px = s0 + nrm * aRing.y * halfW;

    gl_Position = vec4(px / (uRes * 0.5), 0.0, 1.0);
    vSide = aRing.y;
    vNear = near;
}
`

const FRAG_RING = `
precision highp float;
uniform vec3  uColor;
uniform float uAlpha;
varying float vSide;
varying float vNear;
void main() {
    float s    = abs(vSide);
    float core = exp(-pow(s * ${RIBBON.toFixed(1)}, 2.0) * 3.5);
    float halo = exp(-s * s * 2.0) * 0.35;
    float a    = (core + halo) * uAlpha * clamp(vNear, 0.75, 1.35);
    gl_FragColor = vec4(uColor, a);
}
`

/* ------------------------------------------------------------------ helpers */

function parseColor(input) {
    if (!input) return [0.05, 0.35, 0.33, 1]
    let s = String(input).trim()

    const v = s.match(/^var\(\s*[^,)]+\s*,\s*(.+)\)$/i)
    if (v) s = v[1].trim()

    const rgb = s.match(/^rgba?\(([^)]+)\)$/i)
    if (rgb) {
        const p = rgb[1].split(/[\s,/]+/).filter(Boolean).map(parseFloat)
        return [
            (p[0] || 0) / 255,
            (p[1] || 0) / 255,
            (p[2] || 0) / 255,
            p.length > 3 && isFinite(p[3]) ? p[3] : 1,
        ]
    }

    const hsl = s.match(/^hsla?\(([^)]+)\)$/i)
    if (hsl) {
        const p = hsl[1].split(/[\s,/]+/).filter(Boolean)
        const h = (parseFloat(p[0]) || 0) / 360
        const sa = (parseFloat(p[1]) || 0) / 100
        const l = (parseFloat(p[2]) || 0) / 100
        const a = p.length > 3 && isFinite(parseFloat(p[3])) ? parseFloat(p[3]) : 1
        const q = l < 0.5 ? l * (1 + sa) : l + sa - l * sa
        const pp = 2 * l - q
        const hue = (t) => {
            if (t < 0) t += 1
            if (t > 1) t -= 1
            if (t < 1 / 6) return pp + (q - pp) * 6 * t
            if (t < 1 / 2) return q
            if (t < 2 / 3) return pp + (q - pp) * (2 / 3 - t) * 6
            return pp
        }
        return [hue(h + 1 / 3), hue(h), hue(h - 1 / 3), a]
    }

    let x = s.replace("#", "")
    if (x.length === 3 || x.length === 4)
        x = x.split("").map((c) => c + c).join("")
    if (x.length < 6) return [0.05, 0.35, 0.33, 1]
    return [
        parseInt(x.slice(0, 2), 16) / 255,
        parseInt(x.slice(2, 4), 16) / 255,
        parseInt(x.slice(4, 6), 16) / 255,
        x.length >= 8 ? parseInt(x.slice(6, 8), 16) / 255 : 1,
    ]
}

function mulberry32(a) {
    return () => {
        a |= 0
        a = (a + 0x6d2b79f5) | 0
        let t = Math.imul(a ^ (a >>> 15), 1 | a)
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
}

function compile(gl, type, src) {
    const sh = gl.createShader(type)
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS))
        console.warn("VortexDustFall shader:", gl.getShaderInfoLog(sh))
    return sh
}

function linkProg(gl, vs, fs) {
    const prog = gl.createProgram()
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, vs))
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, fs))
    gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS))
        console.warn("VortexDustFall link:", gl.getProgramInfoLog(prog))
    return prog
}

/* --------------------------------------------------------------------- props */

const DEFAULT_RING = {
    radius: 180,
    thickness: 13,
}
const DEFAULT_FALL = {
    height: 165,
    spin: 38,
    spray: 0,
}
const DEFAULT_FIELD = {
    scatter: 280,
    blur: 0,
}
const DEFAULT_HOVER = {
    amount: 103,
    transition: { type: "tween", duration: 0.6, ease: "easeOut" },
}

/* ----------------------------------------------------------------- component */

function __OriginkitBase_VortexDustFall(props) {
    const {
        background = "transparent",
        baseColor = "#0e5b56",
        accentColor = "#092c25",
        density = 160,
        dotSize = 115,
        speed = 48,
        distance = 1420,
        tilt = 19,
        style,
    } = props

    const ring = { ...DEFAULT_RING, ...(props.ring ?? {}) }
    const fall = { ...DEFAULT_FALL, ...(props.fall ?? {}) }
    const field = { ...DEFAULT_FIELD, ...(props.field ?? {}) }
    const hover = { ...DEFAULT_HOVER, ...(props.hover ?? {}) }

    const hostRef = useRef(null)
    const canvasRef = useRef(null)
    const pointerRef = useRef({ x: 0, y: 0, active: 0 })

    const live = useRef({
        baseColor, accentColor, density, dotSize, speed, distance, tilt,
        ring, fall, field, hover,
    })
    live.current = {
        baseColor, accentColor, density, dotSize, speed, distance, tilt,
        ring, fall, field, hover,
    }

    useEffect(() => {
        const host = hostRef.current
        const canvas = canvasRef.current
        if (!host || !canvas) return

        const gl = canvas.getContext("webgl", {
            alpha: true,
            antialias: true,
            premultipliedAlpha: false,
            depth: false,
        })
        if (!gl) return

        const dustProg = linkProg(gl, VERT_DUST, FRAG_DUST)
        const ringProg = linkProg(gl, VERT_RING, FRAG_RING)

        const U = (p, n) => gl.getUniformLocation(p, n)

        const dA = {
            a: gl.getAttribLocation(dustProg, "aA"),
            b: gl.getAttribLocation(dustProg, "aB"),
        }
        const dU = {
            res: U(dustProg, "uRes"), focal: U(dustProg, "uFocal"),
            phase: U(dustProg, "uPhase"), radius: U(dustProg, "uRadius"),
            rise: U(dustProg, "uRise"), fallD: U(dustProg, "uFall"),
            spinTurns: U(dustProg, "uSpinTurns"), scatter: U(dustProg, "uScatter"),
            dotWorld: U(dustProg, "uDotWorld"), blurK: U(dustProg, "uBlurK"),
            camDist: U(dustProg, "uCamDist"), tilt: U(dustProg, "uTilt"),
            yPx: U(dustProg, "uYPx"), alpha: U(dustProg, "uAlpha"),
            color: U(dustProg, "uColor"),
        }
        const rA = { ring: gl.getAttribLocation(ringProg, "aRing") }
        const rU = {
            res: U(ringProg, "uRes"), focal: U(ringProg, "uFocal"),
            radius: U(ringProg, "uRadius"), camDist: U(ringProg, "uCamDist"),
            tilt: U(ringProg, "uTilt"), yPx: U(ringProg, "uYPx"),
            thick: U(ringProg, "uThick"), seg: U(ringProg, "uSeg"),
            color: U(ringProg, "uColor"), alpha: U(ringProg, "uAlpha"),
        }

        const aBuf = gl.createBuffer()
        const bBuf = gl.createBuffer()
        let builtDensity = -1
        let count = 0

        const buildDust = (d) => {
            count = Math.max(1000, Math.round(d * PTS_PER_DENSITY))
            const arrA = new Float32Array(count * 4)
            const arrB = new Float32Array(count * 2)
            const rnd = mulberry32(0x51dd0c7)
            for (let i = 0; i < count; i++) {
                arrA[i * 4] = rnd()
                arrA[i * 4 + 1] = rnd()
                arrA[i * 4 + 2] = rnd()
                arrA[i * 4 + 3] = rnd()
                arrB[i * 2] = rnd()
                arrB[i * 2 + 1] = rnd()
            }
            gl.bindBuffer(gl.ARRAY_BUFFER, aBuf)
            gl.bufferData(gl.ARRAY_BUFFER, arrA, gl.STATIC_DRAW)
            gl.bindBuffer(gl.ARRAY_BUFFER, bBuf)
            gl.bufferData(gl.ARRAY_BUFFER, arrB, gl.STATIC_DRAW)
            builtDensity = d
        }

        const ringBuf = gl.createBuffer()
        const ringVerts = (RING_SEG + 1) * 2
        {
            const arr = new Float32Array(ringVerts * 2)
            for (let i = 0; i <= RING_SEG; i++) {
                const t = i / RING_SEG
                arr[i * 4] = t
                arr[i * 4 + 1] = -1
                arr[i * 4 + 2] = t
                arr[i * 4 + 3] = 1
            }
            gl.bindBuffer(gl.ARRAY_BUFFER, ringBuf)
            gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW)
        }

        gl.disable(gl.DEPTH_TEST)
        gl.enable(gl.BLEND)
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)

        let dpr = 1
        const resize = () => {
            dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP)
            const cssW = canvas.clientWidth || host.clientWidth || 1
            const cssH = canvas.clientHeight || host.clientHeight || 1
            const w = Math.max(1, Math.round(cssW * dpr))
            const h = Math.max(1, Math.round(cssH * dpr))
            if (canvas.width !== w || canvas.height !== h) {
                canvas.width = w
                canvas.height = h
            }
            gl.viewport(0, 0, w, h)
        }
        resize()
        const ro = new ResizeObserver(resize)
        ro.observe(canvas)

        let phase = 0
        let last = performance.now()
        let raf = 0
        let hoverX = 0
        let hoverY = 0
        let hoverAmt = 0

        const frame = (now) => {
            raf = requestAnimationFrame(frame)
            const dt = Math.min((now - last) / 1000, 0.05)
            last = now
            const L = live.current

            if (L.density !== builtDensity) buildDust(L.density)
            if (count === 0) return

            const hoverDur = Math.max(0.05, L.hover.transition?.duration ?? 0.6)
            const hoverK = 1 - Math.exp(-dt / hoverDur)
            const pt = pointerRef.current
            hoverX += (pt.x - hoverX) * hoverK
            hoverY += (pt.y - hoverY) * hoverK
            hoverAmt += (pt.active - hoverAmt) * hoverK
            const hoverAmount = L.hover.amount / 100

            const speedBoost = 1 + hoverAmt * hoverAmount * 0.6
            phase = (phase + (dt * ((L.speed / 50) * speedBoost)) / LIFE_AT_50) % 1

            const w = canvas.width
            const h = canvas.height
            const focal = h / (2 * Math.tan(((FOV_DEG / 2) * Math.PI) / 180))

            const radius = RADIUS_REF * (L.ring.radius / 100)
            const fallH = radius * (L.fall.height / 100)
            const rise = fallH * (L.fall.spray / 400)
            const yPx = h * FRAME_SHIFT
            const spinTurns = (L.fall.spin / 100) * 1.5
            const scatter = radius * (L.field.scatter / 100) * 0.15
            const dotWorld = DOT_REF * (L.dotSize / 100)
            const blurK = BLUR_REF * (L.field.blur / 100)

            const tiltRad =
                (L.tilt * Math.PI) / 180 +
                hoverY * hoverAmount * hoverAmt * ((10 * Math.PI) / 180)
            const camDist = L.distance - hoverAmt * hoverAmount * 150

            const [br, bg, bb, ba] = parseColor(L.baseColor)
            const [ar, ag, ab, aa] = parseColor(L.accentColor)

            gl.clearColor(0, 0, 0, 0)
            gl.clear(gl.COLOR_BUFFER_BIT)

            /* ==== DUST ==== */
            gl.useProgram(dustProg)
            gl.uniform2f(dU.res, w, h)
            gl.uniform1f(dU.focal, focal)
            gl.uniform1f(dU.phase, phase)
            gl.uniform1f(dU.radius, radius)
            gl.uniform1f(dU.rise, rise)
            gl.uniform1f(dU.fallD, fallH)
            gl.uniform1f(dU.spinTurns, spinTurns)
            gl.uniform1f(dU.scatter, scatter)
            gl.uniform1f(dU.dotWorld, dotWorld * dpr)
            gl.uniform1f(dU.blurK, blurK * dpr)
            gl.uniform1f(dU.camDist, camDist)
            gl.uniform1f(dU.tilt, tiltRad)
            gl.uniform1f(dU.yPx, yPx)
            gl.uniform1f(dU.alpha, ba)
            gl.uniform3f(dU.color, br, bg, bb)

            gl.bindBuffer(gl.ARRAY_BUFFER, aBuf)
            gl.enableVertexAttribArray(dA.a)
            gl.vertexAttribPointer(dA.a, 4, gl.FLOAT, false, 0, 0)
            gl.bindBuffer(gl.ARRAY_BUFFER, bBuf)
            gl.enableVertexAttribArray(dA.b)
            gl.vertexAttribPointer(dA.b, 2, gl.FLOAT, false, 0, 0)
            gl.drawArrays(gl.POINTS, 0, count)

            /* ==== RING ==== */
            gl.useProgram(ringProg)
            gl.uniform2f(rU.res, w, h)
            gl.uniform1f(rU.focal, focal)
            gl.uniform1f(rU.radius, radius)
            gl.uniform1f(rU.camDist, camDist)
            gl.uniform1f(rU.tilt, tiltRad)
            gl.uniform1f(rU.yPx, yPx)
            gl.uniform1f(rU.thick, L.ring.thickness * dpr)
            gl.uniform1f(rU.seg, RING_SEG)
            gl.uniform3f(rU.color, ar, ag, ab)
            gl.uniform1f(rU.alpha, aa)

            gl.bindBuffer(gl.ARRAY_BUFFER, ringBuf)
            gl.enableVertexAttribArray(rA.ring)
            gl.vertexAttribPointer(rA.ring, 2, gl.FLOAT, false, 0, 0)
            gl.drawArrays(gl.TRIANGLE_STRIP, 0, ringVerts)
        }
        raf = requestAnimationFrame(frame)

        return () => {
            cancelAnimationFrame(raf)
            ro.disconnect()
        }
    }, [])

    return (
        <div
            ref={hostRef}
            onPointerMove={(e) => {
                const rect = e.currentTarget.getBoundingClientRect()
                pointerRef.current = {
                    x: ((e.clientX - rect.left) / rect.width) * 2 - 1,
                    y: -(((e.clientY - rect.top) / rect.height) * 2 - 1),
                    active: 1,
                }
            }}
            onPointerLeave={() => {
                pointerRef.current = { x: 0, y: 0, active: 0 }
            }}
            style={{
                width: "100%",
                height: "100%",
                position: "relative",
                overflow: "hidden",
                background,
                ...style,
            }}
        >
            <canvas
                ref={canvasRef}
                style={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    display: "block",
                }}
            />
        </div>
    )
}

const __originkitPresetProps = {
  ring: {
    radius: 180,
    thickness: 13,
  },
  fall: {
    spin: 38,
    spray: 0,
    height: 165,
  },
  field: {
    blur: 0,
    scatter: 280,
  },
  hover: {
    amount: 103,
    transition: {
      ease: "easeOut",
      mass: 1,
      type: "tween",
      damping: 60,
      duration: 0.6,
      stiffness: 800,
    },
  },
  baseColor: "#0e5b56",
  accentColor: "#092c25",
  background: "transparent",
  density: 160,
  dotSize: 115,
  speed: 48,
  distance: 1420,
  tilt: 19,
}

export default function VortexDustFall(props) {
  return <__OriginkitBase_VortexDustFall {...__originkitPresetProps} {...props} />
}
