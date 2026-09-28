from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(os.environ.get('SITE_ROOT', 'site')).resolve()
BASE_PATH = os.environ.get('BASE_PATH', '/site-museum').rstrip('/')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + '\n', encoding='utf-8')


def generate_static_data() -> None:
    db_path = ROOT / 'db/custom.db'
    if not db_path.exists():
        raise SystemExit(f'Database not found: {db_path}')
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    movements = []
    for r in con.execute('SELECT id, slug, name, startYear, endYear, description, color, imageUrl, "order" FROM Movement ORDER BY "order" ASC'):
        movements.append(dict(r))

    artworks = []
    q = '''
      SELECT a.id, a.slug, a.title, a.artist, a.year, a.description, a.technique,
             a.dimensions, a.location, a.imageUrl, a.views, a.likes, a.featured,
             m.slug AS movementSlug, m.name AS movementName, m.color AS movementColor,
             EXISTS(SELECT 1 FROM AudioGuide g WHERE g.artworkId = a.id) AS hasAudio
      FROM Artwork a
      JOIN Movement m ON m.id = a.movementId
      ORDER BY a.id ASC
    '''
    for r in con.execute(q):
        artworks.append({
            'id': r['id'], 'slug': r['slug'], 'title': r['title'], 'artist': r['artist'],
            'year': r['year'], 'description': r['description'], 'technique': r['technique'],
            'dimensions': r['dimensions'], 'location': r['location'], 'imageUrl': r['imageUrl'],
            'views': r['views'], 'likes': r['likes'], 'featured': bool(r['featured']),
            'movement': {'slug': r['movementSlug'], 'name': r['movementName'], 'color': r['movementColor']},
            'hasAudio': bool(r['hasAudio']),
        })

    tracks = []
    q = '''
      SELECT g.id, g.slug, g.title, g.narrator, g.lang, g.transcript, g.transcriptPt,
             g.audioUrl, g."order", a.slug AS artworkSlug, a.title AS artworkTitle,
             a.artist AS artworkArtist, a.imageUrl AS artworkImageUrl, a.year AS artworkYear,
             m.name AS movementName
      FROM AudioGuide g
      LEFT JOIN Artwork a ON a.id = g.artworkId
      LEFT JOIN Movement m ON m.id = a.movementId
      ORDER BY g."order" ASC
    '''
    for r in con.execute(q):
        artwork = None
        if r['artworkSlug'] is not None:
            artwork = {
                'slug': r['artworkSlug'], 'title': r['artworkTitle'], 'artist': r['artworkArtist'],
                'imageUrl': r['artworkImageUrl'], 'year': r['artworkYear'], 'movementName': r['movementName'],
            }
        tracks.append({
            'id': r['id'], 'slug': r['slug'], 'title': r['title'], 'narrator': r['narrator'],
            'lang': r['lang'], 'transcript': r['transcript'], 'transcriptPt': r['transcriptPt'],
            'audioUrl': r['audioUrl'], 'order': r['order'], 'artwork': artwork,
        })

    rooms = []
    for r in con.execute('SELECT id, slug, name, description, panoramaUrl, hotspots, "order" FROM TourRoom ORDER BY "order" ASC'):
        rooms.append({
            'id': r['id'], 'slug': r['slug'], 'name': r['name'], 'description': r['description'],
            'panoramaUrl': r['panoramaUrl'], 'order': r['order'], 'hotspots': json.loads(r['hotspots']),
        })

    agg = con.execute('SELECT COUNT(*) AS artworks, COALESCE(SUM(views), 0) AS totalViews, COALESCE(SUM(likes), 0) AS totalLikes FROM Artwork').fetchone()
    stats = {
        'artworks': agg['artworks'],
        'movements': con.execute('SELECT COUNT(*) FROM Movement').fetchone()[0],
        'tracks': con.execute('SELECT COUNT(*) FROM AudioGuide').fetchone()[0],
        'rooms': con.execute('SELECT COUNT(*) FROM TourRoom').fetchone()[0],
        'totalViews': agg['totalViews'],
        'totalLikes': agg['totalLikes'],
    }
    con.close()

    data_dir = ROOT / 'public/data'
    data_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        'artworks.json': {'artworks': artworks},
        'movements.json': {'movements': movements},
        'audio-guides.json': {'tracks': tracks},
        'rooms.json': {'rooms': rooms},
        'stats.json': stats,
    }
    for filename, payload in payloads.items():
        (data_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def configure_next() -> None:
    write('next.config.ts', '''
import type { NextConfig } from "next";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
};

export default nextConfig;
''')
    package_path = ROOT / 'package.json'
    package = json.loads(package_path.read_text(encoding='utf-8'))
    package['scripts']['build'] = 'next build'
    package['scripts']['start'] = 'next dev -p 3000'
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def configure_data_fetchers() -> None:
    write('src/lib/museum.ts', r'''
/**
 * Musæum — shared types & static data contract for GitHub Pages.
 * GitHub Pages has no server runtime, so all museum data is exported to
 * public/data/*.json at build time and loaded by TanStack Query.
 */

export type MovementDTO = {
  id: number;
  slug: string;
  name: string;
  startYear: number;
  endYear: number;
  description: string;
  color: string;
  imageUrl: string | null;
  order: number;
};

export type ArtworkDTO = {
  id: number;
  slug: string;
  title: string;
  artist: string;
  year: string;
  description: string;
  technique: string;
  dimensions: string;
  location: string;
  imageUrl: string;
  views: number;
  likes: number;
  featured: boolean;
  movement: { slug: string; name: string; color: string };
  hasAudio: boolean;
};

export type AudioTrackDTO = {
  id: number;
  slug: string;
  title: string;
  narrator: string;
  lang: string;
  transcript: string;
  transcriptPt: string;
  audioUrl: string;
  order: number;
  artwork: {
    slug: string;
    title: string;
    artist: string;
    imageUrl: string;
    year: string;
    movementName: string;
  } | null;
};

export type HotspotDTO = {
  id: string;
  type: "teleport" | "info";
  lat: number;
  lon: number;
  label: string;
  targetRoomSlug?: string;
  artworkSlug?: string;
};

export type TourRoomDTO = {
  id: number;
  slug: string;
  name: string;
  description: string;
  panoramaUrl: string;
  order: number;
  hotspots: HotspotDTO[];
};

export type StatsDTO = {
  artworks: number;
  movements: number;
  tracks: number;
  rooms: number;
  totalViews: number;
  totalLikes: number;
};

export const qk = {
  artworks: ["artworks"] as const,
  artwork: (slug: string) => ["artwork", slug] as const,
  movements: ["movements"] as const,
  rooms: ["rooms"] as const,
  tracks: ["audio-guides"] as const,
  stats: ["stats"] as const,
};

export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
export const withBasePath = (path: string) =>
  path.startsWith("/") ? `${BASE_PATH}${path}` : path;

async function jsonOrThrow<T>(path: string): Promise<T> {
  const res = await fetch(withBasePath(path));
  if (!res.ok) throw new Error(`Falha ao carregar ${path} (${res.status})`);
  return res.json() as Promise<T>;
}

export const fetchArtworks = () =>
  jsonOrThrow<{ artworks: ArtworkDTO[] }>("/data/artworks.json").then((r) =>
    r.artworks.map((a) => ({ ...a, imageUrl: withBasePath(a.imageUrl) }))
  );

export const fetchMovements = () =>
  jsonOrThrow<{ movements: MovementDTO[] }>("/data/movements.json").then((r) =>
    r.movements.map((m) => ({
      ...m,
      imageUrl: m.imageUrl ? withBasePath(m.imageUrl) : null,
    }))
  );

export const fetchRooms = () =>
  jsonOrThrow<{ rooms: TourRoomDTO[] }>("/data/rooms.json").then((r) =>
    r.rooms.map((room) => ({
      ...room,
      panoramaUrl: withBasePath(room.panoramaUrl),
    }))
  );

export const fetchTracks = () =>
  jsonOrThrow<{ tracks: AudioTrackDTO[] }>("/data/audio-guides.json").then((r) =>
    r.tracks.map((track) => ({
      ...track,
      audioUrl: withBasePath(track.audioUrl),
      artwork: track.artwork
        ? { ...track.artwork, imageUrl: withBasePath(track.artwork.imageUrl) }
        : null,
    }))
  );

export const fetchStats = () => jsonOrThrow<StatsDTO>("/data/stats.json");
''')


def patch_collection() -> None:
    path = ROOT / 'src/components/museum/collection-section.tsx'
    text = path.read_text(encoding='utf-8')
    text = text.replace('import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";', 'import { useQuery, useQueryClient } from "@tanstack/react-query";')
    text = text.replace('import { useToast } from "@/hooks/use-toast";\n', '')
    text = text.replace('  const { toast } = useToast();\n', '')
    start = text.index('  const likeMutation = useMutation({')
    end = text.index('  const handleLike = (artwork: ArtworkDTO) => {', start)
    handle_end = text.index('\n  };', end) + len('\n  };')
    replacement = '''  const handleLike = (artwork: ArtworkDTO) => {
    // GitHub Pages is static: likes are intentionally local to this session.
    if (likedSlugs.includes(artwork.slug)) return;
    queryClient.setQueryData<ArtworkDTO[]>(qk.artworks, (old) =>
      (old ?? []).map((a) =>
        a.slug === artwork.slug ? { ...a, likes: a.likes + 1 } : a
      )
    );
    setLikedSlugs((prev) => [...prev, artwork.slug]);
  };'''
    text = text[:start] + replacement + text[handle_end:]
    path.write_text(text, encoding='utf-8')


def patch_dialog() -> None:
    path = ROOT / 'src/components/museum/artwork-dialog.tsx'
    text = path.read_text(encoding='utf-8')
    text = text.replace('import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";', 'import { useQuery, useQueryClient } from "@tanstack/react-query";')
    text = text.replace('import { useToast } from "@/hooks/use-toast";\n', '')
    text = text.replace('import { qk, type ArtworkDTO } from "@/lib/museum";', 'import { fetchArtworks, fetchTracks, qk, type ArtworkDTO } from "@/lib/museum";')
    old_fetch_start = text.index('async function fetchArtworkDetail')
    old_fetch_end = text.index('\n}\n', old_fetch_start) + 2
    new_fetch = '''async function fetchArtworkDetail(slug: string): Promise<ArtworkDetail> {
  const [artworks, tracks] = await Promise.all([fetchArtworks(), fetchTracks()]);
  const artwork = artworks.find((item) => item.slug === slug);
  if (!artwork) throw new Error("Obra não encontrada");
  const track = tracks.find((item) => item.artwork?.slug === slug);
  return {
    ...artwork,
    audioGuide: track
      ? { slug: track.slug, title: track.title, transcriptPt: track.transcriptPt }
      : null,
  };
}'''
    text = text[:old_fetch_start] + new_fetch + text[old_fetch_end:]
    text = text.replace('  const { toast } = useToast();\n', '')
    start = text.index('  const likeMutation = useMutation({')
    end = text.index('\n  const handleListen', start)
    replacement = '''  const handleLike = (slug: string) => {
    if (likedSlugs.includes(slug)) return;
    queryClient.setQueryData<ArtworkDTO[]>(qk.artworks, (old) =>
      (old ?? []).map((a) => (a.slug === slug ? { ...a, likes: a.likes + 1 } : a))
    );
    queryClient.setQueryData<ArtworkDetail>(qk.artwork(slug), (old) =>
      old ? { ...old, likes: old.likes + 1 } : old
    );
    setLikedSlugs((prev) => [...prev, slug]);
  };
'''
    text = text[:start] + replacement + text[end:]
    text = text.replace('onClick={() => likeMutation.mutate(artwork.slug)}', 'onClick={() => handleLike(artwork.slug)}')
    path.write_text(text, encoding='utf-8')


def configure_pwa() -> None:
    write('src/components/pwa/register-sw.tsx', r'''
"use client";

import { useEffect } from "react";
import { BASE_PATH } from "@/lib/museum";

/** Registers the Musæum service worker on HTTPS/localhost. */
export function RegisterSW() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const isSecure =
      window.location.protocol === "https:" ||
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1";
    if (!isSecure) return;

    const workerUrl = `${BASE_PATH}/sw.js`;
    const workerScope = `${BASE_PATH || ""}/`;
    const register = () => {
      navigator.serviceWorker
        .register(workerUrl, { scope: workerScope })
        .catch((err) => console.warn("[PWA] SW registration failed:", err));
    };

    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
''')
    write('public/manifest.webmanifest', '''
{
  "name": "Musæum — Museu Virtual de História da Arte",
  "short_name": "Musæum",
  "description": "Obras-primas em alta resolução, linha do tempo dos movimentos, tour virtual 3D e audioguia narrado.",
  "id": "./",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "orientation": "any",
  "background_color": "#171310",
  "theme_color": "#171310",
  "lang": "pt-BR",
  "dir": "ltr",
  "categories": ["education", "art", "entertainment"],
  "prefer_related_applications": false,
  "icons": [
    { "src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
''')
    write('public/sw.js', r'''
// Musæum PWA service worker — works at / locally and /site-museum/ on GitHub Pages.
const CACHE_NAME = "museum-pwa-v3";
const scopePath = new URL(self.registration.scope).pathname;
const BASE_PATH = scopePath === "/" ? "" : scopePath.replace(/\/$/, "");
const withBase = (path) => `${BASE_PATH}${path}`;

const PRECACHE = [
  withBase("/"),
  withBase("/manifest.webmanifest"),
  withBase("/icons/icon-192.png"),
  withBase("/icons/icon-512.png"),
  withBase("/data/artworks.json"),
  withBase("/data/movements.json"),
  withBase("/data/audio-guides.json"),
  withBase("/data/rooms.json"),
  withBase("/data/stats.json")
];

const CACHE_FIRST_PREFIXES = [
  withBase("/artworks/"),
  withBase("/panoramas/"),
  withBase("/audio/"),
  withBase("/icons/"),
  withBase("/data/"),
  withBase("/_next/static/")
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const isCacheFirst = CACHE_FIRST_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
  if (isCacheFirst) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            if (response && response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match(withBase("/"))))
    );
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.map((name) => name === CACHE_NAME ? null : caches.delete(name))))
      .then(() => self.clients.claim())
  );
});
''')


def patch_layout() -> None:
    path = ROOT / 'src/app/layout.tsx'
    text = path.read_text(encoding='utf-8')
    marker = 'export const metadata: Metadata = {'
    if 'const basePath = process.env.NEXT_PUBLIC_BASE_PATH' not in text:
        text = text.replace(marker, 'const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";\n\n' + marker)
    text = text.replace('manifest: "/manifest.webmanifest",', 'manifest: `${basePath}/manifest.webmanifest`,')
    text = text.replace('icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],', 'icon: [{ url: `${basePath}/icons/icon-192.png`, sizes: "192x192", type: "image/png" }],')
    text = text.replace('apple: [{ url: "/icons/icon-192.png" }],', 'apple: [{ url: `${basePath}/icons/apple-touch-icon.png` }],')
    path.write_text(text, encoding='utf-8')


def cleanup_server_only() -> None:
    for rel in ['src/app/api', 'src/lib/db.ts', 'prisma', 'db']:
        p = ROOT / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


def main() -> None:
    print(f'Preparing {ROOT} for GitHub Pages at {BASE_PATH or "/"}')
    generate_static_data()
    configure_next()
    configure_data_fetchers()
    patch_collection()
    patch_dialog()
    configure_pwa()
    patch_layout()
    cleanup_server_only()
    print('GitHub Pages/PWA preparation complete.')


if __name__ == '__main__':
    main()
