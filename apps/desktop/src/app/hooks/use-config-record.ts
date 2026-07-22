import { useQuery } from '@tanstack/react-query'

import { getSeraphielConfigRecord } from '@/seraphiel'
import { queryClient, writeCache } from '@/lib/query-client'
import type { SeraphielConfigRecord } from '@/types/seraphiel'

// One shared cache for the whole profile config record (`GET /api/config`).
// Every settings surface (MCP, model, config) reads and writes through this key
// so a save in one shows in the others, and revisiting a tab paints the cache
// instead of blanking on a fresh fetch.
//
// Distinct from session/hooks/use-seraphiel-config.ts, which is side-effecting —
// it pushes personality/cwd/voice/… into the session stores for live chat.
export const SERAPHIEL_CONFIG_KEY = ['seraphiel-config-record'] as const

// staleTime 0 → serve cache instantly, background-revalidate on every mount.
export const useSeraphielConfigRecord = () =>
  useQuery({ queryKey: SERAPHIEL_CONFIG_KEY, queryFn: getSeraphielConfigRecord, staleTime: 0 })

export const setSeraphielConfigCache = writeCache<SeraphielConfigRecord>(SERAPHIEL_CONFIG_KEY)

export const invalidateSeraphielConfig = () => queryClient.invalidateQueries({ queryKey: SERAPHIEL_CONFIG_KEY })
