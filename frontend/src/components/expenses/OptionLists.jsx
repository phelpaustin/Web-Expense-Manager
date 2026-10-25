export default function OptionLists({ form, editForm, options, bulk }) {
  return (
    <>
      {/* Shared option lists — type a new value to add it (auto-learned on save). */}
      <datalist id="cat-options">
        {options.categories.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <datalist id="subcat-add-options">
        {(options.subcategories[form.category] || []).map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <datalist id="subcat-bulk-options">
        {(options.subcategories[bulk.category] || []).map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <datalist id="subcat-edit-options">
        {(options.subcategories[editForm.category] || []).map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <datalist id="shop-options">
        {(options.shops || []).map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
    </>
  )
}
