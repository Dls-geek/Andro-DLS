import { getBasePath } from '@/lib/utils'

const basePath = getBasePath()

export interface Screenshot {
  id: string
  src: string
  alt: string
}

export const screenshots: Screenshot[] = [
  {
    id: '1',
    src: `${basePath}/screenshots/Screenshot-1.png`,
    alt: 'Andro-DLS main dashboard showing device connection and menu options',
  },
  {
    id: '2',
    src: `${basePath}/screenshots/Screenshot-2.png`,
    alt: 'Andro-DLS device control panel with shell, screenshot, and recording options',
  },
  {
    id: '3',
    src: `${basePath}/screenshots/Screenshot-3.png`,
    alt: 'Andro-DLS data extraction module showing file manager and data dump options',
  },
  {
    id: '4',
    src: `${basePath}/screenshots/Screenshot-4.png`,
    alt: 'Andro-DLS media and app management interface',
  },
  {
    id: '5',
    src: `${basePath}/screenshots/Screenshot-5.png`,
    alt: 'Andro-DLS exploitation module with Metasploit integration',
  },
]