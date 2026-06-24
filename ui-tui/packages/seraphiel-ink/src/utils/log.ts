export function logError(error: unknown): void {
  if (!process.env.SERAPHIEL_INK_DEBUG_ERRORS) {
    return
  }

  console.error(error)
}
