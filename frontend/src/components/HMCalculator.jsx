import { useState } from "react"
import api from "../api"
import "../App.css"

const HMCalculator = () => {
  const [value, setValue] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [resultRow, setResultRow] = useState(null)
  const [hasSubmitted, setHasSubmitted] = useState(false)

  const handleEstimate = async () => {
    const trimmed = value.trim()
    if (!trimmed) return
    setIsLoading(true)
    setHasSubmitted(true)
    try {
      const res = await api.post("/submit", { value: trimmed })
      setResultRow(res.data?.row ?? null)
      setValue("")
    } catch (err) {
      console.error(err)
      alert("Failed to send. Is the backend running?")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="HMCalculator">
      <h1>
        Half Marathon <br></br> Calculator
      </h1>

      <div className="card" style={{ marginTop: 16 }}>
        <p className="formatText">Enter Test Result</p>
        <input
          type="text"
          placeholder="hh:mm:ss"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          style={{ padding: 8, marginRight: 8 }}
        />
        <button onClick={handleEstimate} disabled={!value.trim() || isLoading}>
          {isLoading ? "Sending..." : "Estimate"}
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        {resultRow ? (
          (() => {
            const pickFirstExisting = (row, keys) => {
              for (const key of keys) {
                if (key in row && row[key] !== null && row[key] !== undefined) {
                  return row[key]
                }
              }
              return undefined
            }

            const fields = [
              {
                label: "Estimated Half Marathon Time",
                keys: ["race_half_marathon", "race_half", "half_marathon"],
              },
              {
                label: "Easy pace per mile",
                keys: ["easy_pace_per_mile", "easy_per_mile", "easy_mile_pace"],
              },
              {
                label: "Easy pase per km",
                keys: [
                  "easy_pace_per_km",
                  "easy_pase_per_km",
                  "easy_per_km",
                  "easy_km_pace",
                ],
              },
              {
                label: "Marathon pace per mile",
                keys: [
                  "marathon_pace_per_mile",
                  "marathon_per_mile",
                  "marathon_mile_pace",
                ],
              },
              {
                label: "Marathon per km",
                keys: [
                  "marathon_pace_per_km",
                  "marathon_per_km",
                  "marathon_km_pace",
                ],
              },
              {
                label: "Threshold per km",
                keys: [
                  "threshold_pace_per_km",
                  "threshold_per_km",
                  "threshold_km_pace",
                ],
              },
              {
                label: "Threshold per mile",
                keys: [
                  "threshold_pace_per_mile",
                  "threshold_per_mile",
                  "threshold_mile_pace",
                ],
              },
            ]

            const items = fields
              .map((f) => ({
                ...f,
                value: pickFirstExisting(resultRow, f.keys),
              }))
              .filter((f) => f.value !== undefined)

            if (items.length === 0) {
              return <p>No supported fields found in the result.</p>
            }

            return (
              <ul>
                {items.map((item) => (
                  <li key={item.label}>
                    <strong>{item.label}:</strong> {String(item.value)}
                  </li>
                ))}
              </ul>
            )
          })()
        ) : hasSubmitted ? (
          <p>No matching row found.</p>
        ) : null}
      </div>
    </div>
  )
}

export default HMCalculator
