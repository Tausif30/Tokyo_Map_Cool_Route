import { useEffect, useRef, useState } from "react";
import type { Place } from "./types";

interface SearchBoxProps {
  onSelect: (place: Place) => void;
  near?: { lat: number; lon: number };
  categories?: string[];
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
    <div ref={containerRef} className="searchbox-wrapper">
      <span className="searchbox-icon">
        <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
      </span>
      
      <input
        className="searchbox-input"
        type="text"
        value={query}
        placeholder={placeholder}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setIsOpen(true)}
        onKeyDown={handleKeyDown}
        aria-autocomplete="list"
        aria-expanded={isOpen}
      />
      
      {query && (
        <button 
          className="searchbox-clear" 
          onClick={() => { setQuery(""); setResults([]); setIsOpen(false); }}
          aria-label="Clear search"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      )}

      {isOpen && (
        <div role="listbox" className="search-results-list">
          {isLoading && <div className="search-status">Searching...</div>}
          {!isLoading && error && <div className="search-status error">{error}</div>}
          {!isLoading && !error && results.length === 0 && (
            <div className="search-status">No matches found</div>
          )}
          {!isLoading &&
            !error &&
            results.map((place, index) => (
              <div
                key={`${place.category}-${place.name}-${index}`}
                role="option"
                className={`search-option ${index === highlightedIndex ? 'highlighted' : ''}`}
                aria-selected={index === highlightedIndex}
                onMouseEnter={() => setHighlightedIndex(index)}
                onClick={() => pick(place)}
              >
                <strong>{place.name}</strong>
                <span>
                  {place.category}
                  {place.distance_m !== undefined &&
                    ` · ${(place.distance_m / 1000).toFixed(1)} km`}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}