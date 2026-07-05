/**
 * Net liquidity = bank_reserves - reverse_repo - tga
 *
 * Critical for crypto & risk-asset health: 2018-2022 crypto bull/bear
 * regime change tracked 1:1 with this number.
 *
 * @param {Array<{indicator_key: string, value_num: number}>} indicators
 *   Array of indicator observations (from macro_overview layer).
 * @returns {{ value: number|null, status: "ok"|"partial"|"missing", missing: string[] }}
 *   - value: net liquidity in USD billions (null if unavailable)
 *   - status: "ok" if all 3 sub-indicators present, "partial" if some, "missing" if none
 *   - missing: list of indicator_keys that are unavailable
 */
export function computeNetLiquidity(indicators) {
  if (!Array.isArray(indicators)) {
    return { value: null, status: "missing", missing: ["bank_reserves", "reverse_repo", "tga"] };
  }
  const byKey = new Map();
  for (const ind of indicators) {
    if (ind && ind.indicator_key) byKey.set(ind.indicator_key, ind);
  }
  const reserves = byKey.get("bank_reserves");
  const rrp = byKey.get("reverse_repo");
  const tga = byKey.get("tga");
  const missing = [];
  if (!reserves || reserves.value_num == null) missing.push("bank_reserves");
  if (!rrp || rrp.value_num == null) missing.push("reverse_repo");
  if (!tga || tga.value_num == null) missing.push("tga");
  if (missing.length === 3) return { value: null, status: "missing", missing };
  if (missing.length > 0) return { value: null, status: "partial", missing };
  return {
    value: reserves.value_num - rrp.value_num - tga.value_num,
    status: "ok",
    missing: [],
  };
}