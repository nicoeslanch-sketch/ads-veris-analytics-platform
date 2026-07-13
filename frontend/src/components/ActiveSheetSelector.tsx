import { Layers3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDataset } from '../data/DatasetContext'

export default function ActiveSheetSelector() {
  const { sheet, availableSheets, sheetSessions, setSheet } = useDataset()
  if (!sheet || availableSheets.length <= 1) return null

  const cleanedSheets = availableSheets.filter((name) => Boolean(sheetSessions[name]?.cleaning))
  const choices = cleanedSheets.includes(sheet) ? cleanedSheets : [sheet, ...cleanedSheets]

  return (
    <div className="-mt-5 mb-6 flex flex-wrap items-center gap-2 border-b border-navy/10 pb-3 text-xs text-navy/60">
      <Layers3 className="h-4 w-4 text-teal" />
      <label htmlFor="active-data-sheet" className="font-medium text-navy/70">
        Estás viendo
      </label>
      <select
        id="active-data-sheet"
        value={sheet}
        onChange={(event) => setSheet(event.target.value)}
        className="rounded-md border border-navy/20 bg-white px-2.5 py-1.5 font-semibold text-navy outline-none focus:border-teal"
      >
        {choices.map((name) => (
          <option key={name} value={name}>
            Hoja {name}
          </option>
        ))}
      </select>
      <Link to="/estandarizacion" className="ml-auto font-semibold text-teal hover:underline">
        Administrar hojas
      </Link>
    </div>
  )
}
