import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, GeoJSON, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Airport, RouteFare } from '../types';

const INDIA_CENTER: [number, number] = [22.5, 80.5];
const INDIA_ZOOM = 5;

const CARTO_API_KEY = 'cb1_4058_1_761f67dc62084a89816ae61b';
const INDIA_GEOJSON_URL = 'https://raw.githubusercontent.com/datasets/geo-boundaries-world-110m/master/countries/IND.geojson';

interface IndiaMapProps {
  airports: Airport[];
  selectedOrigin: string;
  selectedDestination: string;
  onSelectOrigin: (code: string) => void;
  onSelectDestination: (code: string) => void;
  routeFare: RouteFare | null;
}

function createAirportIcon(code: string, isSelected: boolean, isHovered: boolean) {
  const size = isSelected ? 32 : isHovered ? 28 : 20;
  const color = isSelected ? '#3291ff' : isHovered ? '#ef4444' : '#dc2626';
  const borderColor = isSelected ? '#ffffff' : isHovered ? '#e4e4e7' : '#52525b';

  return L.divIcon({
    className: 'airport-marker',
    html: `<div style="
      width: ${size}px;
      height: ${size}px;
      background: ${color};
      border: 2px solid ${borderColor};
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: ${isSelected ? 9 : 7}px;
      font-weight: 700;
      color: ${isSelected ? '#fff' : '#18181b'};
      box-shadow: 0 0 ${isSelected ? 16 : 8}px ${color}60;
      cursor: pointer;
      transition: all 0.2s ease;
      font-family: system-ui, sans-serif;
    ">${code}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function MapController({ selectedOrigin, selectedDestination }: { selectedOrigin: Airport | undefined; selectedDestination: Airport | undefined }) {
  const map = useMap();

  useEffect(() => {
    if (selectedOrigin && selectedDestination) {
      const bounds = L.latLngBounds(
        [selectedOrigin.lat, selectedOrigin.lon],
        [selectedDestination.lat, selectedDestination.lon]
      );
      map.fitBounds(bounds, { padding: [100, 100], maxZoom: 7 });
    } else if (selectedOrigin) {
      map.flyTo([selectedOrigin.lat, selectedOrigin.lon], 7, { duration: 1.5 });
    }
  }, [selectedOrigin, selectedDestination, map]);

  return null;
}

function IndiaBorders() {
  const [geojson, setGeojson] = useState<GeoJSON.GeoJsonObject | null>(null);

  useEffect(() => {
    fetch(INDIA_GEOJSON_URL)
      .then(r => r.json())
      .then(data => setGeojson(data as GeoJSON.GeoJsonObject))
      .catch(() => {});
  }, []);

  const style = {
    color: '#3291ff',
    weight: 2,
    opacity: 0.6,
    fillColor: '#3291ff',
    fillOpacity: 0.05,
  };

  if (!geojson) return null;

  return <GeoJSON data={geojson} style={style} />;
}

function MapLegend() {
  return (
    <div className="absolute bottom-4 left-4 z-[1000] bg-background/90 backdrop-blur-xl rounded-lg border border-border p-3 text-[10px]">
      <div className="font-semibold text-foreground mb-2">Legend</div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-[#dc2626] border border-[#52525b]"></span>
          <span className="text-muted">Airport</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-[#3291ff] border border-white"></span>
          <span className="text-muted">Selected</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-[#ef4444] border border-[#e4e4e7]"></span>
          <span className="text-muted">Hovered</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-0.5 w-4 bg-[#3291ff]"></span>
          <span className="text-muted">Route</span>
        </div>
      </div>
    </div>
  );
}

function MapSearch({ airports, onSelect }: { airports: Airport[]; onSelect: (code: string) => void }) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return airports.filter(a =>
      a.code.toLowerCase().includes(q) ||
      a.city.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q)
    ).slice(0, 5);
  }, [query, airports]);

  return (
    <div className="absolute top-4 right-4 z-[1000]">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIsOpen(true); }}
          onFocus={() => setIsOpen(true)}
          onBlur={() => setTimeout(() => setIsOpen(false), 200)}
          placeholder="Search airports..."
          className="h-8 w-48 rounded-lg border border-input bg-background/90 backdrop-blur-xl px-3 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
          aria-label="Search airports"
        />
        {isOpen && filtered.length > 0 && (
          <div className="absolute top-full mt-1 w-full bg-background/95 backdrop-blur-xl rounded-lg border border-border overflow-hidden">
            {filtered.map(a => (
              <button
                key={a.code}
                onClick={() => { onSelect(a.code); setQuery(''); setIsOpen(false); }}
                className="w-full text-left px-3 py-2 text-xs hover:bg-accent/10 transition-colors"
              >
                <span className="font-mono font-semibold text-foreground">{a.code}</span>
                <span className="text-muted ml-2">{a.city}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function IndiaMap({ airports, selectedOrigin, selectedDestination, onSelectOrigin, onSelectDestination, routeFare }: IndiaMapProps) {
  const [hoveredCode, setHoveredCode] = useState<string | null>(null);

  const originAirport = useMemo(() => airports.find(a => a.code === selectedOrigin), [airports, selectedOrigin]);
  const destAirport = useMemo(() => airports.find(a => a.code === selectedDestination), [airports, selectedDestination]);

  const handleMarkerClick = (code: string) => {
    if (!selectedOrigin || (selectedOrigin && selectedDestination)) {
      onSelectOrigin(code);
    } else if (selectedOrigin && !selectedDestination) {
      onSelectDestination(code);
    }
  };

  const routePositions = useMemo<[number, number][] | null>(() => {
    if (!originAirport || !destAirport) return null;
    return [
      [originAirport.lat, originAirport.lon],
      [destAirport.lat, destAirport.lon],
    ];
  }, [originAirport, destAirport]);

  return (
    <div className="h-full w-full">
      <MapContainer
        center={INDIA_CENTER}
        zoom={INDIA_ZOOM}
        style={{ height: '100%', width: '100%' }}
        zoomControl={true}
        attributionControl={false}
        className="z-0"
      >
        <TileLayer
          url={`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png?key=${CARTO_API_KEY}`}
          subdomains="abcd"
          maxZoom={20}
        />
        <IndiaBorders />
        <MapController selectedOrigin={originAirport} selectedDestination={destAirport} />

        {routePositions && (
          <Polyline
            positions={routePositions}
            pathOptions={{
              color: '#3291ff',
              weight: 3,
              opacity: 0.9,
              dashArray: '10 6',
            }}
          />
        )}

        {airports.map((airport) => {
          const isSelected = airport.code === selectedOrigin || airport.code === selectedDestination;
          const isHovered = airport.code === hoveredCode;
          const isOrigin = airport.code === selectedOrigin;
          const isDest = airport.code === selectedDestination;

          return (
            <Marker
              key={airport.code}
              position={[airport.lat, airport.lon]}
              icon={createAirportIcon(airport.code, isSelected, isHovered)}
              eventHandlers={{
                click: () => handleMarkerClick(airport.code),
                mouseover: () => setHoveredCode(airport.code),
                mouseout: () => setHoveredCode(null),
              }}
            >
              <Popup>
                <div className="text-center">
                  <div className="font-bold text-sm">{airport.city}</div>
                  <div className="text-xs text-gray-500">{airport.name}</div>
                  <div className="text-xs font-mono mt-1">{airport.code}</div>
                  {isOrigin && <div className="text-xs text-blue-500 mt-1">Origin</div>}
                  {isDest && <div className="text-xs text-green-500 mt-1">Destination</div>}
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      <MapLegend />
      <MapSearch airports={airports} onSelect={(code) => {
        if (!selectedOrigin || (selectedOrigin && selectedDestination)) {
          onSelectOrigin(code);
        } else {
          onSelectDestination(code);
        }
      }} />

      {routeFare && routeFare.avg_fare && (
        <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-[1000]">
          <div className="rounded-2xl border border-accent/30 bg-black/70 backdrop-blur-2xl px-6 py-3 shadow-2xl shadow-black/50">
            <div className="flex items-center gap-4">
              <div>
                <div className="text-[10px] text-white/40 uppercase tracking-wider">Route Fare</div>
                <div className="text-sm font-semibold text-white mt-0.5">
                  {selectedOrigin} → {selectedDestination}
                </div>
              </div>
              <div className="h-8 w-px bg-white/10" />
              <div className="text-right">
                <div className="text-2xl font-bold text-accent">
                  ₹{Number(routeFare.avg_fare).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </div>
                <div className="text-[10px] text-white/40">
                  {routeFare.observations} obs · {routeFare.source}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
