import { normalize } from './search.js';
export function search(items, query) { return items.filter(x => normalize(x).includes(normalize(query))); }
