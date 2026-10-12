type Palette = 'current'

const options: { value: Palette; label: string }[] = [
  { value: 'current', label: 'Current palette' },
]

export default function PalettePreview({ value, onChange }: { value: Palette; onChange: (palette: Palette) => void }) {
  return (
    <section className="palette-preview-tools" aria-label="Color palette previews">
      <div className="palette-preview-label">
        <strong>Palette preview</strong>
        <span>Preview only · not saved</span>
      </div>
      <div className="palette-preview-options" role="group" aria-label="Choose a palette to preview">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={value === option.value}
            className={value === option.value ? 'selected' : ''}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  )
}
