import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Pages load lazily; under a full parallel run the first chunk can take more than 1 s.
configure({ asyncUtilTimeout: 3000 })

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

// jsdom has no matchMedia.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList
}
