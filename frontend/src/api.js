// Wrappers around FastAPI endpoints. We use fetch() returning JSON.
const API_ROOT = ''; // served alongside backend

export async function fetchOverview() {
  const res = await fetch(`${API_ROOT}/api/overview`);
  if (!res.ok) throw new Error('Failed to load overview');
  return res.json();
}

export async function fetchShows() {
  const res = await fetch(`${API_ROOT}/api/shows`);
  if (!res.ok) throw new Error('Failed to load shows list');
  return res.json();
}

export async function fetchShow(name) {
  const res = await fetch(`${API_ROOT}/api/shows/${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error('Show not found');
  return res.json();
}

export async function updateShow(name, config) {
  const res = await fetch(`${API_ROOT}/api/shows/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config })
  });
  if (!res.ok) throw new Error('Update failed');
  return res.json();
}

export async function fetchSettings() {
  const res = await fetch(`${API_ROOT}/api/settings`);
  if (!res.ok) throw new Error('Failed to load settings');
  return res.json();
}

export async function updateSettings(settings) {
  const res = await fetch(`${API_ROOT}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings })
  });
  if (!res.ok) throw new Error('Settings update failed');
  return res.json();
}
