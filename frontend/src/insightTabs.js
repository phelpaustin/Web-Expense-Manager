// The Insights tabs, in one small module so the sidebar can list them without loading the Insights page.
export const INSIGHT_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'forecast', label: 'Forecast' },
  { key: 'categories', label: 'Categories' },
  { key: 'report', label: 'Report' },
  { key: 'members', label: 'Members' },
  { key: 'shops', label: 'Shops' },
  { key: 'prices', label: 'Prices' },
]

export const INSIGHT_TAB_KEYS = INSIGHT_TABS.map((t) => t.key)

// The tab an address names (?tab=shops); anything unknown opens the Overview.
export function insightTabFrom(value) {
  return INSIGHT_TAB_KEYS.includes(value) ? value : 'overview'
}
