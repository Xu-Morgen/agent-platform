// 只实现当前导出 Schema 所用的 JSON 校验子集；不维护另一份字段模型。
function validate(schema, value, root = schema) {
  if (schema.$ref) return validate(schema.$ref.slice(2).split('/').reduce((v, k) => v[k], root), value, root);
  if (schema.anyOf && !schema.anyOf.some((s) => validate(s, value, root))) return false;
  if (schema.oneOf && schema.oneOf.filter((s) => validate(s, value, root)).length !== 1) return false;
  if ('const' in schema && value !== schema.const) return false;
  if (schema.enum && !schema.enum.includes(value)) return false;
  if (schema.type === 'null' && value !== null) return false;
  if (schema.type === 'string' && typeof value !== 'string') return false;
  if (schema.type === 'boolean' && typeof value !== 'boolean') return false;
  if (schema.type === 'integer' && !Number.isInteger(value)) return false;
  if (schema.type === 'number' && (typeof value !== 'number' || !Number.isFinite(value))) return false;
  if (schema.pattern && !new RegExp(schema.pattern).test(value)) return false;
  if (schema.minimum !== undefined && value < schema.minimum) return false;
  if (schema.maximum !== undefined && value > schema.maximum) return false;
  if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) return false;
  if (schema.type === 'array') {
    if (!Array.isArray(value) || !value.every((v) => validate(schema.items, v, root))) return false;
  }
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    if ((schema.required || []).some((key) => !Object.hasOwn(value, key))) return false;
    for (const [key, v] of Object.entries(value)) {
      if (!Object.hasOwn(schema.properties || {}, key)) {
        if (schema.additionalProperties === false) return false;
      } else if (!validate(schema.properties[key], v, root)) return false;
    }
  }
  return true;
}
module.exports = { validate };
