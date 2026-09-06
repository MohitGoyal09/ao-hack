import Nav from './components/Nav'
import Hero from './components/Hero'
import Marquee from './components/Marquee'
import Engine from './components/Engine'
import Workflow from './components/Workflow'
import HumanLoop from './components/HumanLoop'
import Status from './components/Status'
import Footer from './components/Footer'

export default function App() {
  return (
    <>
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