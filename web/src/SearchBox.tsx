import { useEffect, useRef, useState } from "react";
import type { Place } from "./types";

interface SearchBoxProps {
  /** Called when the user picks a result — from typing OR (see note in
   * the module comment at the bottom) from clicking an item in the
   * existing "Nearby cool spots" list. Wire both to this same handler
   * in the parent so Point B always gets set the same way regardless
   * of which UI the place came from. */
  onSelect: (place: Place) => void;
  /** Optional (lat, lon) — usually Point A / current location — used
   * server-side to break ties between similarly-good text matches by
   * distance. Omit if there's no current location yet. */
  near?: { lat: number; lon: number };
  /** Restrict results to specific categories, e.g. ["Hospital",
   * "Pharmacy"]. Omit to search everything. */
  categories?: string[];
  /** Base URL of the FastAPI backend. Defaults to same-origin, which is
   * fine once frontend+API are served together — override this during
   * local dev if they're on different ports (see api.py's own
   * location_test.html for that exact situation). */
  apiBaseUrl?: string;
  placeholder?: string;
}

const DEBOUNCE_MS = 250;

export default function SearchBox({
  onSelect,
  near,
  categories,
  apiBaseUrl = "",
  placeholder = "Search for a destination...",
}: SearchBoxProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [error, setError] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (trimmed.length === 0) {
      setResults([]);
      setIsOpen(false);
      setError(null);
      return;
    }

    debounceRef.current = setTimeout(() => {
      const thisRequest = ++requestSeq.current;
      setIsLoading(true);
      setError(null);

      const params = new URLSearchParams({ q: trimmed, limit: "10" });
      if (near) {
        params.set("near_lat", String(near.lat));
        params.set("near_lon", String(near.lon));
      }
      if (categories && categories.length > 0) {
        params.set("categories", categories.join(","));
      }

      fetch(`${apiBaseUrl}/search-places?${params.toString()}`)
        .then((res) => {
          if (!res.ok) throw new Error(`search failed (${res.status})`);
          return res.json() as Promise<Place[]>;
        })
        .then((data) => {
          // ignore stale responses if the user kept typing
          if (thisRequest !== requestSeq.current) return;
          setResults(data);
          setIsOpen(true);
          setHighlightedIndex(-1);
        })
        .catch((err: Error) => {
          if (thisRequest !== requestSeq.current) return;
          setError(err.message);
          setResults([]);
          setIsOpen(true);
        })
        .finally(() => {
          if (thisRequest === requestSeq.current) setIsLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, near?.lat, near?.lon, categories?.join(",")]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function pick(place: Place) {
    onSelect(place);
    setQuery(place.name);
    setIsOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && highlightedIndex >= 0) {
      event.preventDefault();
      pick(results[highlightedIndex]);
    } else if (event.key === "Escape") {
      setIsOpen(false);
    }
  }

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <input
        type="text"
        value={query}
        placeholder={placeholder}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setIsOpen(true)}
        onKeyDown={handleKeyDown}
        aria-autocomplete="list"
        aria-expanded={isOpen}
      />
      {isOpen && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 20,
            background: "white",
            border: "1px solid #ddd",
            borderRadius: 8,
            marginTop: 4,
            maxHeight: 280,
            overflowY: "auto",
            boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
          }}
        >
          {isLoading && <div style={{ padding: 12 }}>Searching...</div>}
          {!isLoading && error && (
            <div style={{ padding: 12, color: "#c0392b" }}>{error}</div>
          )}
          {!isLoading && !error && results.length === 0 && (
            <div style={{ padding: 12, color: "#888" }}>No matches found</div>
          )}
          {!isLoading &&
            !error &&
            results.map((place, index) => (
              <div
                key={`${place.category}-${place.name}-${index}`}
                role="option"
                aria-selected={index === highlightedIndex}
                onMouseEnter={() => setHighlightedIndex(index)}
                onClick={() => pick(place)}
                style={{
                  padding: "8px 12px",
                  cursor: "pointer",
                  background: index === highlightedIndex ? "#eef4ff" : "white",
                }}
              >
                <div style={{ fontWeight: 600 }}>{place.name}</div>
                <div style={{ fontSize: 12, color: "#888" }}>
                  {place.category}
                  {place.distance_m !== undefined &&
                    ` · ${(place.distance_m / 1000).toFixed(1)} km`}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

/*
INTEGRATION NOTES (the part I can't do for you without seeing App.tsx /
MapView.tsx — see chat message):

1. Replace whatever currently renders "Point B / COOL DESTINATION /
   Select a place on the map" with:
       <SearchBox
         near={pointA ? { lat: pointA.lat, lon: pointA.lon } : undefined}
         onSelect={handleSelectDestination}
       />

2. Define ONE shared handler in App.tsx:
       function handleSelectDestination(place: Place) {
         setPointB({ lat: place.lat, lon: place.lon, label: place.name });
         mapRef.current?.flyTo([place.lat, place.lon], 15); // or however
       }                                                     // MapView
                                                               // currently
                                                               // exposes
                                                               // map control

3. Wire the EXACT SAME handler to each item's onClick in the existing
   right-panel "Nearby cool spots" list — that's the "lock into that one
   as well" part of the ask. Whatever shape that list's items are in
   today, as long as each one can produce a {name, category, lat, lon}
   it can call handleSelectDestination directly, no new logic needed.
*/