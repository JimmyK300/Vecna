export function getSimilarId(query = {}) {
  return query.id || null;
}

export function buildSimilarNavigation(id, params = {}, offset = 0) {
  return { ...params, id, offset };
}
