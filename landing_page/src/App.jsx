import Nav from './components/Nav'
import Hero from './components/Hero'
import Marquee from './components/Marquee'
import Engine from './components/Engine'
import Workflow from './components/Workflow'
import HumanLoop from './components/HumanLoop'
import Status from './components/Status'
import Footer from './components/Footer'
import CustomCursor from './components/CustomCursor'

export default function App() {
  return (
    <>
      <CustomCursor />
      <div className="grain" aria-hidden="true" />
      <Nav />
      <main>
        <Hero />
        <Marquee />
        <Engine />
        <Workflow />
        <HumanLoop />
        <Status />
      </main>
      <Footer />
    </>
  )
}