import { useState } from "react"
import "./App.css"
import HMCalculator from "./components/HMCalculator"
import LthrZones from "./components/LthrZones"

function App() {
  const [active, setActive] = useState("hm")

  return (
    <div
      style={{
        width: "500px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-start",
        padding: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 16,
          justifyContent: "center",
        }}
      >
        <button onClick={() => setActive("hm")}>
          Half Marathon Calculator
        </button>
        <button onClick={() => setActive("lthr")}>LTHR Calculator</button>
      </div>
      <div>
        {active === "hm" && <HMCalculator />}
        {active === "lthr" && <LthrZones />}
      </div>
    </div>
  )
}

export default App
