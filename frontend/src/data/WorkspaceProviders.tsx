import type { ReactNode } from 'react'
import SecurityGate from '../auth/SecurityGate'
import { AccessProvider } from '../lib/access'
import { DemoProvider } from '../demo/DemoContext'
import { DatasetProvider } from './DatasetContext'

export default function WorkspaceProviders({ children }: { children: ReactNode }) {
  // Token renewal temporarily unmounts SecurityGate's children. Keep the file
  // in memory while rechecking; DatasetProvider still resets on identity changes.
  return <DatasetProvider>
    <SecurityGate><AccessProvider><DemoProvider>{children}</DemoProvider></AccessProvider></SecurityGate>
  </DatasetProvider>
}
