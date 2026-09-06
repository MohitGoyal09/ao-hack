# Rux — Landing Page

3D animated landing page for **Rux**, the autonomous covenant engine.

Built with **React 18 + Vite + react-three-fiber + drei + framer-motion**.

## Design system

- **Typography** — from [impeccable.style](https://impeccable.style/):
  `Alumni Sans` (hairline display), `Albert Sans` (body),
  `JetBrains Mono` (mono), `Instrument Serif` (italic accents).
- **Palette** — cream `#f7f5ec`, dark green `#146f69`, white `#fdfcf6`,
  ink `#242218` (impeccable's oklch tokens converted to hex).

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build → dist/
npm run preview  # serve the production build
npm run verify   # headless-Chrome runtime check (needs `npm run preview` first)
```

## Structure

```
src/
  App.jsx                 page composition
  components/             Nav, Hero, Marquee, Engine, Workflow, HumanLoop, Status, Footer
  three/                  the 3D "decision core" scene
    RuxCore.jsx           Canvas + camera rig (pointer / scroll parallax)
    core.jsx              orbiting icosahedron core + rings + bloom
    chips.jsx             floating evidence chips (Covenant 3.1, Ratio 2.40x…)
    field.jsx             particle field + floating shards
    textures.js           canvas-texture helpers
  styles/                 tokens, base, hero, sections, responsive
```

## 3D scene

A floating "decision core": translucent icosahedron lattice with a solid
emerald heart, three orbit rings, canvas-labeled evidence chips orbiting in
3D, an additive particle field, metallic shards, a grid floor, contact
shadows, mouse parallax, scroll elevation, and `prefers-reduced-motion`
support.