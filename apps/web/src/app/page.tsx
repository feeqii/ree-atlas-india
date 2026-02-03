'use client'

import { useEffect, useRef, useState } from 'react'
import maplibregl, { Map } from 'maplibre-gl'
import clsx from 'clsx'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { createRun, getRun, getTargets, getTargetDetail, API_URL } from '../lib/api'
import { AOI_PRESETS } from '../data/presets'

const baseMapStyle = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors'
    }
  },
  layers: [
    {
      id: 'osm',
      type: 'raster',
      source: 'osm'
    }
  ]
} as const

const defaultParams = {
  time_range: '',
  cloud_cover_max: 40,
  target_percentile: 95,
  threshold_method: 'percentile',
  fixed_threshold: 0.7,
  min_area_km2: 0.1,
  max_items: 3,
  cache_downloads: false,
  osm_timeout_s: 40,
  use_synthetic: false,
  synthetic_width: 256,
  synthetic_height: 256
}

const progressSteps = [
  'fetch_imagery',
  'fetch_dem',
  'fetch_osm',
  'compute_features',
  'score',
  'extract_targets',
  'generate_outputs'
]

export default function HomePage() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<Map | null>(null)
  const searchParams = useSearchParams()
  const [mode, setMode] = useState<'coastal' | 'hardrock'>('coastal')
  const [aoiGeojson, setAoiGeojson] = useState<any | null>(null)
  const [aoiName, setAoiName] = useState<string>('')
  const [geologyGeojson, setGeologyGeojson] = useState<any | null>(null)
  const [params, setParams] = useState(defaultParams)
  const [weightsText, setWeightsText] = useState<string>('')
  const [runId, setRunId] = useState<string | null>(null)
  const [runDetail, setRunDetail] = useState<any | null>(null)
  const [targets, setTargets] = useState<any | null>(null)
  const [selectedTarget, setSelectedTarget] = useState<any | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [drawing, setDrawing] = useState(false)
  const drawStartRef = useRef<[number, number] | null>(null)
  const drawingRef = useRef(false)
  const [layerVisibility, setLayerVisibility] = useState({
    overlay: true,
    targets: true,
    sentinel: false,
    hillshade: false,
    roads: false,
    rivers: false
  })

  useEffect(() => {
    if (mapRef.current || !mapContainerRef.current) return
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: baseMapStyle,
      center: [78.9629, 20.5937],
      zoom: 4.5
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')

    map.on('load', () => {
      map.addSource('aoi', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      })
      map.addLayer({
        id: 'aoi-fill',
        type: 'fill',
        source: 'aoi',
        paint: { 'fill-color': '#0f766e', 'fill-opacity': 0.15 }
      })
      map.addLayer({
        id: 'aoi-line',
        type: 'line',
        source: 'aoi',
        paint: { 'line-color': '#0f766e', 'line-width': 2 }
      })
    })

    map.on('mousedown', (e) => {
      if (!drawingRef.current) return
      drawStartRef.current = [e.lngLat.lng, e.lngLat.lat]
      map.dragPan.disable()
      map.dragRotate.disable()
      map.doubleClickZoom.disable()
      map.boxZoom.disable()
      map.scrollZoom.disable()
    })

    map.on('mousemove', (e) => {
      if (!drawingRef.current || !drawStartRef.current) return
      const end: [number, number] = [e.lngLat.lng, e.lngLat.lat]
      const minx = Math.min(drawStartRef.current[0], end[0])
      const maxx = Math.max(drawStartRef.current[0], end[0])
      const miny = Math.min(drawStartRef.current[1], end[1])
      const maxy = Math.max(drawStartRef.current[1], end[1])
      const poly = {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]
        },
        properties: {}
      }
      setAoiGeojson(poly)
    })

    map.on('mouseup', (e) => {
      if (!drawingRef.current || !drawStartRef.current) return
      const end: [number, number] = [e.lngLat.lng, e.lngLat.lat]
      const minx = Math.min(drawStartRef.current[0], end[0])
      const maxx = Math.max(drawStartRef.current[0], end[0])
      const miny = Math.min(drawStartRef.current[1], end[1])
      const maxy = Math.max(drawStartRef.current[1], end[1])
      const poly = {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]
        },
        properties: {}
      }
      setAoiGeojson(poly)
      setDrawing(false)
      drawStartRef.current = null
      map.dragPan.enable()
      map.dragRotate.enable()
      map.doubleClickZoom.enable()
      map.boxZoom.enable()
      map.scrollZoom.enable()
    })
  }, [])

  useEffect(() => {
    drawingRef.current = drawing
    if (!mapRef.current) return
    const map = mapRef.current
    const canvas = map.getCanvas()
    canvas.style.cursor = drawing ? 'crosshair' : ''
    if (!drawing) {
      drawStartRef.current = null
      map.dragPan.enable()
      map.dragRotate.enable()
      map.doubleClickZoom.enable()
      map.boxZoom.enable()
      map.scrollZoom.enable()
    }
  }, [drawing])

  useEffect(() => {
    if (!mapRef.current) return
    const map = mapRef.current
    const source = map.getSource('aoi') as maplibregl.GeoJSONSource | undefined
    if (source) {
      source.setData(aoiGeojson ? { type: 'FeatureCollection', features: [aoiGeojson] } : { type: 'FeatureCollection', features: [] })
    }
    if (aoiGeojson) {
      const bbox = aoiGeojson.geometry.coordinates[0].reduce((acc: number[], coord: number[]) => {
        return [
          Math.min(acc[0], coord[0]),
          Math.min(acc[1], coord[1]),
          Math.max(acc[2], coord[0]),
          Math.max(acc[3], coord[1])
        ]
      }, [Infinity, Infinity, -Infinity, -Infinity])
      map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40 })
    }
  }, [aoiGeojson])

  useEffect(() => {
    if (!runId) return
    const interval = setInterval(async () => {
      try {
        const detail = await getRun(runId)
        setRunDetail(detail)
        if (detail.status === 'completed') {
          clearInterval(interval)
          const tgt = await getTargets(runId)
          setTargets(tgt)
          await applyRunLayers(detail, tgt)
        }
        if (detail.status === 'failed') {
          clearInterval(interval)
          setError(detail.error || 'Run failed')
        }
      } catch (err) {
        clearInterval(interval)
        setError((err as Error).message)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [runId])

  useEffect(() => {
    const runParam = searchParams.get('run')
    if (!runParam) return
    setRunId(runParam)
    getRun(runParam)
      .then(async (detail) => {
        setRunDetail(detail)
        if (detail.status === 'completed') {
          const tgt = await getTargets(runParam)
          setTargets(tgt)
          await applyRunLayers(detail, tgt)
        }
      })
      .catch((err) => setError(err.message))
  }, [searchParams])

  async function applyRunLayers(detail: any, tgtGeojson: any) {
    if (!mapRef.current) return
    const map = mapRef.current
    if (!map.isStyleLoaded()) {
      map.once('load', () => applyRunLayers(detail, tgtGeojson))
      return
    }

    const removeLayer = (id: string) => {
      if (map.getLayer(id)) map.removeLayer(id)
    }
    const removeSource = (id: string) => {
      if (map.getSource(id)) map.removeSource(id)
    }

    ['overlay', 'sentinel', 'hillshade', 'targets', 'targets-outline', 'roads', 'rivers'].forEach((id) => {
      removeLayer(id)
      removeSource(id)
    })

    if (detail.overlay_bbox) {
      const { minx, miny, maxx, maxy } = detail.overlay_bbox
      const coords: any = [
        [minx, maxy],
        [maxx, maxy],
        [maxx, miny],
        [minx, miny]
      ]
      map.addSource('overlay', {
        type: 'image',
        url: `${API_URL}/runs/${detail.id}/overlay.png` as any,
        coordinates: coords
      })
      map.addLayer({
        id: 'overlay',
        type: 'raster',
        source: 'overlay',
        paint: { 'raster-opacity': 0.8 }
      })
    }

    if (detail.overlay_bbox) {
      const { minx, miny, maxx, maxy } = detail.overlay_bbox
      const coords: any = [
        [minx, maxy],
        [maxx, maxy],
        [maxx, miny],
        [minx, miny]
      ]
      map.addSource('sentinel', {
        type: 'image',
        url: `${API_URL}/runs/${detail.id}/sentinel.png` as any,
        coordinates: coords
      })
      map.addLayer({
        id: 'sentinel',
        type: 'raster',
        source: 'sentinel',
        paint: { 'raster-opacity': 0.75 },
        layout: { visibility: layerVisibility.sentinel ? 'visible' : 'none' }
      })

      map.addSource('hillshade', {
        type: 'image',
        url: `${API_URL}/runs/${detail.id}/hillshade.png` as any,
        coordinates: coords
      })
      map.addLayer({
        id: 'hillshade',
        type: 'raster',
        source: 'hillshade',
        paint: { 'raster-opacity': 0.55 },
        layout: { visibility: layerVisibility.hillshade ? 'visible' : 'none' }
      })
    }

    if (tgtGeojson) {
      map.addSource('targets', { type: 'geojson', data: tgtGeojson })
      map.addLayer({
        id: 'targets',
        type: 'fill',
        source: 'targets',
        paint: { 'fill-color': '#0f766e', 'fill-opacity': 0.25 },
        layout: { visibility: layerVisibility.targets ? 'visible' : 'none' }
      })
      map.addLayer({
        id: 'targets-outline',
        type: 'line',
        source: 'targets',
        paint: { 'line-color': '#0f766e', 'line-width': 2 },
        layout: { visibility: layerVisibility.targets ? 'visible' : 'none' }
      })
      map.on('click', 'targets', async (e) => {
        const feature = e.features?.[0]
        if (!feature) return
        const id = feature.properties?.id
        if (id) {
          const detail = await getTargetDetail(runId!, id)
          setSelectedTarget(detail)
        }
      })
    }

    try {
      const roads = await fetch(`${API_URL}/runs/${detail.id}/exports/roads.geojson`).then((r) => (r.ok ? r.json() : null))
      if (roads) {
        map.addSource('roads', { type: 'geojson', data: roads })
        map.addLayer({
          id: 'roads',
          type: 'line',
          source: 'roads',
          paint: { 'line-color': '#334155', 'line-width': 1 },
          layout: { visibility: layerVisibility.roads ? 'visible' : 'none' }
        })
      }
    } catch (e) {
      // ignore
    }

    try {
      const rivers = await fetch(`${API_URL}/runs/${detail.id}/exports/rivers.geojson`).then((r) => (r.ok ? r.json() : null))
      if (rivers) {
        map.addSource('rivers', { type: 'geojson', data: rivers })
        map.addLayer({
          id: 'rivers',
          type: 'line',
          source: 'rivers',
          paint: { 'line-color': '#0ea5e9', 'line-width': 1 },
          layout: { visibility: layerVisibility.rivers ? 'visible' : 'none' }
        })
      }
    } catch (e) {
      // ignore
    }

    if (layerVisibility.overlay) {
      map.setLayoutProperty('overlay', 'visibility', 'visible')
    } else if (map.getLayer('overlay')) {
      map.setLayoutProperty('overlay', 'visibility', 'none')
    }
  }

  function handlePreset(bbox: number[]) {
    const poly = {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]
      },
      properties: {}
    }
    setAoiGeojson(poly)
  }

  async function handleRun() {
    setError(null)
    if (!aoiGeojson) {
      setError('Please define an AOI before running analysis.')
      return
    }
    const withName = {
      ...aoiGeojson,
      properties: { ...(aoiGeojson.properties || {}), name: aoiName || aoiGeojson.properties?.name }
    }
    let weights: Record<string, number> | undefined
    if (weightsText.trim()) {
      try {
        weights = JSON.parse(weightsText)
      } catch (e) {
        setError('Weights JSON is invalid.')
        return
      }
    }
    const payload = {
      aoi_geojson: withName,
      mode,
      params: { ...params, ...(weights ? { weights } : {}) },
      geology_geojson: geologyGeojson || undefined
    }
    try {
      const res = await createRun(payload)
      setRunId(res.run_id)
      setRunDetail({ status: 'queued', progress: { steps: {} } })
      setTargets(null)
      setSelectedTarget(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  async function handleGeojsonUpload(file: File, setter: (data: any) => void) {
    const text = await file.text()
    try {
      const data = JSON.parse(text)
      setter(data)
    } catch (err) {
      setError('Invalid GeoJSON file')
    }
  }

  function toggleLayer(key: keyof typeof layerVisibility) {
    const next = { ...layerVisibility, [key]: !layerVisibility[key] }
    setLayerVisibility(next)
    if (!mapRef.current) return
    const map = mapRef.current
    const mapLayerId = key === 'targets' ? 'targets' : key
    if (map.getLayer(mapLayerId)) {
      map.setLayoutProperty(mapLayerId, 'visibility', next[key] ? 'visible' : 'none')
    }
    if (key === 'targets' && map.getLayer('targets-outline')) {
      map.setLayoutProperty('targets-outline', 'visibility', next[key] ? 'visible' : 'none')
    }
  }

  const progress = runDetail?.progress?.steps || {}

  return (
    <div className="flex h-screen">
      <aside className="w-[320px] bg-white/85 backdrop-blur border-r border-slate-200 shadow-soft p-4 overflow-y-auto panel-scroll">
        <div className="mb-4">
          <h1 className="text-xl font-semibold">REE Atlas India</h1>
          <p className="text-xs text-slate-500">Explainable open-data prospectivity for REE exploration.</p>
          <div className="mt-2 flex gap-3 text-xs text-reef">
            <Link href="/runs">Run History</Link>
            <Link href="/data-sources">Data Sources</Link>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-600">AOI</label>
            <div className="mt-2 flex flex-col gap-2">
              <input
                className="border border-slate-300 rounded px-2 py-1 text-sm"
                placeholder="AOI name (optional)"
                value={aoiName}
                onChange={(e) => setAoiName(e.target.value)}
              />
              <button
                className={clsx('px-3 py-2 text-sm rounded border', drawing ? 'border-reef bg-reef text-white' : 'border-slate-300')}
                onClick={() => {
                  setDrawing(!drawing)
                }}
              >
                {drawing ? 'Drag on map to draw…' : 'Draw Rectangle'}
              </button>
              <div className="text-[11px] text-slate-500">Tip: When draw mode is on, drag to size the box. Pan is disabled.</div>
              <input
                type="file"
                accept="application/geo+json,application/json,.geojson"
                className="text-xs"
                onChange={(e) => e.target.files && handleGeojsonUpload(e.target.files[0], setAoiGeojson)}
              />
              <select
                className="border border-slate-300 rounded px-2 py-1 text-sm"
                onChange={(e) => {
                  const preset = AOI_PRESETS.find((p) => p.id === e.target.value)
                  if (preset) {
                    handlePreset(preset.bbox)
                    setAoiName(preset.name)
                  }
                }}
              >
                <option value="">Use preset…</option>
                {AOI_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              {aoiGeojson && (
                <button className="text-xs text-reef" onClick={() => { setAoiGeojson(null); setAoiName('') }}>Clear AOI</button>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600">Mode</label>
            <div className="mt-2 flex gap-2">
              <button className={clsx('px-3 py-1 rounded text-sm border', mode === 'coastal' ? 'bg-reef text-white border-reef' : 'border-slate-300')} onClick={() => setMode('coastal')}>Coastal Placer</button>
              <button className={clsx('px-3 py-1 rounded text-sm border', mode === 'hardrock' ? 'bg-reef text-white border-reef' : 'border-slate-300')} onClick={() => setMode('hardrock')}>Hard-Rock</button>
            </div>
          </div>

          {mode === 'hardrock' && (
            <div>
              <label className="text-xs font-semibold text-slate-600">Optional Geology Upload</label>
              <input
                type="file"
                accept="application/geo+json,application/json,.geojson"
                className="mt-2 text-xs"
                onChange={(e) => e.target.files && handleGeojsonUpload(e.target.files[0], setGeologyGeojson)}
              />
            </div>
          )}

          <div>
            <details>
              <summary className="text-xs font-semibold text-slate-600 cursor-pointer">Advanced Params</summary>
              <div className="mt-2 space-y-2">
                <label className="text-xs text-slate-500">Time Range (YYYY-MM-DD/YYYY-MM-DD)</label>
                <input
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.time_range}
                  onChange={(e) => setParams({ ...params, time_range: e.target.value })}
                  placeholder="2024-01-01/2024-12-31"
                />
                <label className="text-xs text-slate-500">Threshold Method</label>
                <select
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.threshold_method}
                  onChange={(e) => setParams({ ...params, threshold_method: e.target.value })}
                >
                  <option value="percentile">Percentile</option>
                  <option value="fixed">Fixed</option>
                </select>
                <label className="text-xs text-slate-500">Cloud Cover Max</label>
                <input
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.cloud_cover_max}
                  onChange={(e) => setParams({ ...params, cloud_cover_max: Number(e.target.value) })}
                />
                <label className="text-xs text-slate-500">Target Percentile</label>
                <input
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.target_percentile}
                  onChange={(e) => setParams({ ...params, target_percentile: Number(e.target.value) })}
                />
                <label className="text-xs text-slate-500">Fixed Threshold (0–1)</label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.fixed_threshold}
                  onChange={(e) => setParams({ ...params, fixed_threshold: Number(e.target.value) })}
                />
                <label className="text-xs text-slate-500">Min Target Area (km²)</label>
                <input
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.min_area_km2}
                  onChange={(e) => setParams({ ...params, min_area_km2: Number(e.target.value) })}
                />
                <label className="text-xs text-slate-500">STAC Max Items</label>
                <input
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.max_items}
                  onChange={(e) => setParams({ ...params, max_items: Number(e.target.value) })}
                />
                <label className="text-xs text-slate-500">OSM Timeout (s)</label>
                <input
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                  value={params.osm_timeout_s}
                  onChange={(e) => setParams({ ...params, osm_timeout_s: Number(e.target.value) })}
                />
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={params.cache_downloads}
                    onChange={(e) => setParams({ ...params, cache_downloads: e.target.checked })}
                  />
                  Cache STAC downloads
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={params.use_synthetic}
                    onChange={(e) => setParams({ ...params, use_synthetic: e.target.checked })}
                  />
                  Use synthetic data (fast test mode)
                </label>
                {params.use_synthetic && (
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-slate-500">Synthetic Width</label>
                      <input
                        type="number"
                        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                        value={params.synthetic_width}
                        onChange={(e) => setParams({ ...params, synthetic_width: Number(e.target.value) })}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">Synthetic Height</label>
                      <input
                        type="number"
                        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
                        value={params.synthetic_height}
                        onChange={(e) => setParams({ ...params, synthetic_height: Number(e.target.value) })}
                      />
                    </div>
                  </div>
                )}
                <label className="text-xs text-slate-500">Weights Override (JSON)</label>
                <textarea
                  className="w-full border border-slate-300 rounded px-2 py-1 text-xs font-mono"
                  rows={4}
                  placeholder='{\"coastal_proximity\":0.3,\"slope\":0.2,\"bare_land\":0.2,\"sandiness\":0.2,\"river_proximity\":0.1}'
                  value={weightsText}
                  onChange={(e) => setWeightsText(e.target.value)}
                />
              </div>
            </details>
          </div>

          <button className="w-full bg-reef text-white py-2 rounded shadow-soft" onClick={handleRun}>
            Run Analysis
          </button>

          {error && <div className="text-xs text-red-600">{error}</div>}

          <div className="text-xs text-slate-500">
            This tool prioritizes areas for field validation; it does not confirm a deposit.
          </div>
        </div>

        <div className="mt-6">
          <h2 className="text-sm font-semibold">Progress</h2>
          <div className="mt-2 space-y-1 text-xs">
            {progressSteps.map((step) => (
              <div key={step} className="flex justify-between">
                <span>{step.replace('_', ' ')}</span>
                <span className="text-slate-500">{progress[step] || 'pending'}</span>
              </div>
            ))}
          </div>
        </div>

        {runId && runDetail?.status === 'completed' && (
          <div className="mt-6">
            <h2 className="text-sm font-semibold">Exports</h2>
            <div className="mt-2 flex flex-col gap-2 text-xs text-reef">
              <a href={`${API_URL}/runs/${runId}/exports/targets.geojson`} target="_blank">Download GeoJSON</a>
              <a href={`${API_URL}/runs/${runId}/exports/targets.csv`} target="_blank">Download CSV</a>
              <a href={`${API_URL}/runs/${runId}/report.html`} target="_blank">Open Report</a>
            </div>
          </div>
        )}

        <div className="mt-6">
          <h2 className="text-sm font-semibold">Layers</h2>
          <div className="mt-2 space-y-2 text-xs">
            {Object.entries(layerVisibility).map(([key, value]) => (
              <label key={key} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={value}
                  onChange={() => toggleLayer(key as keyof typeof layerVisibility)}
                />
                <span>{key}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-6">
          <h2 className="text-sm font-semibold">Targets</h2>
          <div className="mt-2 space-y-2">
            {targets?.features?.length ? (
              targets.features.map((f: any, idx: number) => (
                <button
                  key={f.properties.id}
                  className="w-full text-left border border-slate-200 rounded p-2 hover:border-reef"
                  onClick={async () => {
                    const detail = await getTargetDetail(runId!, f.properties.id)
                    setSelectedTarget(detail)
                  }}
                >
                  <div className="text-xs text-slate-500">#{idx + 1}</div>
                  <div className="text-sm font-semibold">Score {f.properties.mean_score.toFixed(2)}</div>
                  <div className="text-xs text-slate-500">Area {f.properties.area_km2.toFixed(2)} km²</div>
                  <div className="text-xs text-slate-500">Road dist {f.properties.distance_to_road_m ? Math.round(f.properties.distance_to_road_m) : 'n/a'} m</div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(f.properties.evidence_summary || []).map((chip: string) => (
                      <span key={chip} className="text-[10px] bg-slate-100 rounded px-1">{chip}</span>
                    ))}
                  </div>
                </button>
              ))
            ) : (
              <div className="text-xs text-slate-400">No targets yet.</div>
            )}
          </div>
        </div>
      </aside>

      <main className="flex-1 relative">
        <div ref={mapContainerRef} className="absolute inset-0" />
      </main>

      <aside className="w-[360px] bg-white/90 backdrop-blur border-l border-slate-200 shadow-soft p-4 overflow-y-auto panel-scroll">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Target Detail</h2>
          {selectedTarget && (
            <button className="text-xs text-slate-500" onClick={() => setSelectedTarget(null)}>Close</button>
          )}
        </div>
        {selectedTarget ? (
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <div className="text-xs text-slate-500">Target ID</div>
              <div className="font-mono text-xs break-all">{selectedTarget.id}</div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-slate-500">Area</div>
                <div>{selectedTarget.area_km2.toFixed(2)} km²</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Mean Score</div>
                <div>{selectedTarget.mean_score.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Max Score</div>
                <div>{selectedTarget.max_score.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Dist. to Road</div>
                <div>{selectedTarget.distance_to_road_m ? selectedTarget.distance_to_road_m.toFixed(0) : 'n/a'} m</div>
              </div>
            </div>

            <div>
              <div className="text-xs text-slate-500">Evidence</div>
              <pre className="text-[11px] bg-slate-50 border rounded p-2 overflow-x-auto">
                {JSON.stringify(selectedTarget.evidence, null, 2)}
              </pre>
            </div>

            <div>
              <div className="text-xs text-slate-500 mb-1">Suggested Next Steps</div>
              <ul className="text-xs text-slate-700 list-disc pl-4 space-y-1">
                <li>Validate access and land status.</li>
                <li>Run field traverse and map lithology/structures.</li>
                <li>Collect stream/soil or beach sand samples.</li>
                <li>Review historical drilling or public reports.</li>
              </ul>
            </div>

            {runId && (
              <div className="space-y-2">
                <a className="text-xs text-reef" href={`${API_URL}/runs/${runId}/exports/targets.geojson`} target="_blank">Download GeoJSON</a>
                <a className="text-xs text-reef block" href={`${API_URL}/runs/${runId}/exports/targets.csv`} target="_blank">Download CSV</a>
                <a className="text-xs text-reef block" href={`${API_URL}/runs/${runId}/report.html`} target="_blank">Open Report</a>
              </div>
            )}
          </div>
        ) : (
          <div className="mt-4 text-xs text-slate-400">Select a target to view evidence.</div>
        )}
      </aside>
    </div>
  )
}
