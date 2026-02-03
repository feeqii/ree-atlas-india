export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type RunCreate = {
  aoi_geojson: any
  mode: 'coastal' | 'hardrock'
  params?: Record<string, any>
  geology_geojson?: any
}

export async function createRun(payload: RunCreate) {
  const res = await fetch(`${API_URL}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create run')
  }
  return res.json()
}

export async function getRun(runId: string) {
  const res = await fetch(`${API_URL}/runs/${runId}`)
  if (!res.ok) throw new Error('Run not found')
  return res.json()
}

export async function listRuns() {
  const res = await fetch(`${API_URL}/runs`)
  if (!res.ok) throw new Error('Failed to list runs')
  return res.json()
}

export async function getTargets(runId: string) {
  const res = await fetch(`${API_URL}/runs/${runId}/targets`)
  if (!res.ok) throw new Error('Failed to fetch targets')
  return res.json()
}

export async function getTargetDetail(runId: string, targetId: string) {
  const res = await fetch(`${API_URL}/runs/${runId}/targets/${targetId}`)
  if (!res.ok) throw new Error('Target not found')
  return res.json()
}
