// Debug utility to inspect localStorage
export function debugLocalStorage() {
  console.log('=== LocalStorage Debug ===')
  console.log('Total items:', localStorage.length)
  
  const extractionResults: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key?.startsWith('extraction_result_')) {
      extractionResults.push(key)
      const value = localStorage.getItem(key)
      console.log(`${key}:`, value ? JSON.parse(value) : 'null')
    }
  }
  
  console.log('Extraction result keys:', extractionResults)
  console.log('======================')
  
  return extractionResults
}

// Call this from browser console: window.debugStorage()
if (typeof window !== 'undefined') {
  (window as any).debugStorage = debugLocalStorage
}
