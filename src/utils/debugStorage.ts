// Debug utility to inspect localStorage keys for extraction results.
export function debugLocalStorage() {
  const extractionResults: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key?.startsWith('extraction_result_')) {
      extractionResults.push(key)
    }
  }

  return extractionResults
}
