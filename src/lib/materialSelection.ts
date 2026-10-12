export const MAX_FILE_BYTES = 100 * 1024 * 1024

const supportedTypes = [
  { extension: '.pdf', mime: 'application/pdf', label: 'PDF' },
  { extension: '.pptx', mime: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', label: 'PowerPoint' },
  { extension: '.docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', label: 'Word document' },
  { extension: '.mp4', mime: 'video/mp4', label: 'MP4 video' },
] as const

export type SelectedMaterial = { id: string; file: File }
export type SelectionResult = { accepted: SelectedMaterial[]; errors: string[] }

export function validateMaterial(file: File): string | null {
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  const type = supportedTypes.find((candidate) => candidate.extension === extension)
  if (!type) return 'Choose a PDF, PPTX, DOCX, or MP4 file.'
  if (file.type && file.type !== type.mime && file.type !== 'application/octet-stream') {
    return `The file contents do not match the ${type.label} extension.`
  }
  if (file.size > MAX_FILE_BYTES) return 'Files must be 100 MB or smaller.'
  return null
}

export function selectMaterials(files: readonly File[]): SelectionResult {
  const accepted: SelectedMaterial[] = []
  const errors: string[] = []
  files.forEach((file) => {
    const error = validateMaterial(file)
    if (error) errors.push(`${file.name}: ${error}`)
    else accepted.push({ id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2)}`, file })
  })
  return { accepted, errors }
}

export function removeMaterial(materials: readonly SelectedMaterial[], id: string): SelectedMaterial[] {
  return materials.filter((material) => material.id !== id)
}
