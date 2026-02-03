'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { listRuns } from '../../lib/api'

export default function RunsPage() {
  const [runs, setRuns] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRuns().then(setRuns).catch((err) => setError(err.message))
  }, [])

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold">Run History</h1>
          <Link className="text-sm text-reef" href="/">Back to Map</Link>
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        <div className="space-y-3">
          {runs.length === 0 && <div className="text-sm text-slate-500">No runs yet.</div>}
          {runs.map((run) => (
            <div key={run.id} className="border border-slate-200 rounded p-4 bg-white/80">
              <div className="text-xs text-slate-500">{new Date(run.created_at).toLocaleString()}</div>
              <div className="text-sm font-semibold">{run.mode} – {run.status}</div>
              <div className="text-xs text-slate-500">AOI: {run.aoi_name || 'Untitled AOI'}</div>
              <div className="text-xs text-slate-500">Run ID: {run.id}</div>
              <Link className="text-xs text-reef" href={`/?run=${run.id}`}>Open in Map</Link>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
