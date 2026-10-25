export const PAGE_SIZES = [10, 25, 50, 100]

// '__keep__' for the space means "leave it where it is"; '' is personal.
export const KEEP = '__keep__'
export const EMPTY_BULK = { category: '', subcategory: '', shop: '', description: '', group_id: KEEP }

export const SPACE_TYPE_ICONS = { household: '🏠', business: '💼', rental: '🏢', trip: '✈️', custom: '📁' }

// A tick box that can show "some of these are selected". Clicking it never toggles the bill group it sits in.
export function SelectBox({ state, onChange, label }) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={state === 'all'}
      ref={(el) => {
        if (el) el.indeterminate = state === 'some'
      }}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onChange(e.target.checked)}
    />
  )
}
