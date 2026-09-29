const allowedExtensions = new Set(['pdf', 'doc', 'docx', 'ppt', 'pptx'])
export const MAX_MATERIAL_FILES = 10
export const MAX_MATERIAL_FILE_BYTES = 25 * 1024 * 1024

export function fileExtension(filename) {
  return String(filename || '').split('.').pop()?.toLowerCase() || ''
}

export function formatFileSize(sizeBytes) {
  const size = Number(sizeBytes) || 0
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function validateMaterialFiles(files, existingCount = 0) {
  if (existingCount + files.length > MAX_MATERIAL_FILES) {
    return 'A Learning Material can include at most 10 files.'
  }
  if (files.some((file) => !allowedExtensions.has(fileExtension(file.name)))) {
    return 'That file type is not supported. Choose PDF, DOC, DOCX, PPT, or PPTX.'
  }
  if (files.some((file) => file.size > MAX_MATERIAL_FILE_BYTES)) {
    return 'Each file must be 25 MB or smaller.'
  }
  return ''
}

export function downloadBlobResponse(response, fallbackFilename) {
  const disposition = response.headers?.['content-disposition'] || ''
  const encodedFilename = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quotedFilename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  let filename = quotedFilename || fallbackFilename
  if (encodedFilename) {
    try {
      filename = decodeURIComponent(encodedFilename)
    } catch {
      filename = fallbackFilename
    }
  }
  const objectUrl = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}
