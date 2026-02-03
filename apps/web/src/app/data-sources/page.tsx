import Link from 'next/link'

const sources = [
  {
    name: 'Sentinel-2 L2A (Copernicus)',
    license: 'Copernicus Open Access / Creative Commons BY 4.0',
    url: 'https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-2-msi'
  },
  {
    name: 'Copernicus DEM GLO-30',
    license: 'Copernicus DEM – free and open',
    url: 'https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model'
  },
  {
    name: 'OpenStreetMap',
    license: 'ODbL 1.0',
    url: 'https://www.openstreetmap.org/copyright'
  },
  {
    name: 'STAC API (Microsoft Planetary Computer)',
    license: 'Open data endpoints',
    url: 'https://planetarycomputer.microsoft.com/'
  }
]

export default function DataSourcesPage() {
  return (
    <div className="min-h-screen p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Data Sources & Attribution</h1>
          <Link className="text-sm text-reef" href="/">Back to Map</Link>
        </div>

        <div className="bg-white/90 border border-slate-200 rounded p-4">
          <h2 className="text-lg font-semibold mb-2">Sources</h2>
          <ul className="text-sm text-slate-700 space-y-2">
            {sources.map((s) => (
              <li key={s.name}>
                <div className="font-medium">{s.name}</div>
                <div className="text-xs">License: {s.license}</div>
                <div className="text-xs">URL: {s.url}</div>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white/90 border border-slate-200 rounded p-4">
          <h2 className="text-lg font-semibold mb-2">How Scoring Works</h2>
          <p className="text-sm text-slate-700">
            REE Atlas India uses transparent weighted layers derived from open satellite imagery, terrain and OSM
            vectors. Each target includes evidence metrics and threshold pass rates. No machine learning is used in v1.
          </p>
        </div>

        <div className="bg-white/90 border border-slate-200 rounded p-4">
          <h2 className="text-lg font-semibold mb-2">Disclaimer</h2>
          <p className="text-sm text-slate-700">
            This tool provides an explainable prospectivity map for prioritization only. It does not confirm the
            presence of mineral deposits and must be validated through field work and professional review.
          </p>
        </div>
      </div>
    </div>
  )
}
